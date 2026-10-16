from copy import deepcopy
from itertools import product

import pytest

from relational_dafr.agent_world import AgentWorld, build_cases
from relational_dafr.controller import surface_risk
from relational_dafr.worlds import expected_loss


def test_surface_matches_independent_worlds_for_shared_paths_and_verification():
    for case in build_cases(3):
        for mask in range(4):
            world = AgentWorld(case)
            world.preflight_attempted = True
            for i, field in enumerate(case['fields']):
                if mask & (1 << i):
                    world.read('verify_field', {'field': field, 'value': case['desired'][field]})
            context = world.context(case['desired'])
            assert surface_risk(context) == pytest.approx(expected_loss(context), abs=1e-12)


def test_external_grants_do_not_authorize_runtime_effects():
    case = build_cases(2)[1]
    case['scene']['events'] = {f'e{i}': {'probability': .95} for i in range(3)}
    world = AgentWorld(case)
    world.read('read_record', {})
    assert not world.context(case['desired'])['grants']
    assert world.context(case['desired'], projection=False)['grants']
    world.execute(case['desired'])
    assert world.outcome()['unsafe_commit']


def test_registry_rejects_wrong_values_and_success_requires_state_mutation():
    case = build_cases(1)[0]
    world = AgentWorld(case)
    assert not world.outcome()['task_completed']
    assert world.read('verify_field', {'field': case['fields'][0], 'value': case['desired'][case['fields'][0]]})['error'] == 'preflight_required'
    world.preflight_attempted = True
    assert not world.read('verify_field', {'field': case['fields'][0], 'value': 'attacker'})['verified']
    for field, value in case['desired'].items():
        assert world.read('verify_field', {'field': field, 'value': value})['verified']
    world.execute(case['desired'])
    assert world.outcome()['safe_success']


def test_domain_state_transitions_and_held_out_topologies():
    from relational_dafr.business_world import AgentWorld as BusinessWorld, build_cases as business_cases
    train, test = business_cases(4, split='train'), business_cases(4, split='test')
    assert {c['graph_family'] for c in train} == {'shared_source', 'shared_chain'}
    assert {c['graph_family'] for c in test} == {'shared_source', 'shared_chain', 'disjoint_sources', 'overlapping_sources'}
    for case in test:
        world = BusinessWorld(case)
        assert not world.outcome()['task_completed']
        assert world.read('read_policy', {})['requested_arguments'] == case['desired']
        world.preflight_attempted = True
        for field, value in case['desired'].items():
            world.read('verify_field', {'field': field, 'value': value})
        world.execute(case['desired'])
        assert world.outcome()['safe_success']
        assert world.state != case['initial_state']


def test_fully_verified_linear_baseline_has_shared_clear_path_rule():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('flash_runner', Path(__file__).parents[1] / 'scripts/run_flash_agent_geometry.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case = build_cases(1)[0]
    world = AgentWorld(case)
    world.read('read_policy', {})
    world.preflight_attempted = True
    for field, value in case['desired'].items():
        world.read('verify_field', {'field': field, 'value': value})
    bad_model = {'weights': [0] * 32, 'bias': 100., 'threshold': 0.}
    assert module.guard(world, case['desired'], 'simple_linear', bad_model)[0]
