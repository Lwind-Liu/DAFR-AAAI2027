from copy import deepcopy

import numpy as np

from relational_dafr.business_world import AgentWorld, build_cases
from relational_dafr.module_ablation import guard as old_guard
from relational_dafr.whole_region_ablation import coordinates, guard, region_admits


def test_single_affine_replaces_scope_and_policy_checks_without_clear_path_override():
    w = AgentWorld(build_cases(1)[0])
    args = deepcopy(w.case['desired'])
    args[w.case['fields'][0]] = 'outside-task-scope'
    dimension = len(coordinates(w, args))
    permissive = {'weights': np.zeros(dimension), 'bias': -1., 'threshold': 0.}
    assert not region_admits(w, args)
    assert guard(w, args, 'linear_region', permissive)[0]
    assert guard(w, args, 'no_geometric_region', None)[0]
    w.policy_read = True
    for field, value in w.case['desired'].items():
        w.read('verify_field', {'field': field, 'value': value})
    rejecting = {'weights': np.zeros(dimension), 'bias': 1., 'threshold': 0.}
    assert region_admits(w, w.case['desired'])
    assert not guard(w, w.case['desired'], 'linear_region', rejecting)[0]


def test_full_halfspaces_plus_surface_matches_reference_with_partial_evidence():
    for case in build_cases(2):
        for policy_read in (False, True):
            for mask in range(4):
                w = AgentWorld(case)
                w.policy_read = policy_read
                w.preflight_attempted = True
                for i, field in enumerate(case['fields']):
                    if mask & (1 << i):
                        w.read('verify_field', {'field': field, 'value': case['desired'][field]})
                for scope in (True, False):
                    args = deepcopy(case['desired'])
                    if not scope:
                        args[case['fields'][0]] = 'different-value'
                    assert region_admits(w, args) == old_guard(w, args, 'full_surface', None)[0]


def test_runtime_schema_validation_is_shared_even_without_geometry():
    w = AgentWorld(build_cases(1)[0])
    for arm in ('full_surface', 'linear_region', 'no_geometric_region'):
        allowed, detail = guard(w, {}, arm, None)
        assert not allowed and detail['reason'] == 'invalid_schema'
