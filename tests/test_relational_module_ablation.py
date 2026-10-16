from copy import deepcopy

from relational_dafr.business_world import AgentWorld, build_cases
from relational_dafr.module_ablation import context, guard
from relational_dafr.controller import surface_risk


def world():
    case = build_cases(1)[0]
    case['scene']['events'] = {k: {'probability': .95} for k in case['scene']['events']}
    case['scene']['budget'] = .1
    w = AgentWorld(case)
    w.read('read_record', {})
    w.read('read_policy', {})
    w.preflight_attempted = True
    return w


def test_unbound_evidence_does_not_change_paths_but_loses_field_scope():
    w = world()
    field = w.case['fields'][0]
    w.read('verify_field', {'field': field, 'value': w.case['desired'][field]})
    full = context(w, w.case['desired'], 'full_surface')
    removed = context(w, w.case['desired'], 'no_lifting')
    assert full['paths'] == removed['paths'] == w.case['scene']['paths']
    assert full['events'] == removed['events']
    assert surface_risk(full) > .1
    assert surface_risk(removed) == 0
    assert not guard(w, w.case['desired'], 'full_surface', None)[0]
    assert guard(w, w.case['desired'], 'no_lifting', None)[0]


def test_scope_checks_remain_identical_for_all_component_variants():
    w = world()
    args = deepcopy(w.case['desired'])
    args[w.case['fields'][0]] = 'unrequested-value'
    for arm in ('full_surface', 'no_lifting', 'no_geometry', 'no_projection', 'no_feedback'):
        allowed, detail = guard(w, args, arm, None)
        assert not allowed and detail['reason'] == 'outside_user_scope'


def test_feedback_omission_preserves_verification_and_retry_opportunity():
    w = world()
    allowed, detail = guard(w, w.case['desired'], 'no_feedback', None)
    assert not allowed and 'verification_targets' not in detail
    for field, value in w.case['desired'].items():
        assert w.read('verify_field', {'field': field, 'value': value})['verified']
    assert guard(w, w.case['desired'], 'no_feedback', None)[0]


def test_targeted_feedback_is_a_valid_minimum_verification_set():
    w = world()
    # First path is harmless; only the second field requires verification.
    w.case['scene']['events'] = {'e0': {'probability': 1},
        'e1': {'probability': .01}, 'e2': {'probability': .9}}
    w.case['scene']['paths'] = [{'field': w.case['fields'][0], 'events': ['e0', 'e1']},
        {'field': w.case['fields'][1], 'events': ['e0', 'e2']}]
    allowed, detail = guard(w, w.case['desired'], 'full_surface', None)
    assert not allowed and detail['verification_targets'] == [w.case['fields'][1]]
    field = detail['verification_targets'][0]
    w.read('verify_field', {'field': field, 'value': w.case['desired'][field]})
    assert guard(w, w.case['desired'], 'full_surface', None)[0]
