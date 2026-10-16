"""Protocol compatibility checks on the unchanged catalog environment."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import catalog_baseline_adapter_v2 as adapter
from agentdojo.agent_pipeline.drift_defense.drift_llm import DRIFTLLM
from agentdojo.functions_runtime import FunctionCall


def test_native_call_preserves_name_and_arguments_in_drift_parser():
    class Client:
        def chat(self, messages, tools=None, max_tokens=650):
            assert tools and max_tokens == 650
            return {'content': '', 'tool_calls': [{'function': {
                'name': 'verify_record', 'arguments': '{"record_id":"record-1"}'}}]}, {}
    bridge = adapter.WorkflowDriftClient({}, None, Client())
    tools = [{'name': 'verify_record', 'description': 'Verify a record',
              'parameters': {'type': 'object', 'properties': {'record_id': {'type': 'string'}}}}]
    output = bridge.agent_run([{'role': 'system', 'content': 'Use tools'}], tools, query='verify')[0]
    parsed = object.__new__(DRIFTLLM)._parse_model_output(output)
    assert parsed['tool_calls'][0].function == 'verify_record'
    assert parsed['tool_calls'][0].args == {'record_id': 'record-1'}


def test_failed_registry_read_can_retry_but_successful_call_is_deduplicated():
    core = object.__new__(adapter.shared_budget_drift_class(DRIFTLLM))
    messages = [{'role': 'assistant', 'tool_calls': [FunctionCall(
        function='verify_record', args={'record_id': 'record-1'}, id='call-1')]},
        {'role': 'tool', 'tool_call_id': 'call-1',
         'content': '{"error":"registry_temporarily_unavailable"}'}]
    assert core._load_previous_calls(messages) == []
    messages[-1]['content'] = '{"value":"current"}'
    assert len(core._load_previous_calls(messages)) == 1


def test_truncated_native_arguments_enter_original_parse_retry():
    class Client:
        def chat(self, messages, tools=None, max_tokens=650):
            return {'content': '', 'tool_calls': [{'function': {
                'name': 'stage_operation', 'arguments': '{"payload":"unfinished'}}]}, {}
    bridge = adapter.WorkflowDriftClient({}, None, Client())
    output = bridge.agent_run([{'role': 'system', 'content': 'Use tools'}], [], query='stage')[0]
    assert output == '<function_call>[invalid_function_call(</function_call>'
