"""Check isolation and genuine enforcement in the small baseline adapters."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_flash_other_methods as baseline


class FakeClient:
    def __init__(self, policy):
        self.policy = policy
        self.messages = []

    def chat(self, messages, tools=None, max_tokens=650):
        self.messages.append(messages)
        return {'role': 'assistant', 'content': json.dumps(self.policy)}, {}


def test_progent_policies_do_not_cross_task_boundaries():
    cases = [json.loads(s) for s in (ROOT / 'data/flash_business_geometry_final_v4/test.jsonl').read_text().splitlines()[:2]]
    adapters = []
    for case in cases:
        field = case['fields'][0]
        policy = [{'name': case['tool'], 'args': {field: {'enum': [case['desired'][field]]}}}]
        adapters.append(baseline.ProgentAdapter(case, FakeClient(policy)))
    first, second = adapters
    assert first.admit(cases[0]['tool'], cases[0]['desired'])[0]
    assert not first.admit(cases[0]['tool'], cases[1]['desired'])[0]
    assert second.admit(cases[1]['tool'], cases[1]['desired'])[0]
    assert first.core.security_policy is not second.core.security_policy


def test_baseline_has_no_hidden_dafr_risk_gate():
    case = json.loads((ROOT / 'data/flash_business_geometry_final_v4/test.jsonl').read_text().splitlines()[0])
    client = FakeClient([{'name': case['tool'], 'args': {}}])
    adapter = baseline.ProgentAdapter(case, client)
    # The original policy checker can admit an unverified operation; the oracle
    # remains in the world outcome, never inserted into this admission decision.
    world = baseline.AgentWorld(case)
    assert not world.grants
    assert adapter.admit(case['tool'], case['desired'])[0]
    assert all('desired' not in m[1]['content'] for m in client.messages)


def test_drift_uses_original_core_and_new_tool_schemas():
    case = json.loads((ROOT / 'data/flash_business_geometry_final_v4/test.jsonl').read_text().splitlines()[0])
    core, bridge, runtime = baseline.drift_setup(case, baseline.AgentWorld(case), None)
    assert type(core).__name__ == 'DRIFTLLM'
    assert core.args.build_constraints and core.args.injection_isolation and core.args.dynamic_validation
    assert set(runtime.functions) == {t['function']['name'] for t in baseline.schemas(case)}
    assert core.user_approval_request() is False
