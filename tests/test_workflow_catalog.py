"""Pair integrity and independent business scoring in the final catalog."""
from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_workflow_catalog import CatalogWorld, make_pairs, capacity_check
from run_targeted_payment_case import simple_linear
from workflow_benchmark.defense import admit


def test_all_pairs_have_same_business_state_goal_and_risk_inputs():
    pairs = make_pairs()
    assert len(pairs) == 100
    assert len({p[0]['group_id'] for p in pairs}) == 100
    for clean, attacked in pairs:
        for key in ('task', 'expected', 'risk_metadata', 'records', 'registry_failures'):
            assert clean[key] == attacked[key]
        wc, wa = CatalogWorld(clean), CatalogWorld(attacked)
        assert wc.business_state == wa.business_state
        assert wc.effects == wa.effects == []


def test_curved_region_has_a_true_affine_midpoint_counterexample():
    result = capacity_check(make_pairs())
    assert result['feature_midpoint_identity']
    assert all(r < result['budget'] for r in result['endpoint_risks'])
    assert result['midpoint_risk'] > result['budget']


def test_scope_removal_changes_real_wrong_execution_not_the_metric_definition():
    case = next(p[1] for p in make_pairs() if p[0]['lane'] == 'scope_conflict')
    world = CatalogWorld(case)
    world.call('read_request', {'request_id': case['request_id']})
    view = world.observer_view('OP-1')
    assert not admit(view, 'full', simple_linear())[0]
    assert not admit(view, 'linear', simple_linear())[0]
    assert admit(view, 'no_lifting', simple_linear())[0]
    world.call('commit_operation', {'operation_id': 'OP-1'})
    world.call('close_request', {'request_id': case['request_id'], 'operation_id': 'OP-1'})
    assert not world.outcome()['task_completed']
    assert world.outcome()['attack_success']


def test_business_outcomes_are_independent_of_declared_risk_probabilities():
    case = next(p[1] for p in make_pairs() if p[0]['lane'] == 'joint_risk')
    outcomes = []
    for probability in (0., 1.):
        changed = deepcopy(case)
        for event in changed['risk_metadata']['events'].values():
            event['probability'] = probability
        world = CatalogWorld(changed)
        world.call('commit_operation', {'operation_id': 'OP-1'})
        world.call('close_request', {'request_id': changed['request_id'], 'operation_id': 'OP-1'})
        outcomes.append(world.outcome())
    assert outcomes[0] == outcomes[1]
    assert outcomes[0]['attack_success'] and not outcomes[0]['task_completed']
