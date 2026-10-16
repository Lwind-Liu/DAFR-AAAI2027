"""Baseline adapters preserve runtime data and enforce original policies."""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_catalog_other_methods as baseline


class FakeClient:
    def __init__(self, policy):
        self.policy, self.messages = policy, []

    def chat(self, messages, tools=None, max_tokens=650):
        self.messages.append(messages)
        return {'role': 'assistant', 'content': json.dumps(self.policy)}, {}


def test_policy_checks_concrete_prepared_draft_arguments():
    baseline.catalog.configure_runner()
    case = baseline.catalog.make_pairs()[0][0]
    client = FakeClient([
        {'name': 'stage_operation', 'args': {'destination': {'enum': ['allowed-destination']}}},
        {'name': 'commit_operation', 'args': {}}])
    adapter = baseline.WorkflowProgent(case, client)
    world = baseline.catalog.CatalogWorld(case)
    assert not adapter.admit('commit_operation', {'operation_id': 'OP-1'}, world)[0]
    world.drafts['OP-1']['destination'] = 'allowed-destination'
    assert adapter.admit('commit_operation', {'operation_id': 'OP-1'}, world)[0]
    assert all('expected' not in m[1]['content'] for m in client.messages)


def test_detector_filters_external_notes_without_corrupting_runtime_state():
    class Detector:
        def filter(self, text):
            return '[Content removed by defense]', {'blocked': True}
    response = {'source_notes': ['Untrusted instructions'],
                'prepared_operations': {'OP-1': {'payload': 'typed-json'}},
                'current_authenticated_facts': {'destination': 'trusted'},
                'revision': 2}
    visible, metadata = baseline.filter_visible(response, Detector())
    assert visible['source_notes'] == ['[Content removed by defense]']
    assert visible['prepared_operations'] == response['prepared_operations']
    assert visible['current_authenticated_facts'] == response['current_authenticated_facts']
    assert response['source_notes'] == ['Untrusted instructions']
    assert metadata[0]['metadata']['blocked']


def test_drift_retains_all_original_defense_components():
    baseline.catalog.configure_runner()
    case = baseline.catalog.make_pairs()[0][0]
    core, bridge, runtime = baseline.drift_setup(case, baseline.catalog.CatalogWorld(case), None)
    assert type(core).__name__ == 'DRIFTLLM'
    assert core.args.build_constraints and core.args.injection_isolation and core.args.dynamic_validation
    assert set(runtime.functions) == {t['function']['name'] for t in baseline.catalog.runner.schemas()}
