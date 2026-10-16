from relational_dafr.operational_failures import AgentWorld, build_cases
from relational_dafr.whole_region_ablation import guard


def ready(case):
    w = AgentWorld(case)
    w.read('read_record', {})
    w.read('read_policy', {})
    w.preflight_attempted = True
    return w


def test_outage_cannot_create_trusted_evidence_and_temporary_failure_recovers():
    c = next(c for c in build_cases() if c['operational_scenario'] == 'transient_outage')
    w = ready(c)
    field = c['fields'][0]
    args = {'field': field, 'value': c['desired'][field]}
    assert w.read('verify_field', args)['error'] == 'service_unavailable'
    assert not w.grants
    assert w.read('verify_field', args)['verified']
    assert w.verifications == 2


def test_unavailable_field_remains_unverified_and_other_field_can_be_verified():
    c = next(c for c in build_cases() if c['operational_scenario'] == 'field_unavailable')
    w = ready(c)
    blocked = c['verification_service']['unavailable_field']
    assert not w.read('verify_field', {'field': blocked, 'value': c['desired'][blocked]})['verified']
    other = next(f for f in c['fields'] if f != blocked)
    assert w.read('verify_field', {'field': other, 'value': c['desired'][other]})['verified']
    assert all(g['field'] != blocked for g in w.grants)


def test_retry_pressure_uses_shared_budget_and_preserves_business_state_before_commit():
    c = next(c for c in build_cases() if c['operational_scenario'] == 'retry_pressure')
    w = ready(c)
    field = c['fields'][0]
    for _ in range(3):
        assert w.read('verify_field', {'field': field, 'value': c['desired'][field]})['error'] == 'service_unavailable'
    assert w.read('verify_field', {'field': field, 'value': c['desired'][field]})['verified']
    assert w.read('verify_field', {'field': field, 'value': c['desired'][field]})['error'] == 'verification_budget_exhausted'
    assert not w.effects and w.state == c['initial_state']


def test_scenarios_are_balanced_without_changing_business_risk_inputs():
    from collections import Counter
    from relational_dafr.business_world import build_cases as business_cases
    cases = build_cases()
    assert Counter(c['operational_scenario'] for c in cases) == {
        'available': 6, 'transient_outage': 6, 'field_unavailable': 6, 'retry_pressure': 6}
    original = business_cases(4, 20261026, 'test')
    for c, before in zip(cases, original):
        assert c['scene'] == before['scene']
        assert c['desired'] == before['desired'] and c['initial_state'] == before['initial_state']
