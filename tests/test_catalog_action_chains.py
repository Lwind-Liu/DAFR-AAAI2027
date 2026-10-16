import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_catalog_action_chains as chains


def test_chain_requires_real_commits_and_unlocks_distinct_operations():
    case = next(c for c in chains.make_cases() if c['length'] == 2 and c['domain'] == 'payment' and c['variant'] == 'clean')
    world = chains.ChainWorld(case)
    next_request = case['children'][1]['request_id']
    assert world.call('read_request', {'request_id': next_request})['error'] == 'workflow_prerequisite_not_complete'
    first_request = case['children'][0]['request_id']
    assert world.call('close_request', {'request_id': first_request, 'operation_id': 'W1-OP-1'})['error'] == 'operation_not_executed'
    for step, child in enumerate(case['children'], 1):
        request = world.call('read_request', {'request_id': child['request_id']})
        op = f'W{step}-OP-1'
        assert op in request['prepared_operations']
        assert world.call('commit_operation', {'operation_id': op})['status'] == 'committed'
        closed = world.call('close_request', {'request_id': child['request_id'], 'operation_id': op})
        assert closed['workflow_complete'] == (step == 2)
    assert world.outcome()['task_completed']
    assert world.outcome()['completed_operations'] == 2


def test_one_attack_per_chain_and_request_scoped_static_guards():
    cases = chains.make_cases()
    for case in cases:
        assert sum(c['variant'] == 'attack' for c in case['children']) == (case['variant'] == 'attack')
    case = next(c for c in cases if c['length'] == 2 and c['domain'] == 'payment' and c['variant'] == 'clean')
    world = chains.ChainWorld(case)
    guard = chains.ChainGuard('static')
    for step, child in enumerate(case['children'], 1):
        world.call('read_request', {'request_id': child['request_id']})
        op = f'W{step}-OP-1'
        assert guard(world.observer_view(op))[0]
        world.call('commit_operation', {'operation_id': op})
        world.call('close_request', {'request_id': child['request_id'], 'operation_id': op})
    assert set(guard.guards) == {c['request_id'] for c in case['children']}
