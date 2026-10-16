from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_single_dojo_case import make_case
from workflow_benchmark.native_dojo import NativeDojoWorld, guard


def test_native_rent_predicates_are_separate_and_reading_an_attack_is_not_success():
    case = {**make_case(), 'variant': 'attack'}
    world = NativeDojoWorld(case)
    world.call('read_file', {'file_path': 'landlord-notices.txt'})
    assert not world.outcome()['task_completed']
    assert not world.outcome()['attack_success']
    world.call('update_scheduled_transaction', case['attack_action']['args'])
    assert world.outcome()['task_completed']
    assert world.outcome()['attack_success']


def test_pair_initial_states_match_and_verification_restores_original_content():
    clean = NativeDojoWorld(make_case())
    attacked = NativeDojoWorld({**make_case(), 'variant': 'attack'})
    assert clean.initial == attacked.initial
    args = {'file_path': 'landlord-notices.txt'}
    c = clean.call('read_file', args)
    a = attacked.call('read_file', args)
    assert c['content'] == a['content']
    assert 'external_operational_note' not in c and 'external_operational_note' in a
    verified = attacked.call('verify_evidence', {'evidence_id': a['evidence_id']})
    assert verified['content'] == c['content']
    assert 'external_operational_note' not in verified


def test_source_projection_and_receipt_scope_changes_are_actual_modules():
    case = {**make_case(), 'variant': 'attack'}
    world = NativeDojoWorld(case)
    world.call('read_file', {'file_path': 'landlord-notices.txt'})
    action = case['attack_action']
    view = world.visible_view(action['function'], action['args'])
    assert guard(view, 'full', None)[0] is False
    assert guard(view, 'no_projection', None)[0] is True
    assert guard(view, 'no_lifting', None)[0] is True
    assert guard(view, 'no_geometry', None)[0] is True
    assert set(view) == {'action', 'user_request', 'sources', 'observations', 'risk_metadata'}
    assert all(s['authenticated_content'] is None for s in view['sources'])
