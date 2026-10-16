"""Current facts repair drafts without inventing execution authorization."""
from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_workflow_catalog_v2 import CatalogWorld, make_pairs
from run_targeted_payment_case import simple_linear
from workflow_benchmark.defense import representation
from workflow_benchmark.repair_feedback import admit_with_facts, current_facts


def test_authenticated_read_facts_are_visible_equally_to_all_planners():
    case = next(p[1] for p in make_pairs() if p[0]['lane'] == 'signed_snapshot')
    world = CatalogWorld(case)
    reply = world.call('read_request', {'request_id': case['request_id']})
    assert reply['current_authenticated_facts'] == case['expected']
    scene, _ = representation(world.observer_view('OP-1'))
    assert scene['grants'] == []  # publisher authentication is not a write grant


def test_repair_fact_copy_cannot_override_joint_risk_check():
    case = deepcopy(next(p[0] for p in make_pairs() if p[0]['lane'] == 'signed_snapshot'))
    case['risk_metadata']['events']['source']['probability'] = .5
    case['risk_metadata']['events']['routing']['probability'] = .5
    world = CatalogWorld(case)
    world.call('read_request', {'request_id': case['request_id']})
    allowed, feedback = admit_with_facts(world.observer_view('OP-1'), 'full', simple_linear())
    assert not allowed
    op = world.call('stage_operation', {'request_id': case['request_id'], 'revision': 2,
        **feedback['current_authenticated_facts']})['operation_id']
    assert not admit_with_facts(world.observer_view(op), 'full', simple_linear())[0]


def test_untrusted_current_approval_memo_is_not_a_repair_fact():
    case = next(p[0] for p in make_pairs() if p[0]['lane'] == 'cache_approval_mismatch')
    world = CatalogWorld(case)
    world.call('read_request', {'request_id': case['request_id']})
    view = world.observer_view('OP-1')
    assert current_facts(view) == {}
    assert not admit_with_facts(view, 'full', simple_linear())[0]
    assert admit_with_facts(view, 'no_projection', simple_linear())[0]


def test_correcting_from_trusted_facts_resolves_a_scope_conflict():
    case = next(p[1] for p in make_pairs() if p[0]['lane'] == 'scope_conflict')
    world = CatalogWorld(case)
    world.call('read_request', {'request_id': case['request_id']})
    allowed, feedback = admit_with_facts(world.observer_view('OP-1'), 'full', simple_linear())
    assert not allowed
    op = world.call('stage_operation', {'request_id': case['request_id'], 'revision': 2,
        **feedback['current_authenticated_facts']})['operation_id']
    assert admit_with_facts(world.observer_view(op), 'full', simple_linear())[0]
    world.call('commit_operation', {'operation_id': op})
    world.call('close_request', {'request_id': case['request_id'], 'operation_id': op})
    assert world.outcome()['task_completed'] and not world.outcome()['attack_success']
