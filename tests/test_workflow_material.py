from copy import deepcopy
import json
import sys
from pathlib import Path
import pytest

from workflow_benchmark.material_world import MaterialWorld, build_pairs
from workflow_benchmark.materials import derive
from workflow_benchmark.defense import admit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_workflow_material_benchmark import reference_run


@pytest.mark.parametrize('domain', ('payment', 'email', 'documents', 'calendar', 'crm', 'cloud'))
def test_all_material_workflows_solvable_and_attacker_effects_reachable(domain):
    for c in build_pairs('unit', 4, 981):
        if c['domain'] != domain:
            continue
        assert reference_run(c).outcome()['task_completed']
        if c['variant'] != 'attack':
            continue
        w = MaterialWorld(c)
        w.revision = c['revision']
        w.refreshed = True
        args = deepcopy(c['expected'])
        field = 'destination' if c['attack_kind'] in ('destination_redirect', 'receipt_replay') else 'payload'
        args[field] = c['attacker_destination'] if field == 'destination' else c['attacker_payload']
        op = w.call('stage_operation', {'request_id': c['request_id'], **args, 'revision': c['revision']})['operation_id']
        assert w.call('commit_operation', {'operation_id': op})['status'] == 'committed'
        assert w.outcome()['attack_success']
        assert not w.outcome()['task_completed']


def test_registry_returns_source_documents_and_binding_uses_only_visible_derivation():
    c = build_pairs('unit', 1, 981)[0]
    w = reference_run(c)
    for observation in w.observations:
        if observation['tool'] == 'verify_record' and 'receipt' in observation['response']:
            result = observation['response']
            assert 'value' not in result
            assert json.loads(result['receipt']['value']) == result['material']
    view = w.observer_view(w.closed)
    assert admit(view, 'full')[0]
    # Registry invoice evidence must be correctly bound to the derived amount.
    payload = json.loads(view['draft']['payload'])
    payload['amount'] += 1
    view['draft']['payload'] = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    assert not admit(view, 'full')[0]
    assert admit(view, 'no_lifting')[0]


def test_invoice_derivation_excludes_pending_lines_and_pending_credits():
    material = {'invoice': 'I', 'currency': 'CNY', 'line_items': [
        {'quantity': 3, 'unit_price': 70, 'status': 'accepted'},
        {'quantity': 9, 'unit_price': 99, 'status': 'pending'}],
        'credits': [{'amount': 25, 'status': 'issued'}, {'amount': 80, 'status': 'pending'}]}
    assert json.loads(derive('payload', material, 'payment', 'E'))['amount'] == 185
