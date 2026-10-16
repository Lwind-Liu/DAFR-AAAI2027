"""Resolve prepared-operation handles without replacing native DRIFT checks."""
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import catalog_baseline_adapter_v9 as adapter
from agentdojo.agent_pipeline.drift_defense.drift_llm import DRIFTLLM


def test_corrected_handle_passes_but_wrong_business_destination_is_rejected():
    core = object.__new__(DRIFTLLM)
    core.logger = logging.getLogger(__name__)
    core.achieved_function_trajectory = ['commit_operation']
    bridge = SimpleNamespace()
    world = SimpleNamespace(drafts={'OP-2': {'destination': 'approved-bank', 'payload': 'amount=100'}})
    adapter.install_resolved_draft_check(core, bridge, world)
    checklist = json.dumps([{'name': 'commit_operation', 'required parameters': {
        'operation_id': 'OP-1', 'destination': 'approved-bank', 'payload': 'amount=100'}}])
    proposal = [{'function': {'name': 'commit_operation', 'arguments': '{"operation_id":"OP-2"}'}}]
    assert core.node_check(checklist, proposal)[0]
    assert json.loads(proposal[0]['function']['arguments']) == {'operation_id': 'OP-2'}
    world.drafts['OP-2']['destination'] = 'unauthorized-bank'
    assert not core.node_check(checklist, proposal)[0]
    assert len(bridge.audit_events) == 2


def test_protocol_retry_does_not_treat_a_final_answer_as_a_tool_proposal():
    assert adapter.drift_unexecuted_proposal({'content': '<function_call>[commit_operation(operation_id="OP-1")]</function_call>'}, [])
    assert not adapter.drift_unexecuted_proposal({'content': 'The task is complete.'}, [])
