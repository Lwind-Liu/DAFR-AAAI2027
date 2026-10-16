from copy import deepcopy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from workflow_benchmark.scenarios import build_pairs, SPLITS
from workflow_benchmark.world import WorkflowWorld
from workflow_benchmark.defense import admit, representation, coordinates
from workflow_benchmark.evaluation import summarize

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_workflow_benchmark import reference_run


@pytest.mark.parametrize('domain', ('payment', 'email', 'documents', 'calendar', 'crm', 'cloud'))
def test_every_condition_is_solvable_with_tool_returned_authoritative_values(domain):
    for c in build_pairs('unit', 8, 991):
        if c['domain'] == domain:
            w = reference_run(c)
            assert w.calls <= 32
            assert w.business_state != w.initial_business_state()
            assert w.outcome()['task_completed']


def test_pairs_share_every_input_except_external_attack_and_split_groups_are_disjoint():
    all_groups = []
    for split, args in SPLITS.items():
        cases = build_pairs(split, *args)
        for clean, attacked in zip(cases[::2], cases[1::2]):
            assert {k: v for k, v in clean.items() if k not in ('id', 'variant')} == {
                k: v for k, v in attacked.items() if k not in ('id', 'variant')}
            wc, wa = WorkflowWorld(clean), WorkflowWorld(attacked)
            assert wc.business_state == wa.business_state
        groups = {c['group_id'] for c in cases}
        assert all(not groups & previous for previous in all_groups)
        all_groups.append(groups)


def staged_attack(case):
    w = WorkflowWorld(case)
    policy = w.call('read_request', {'request_id': case['request_id']})
    args = {}
    for rid in policy['records']:
        r = w.call('read_record', {'record_id': rid})
        args[r['field']] = r['value']
    # This helper only uses standard cases with stable revisions.
    op = w.call('stage_operation', {'request_id': case['request_id'], **args, 'revision': policy['revision']})['operation_id']
    return w, op


def test_attack_requires_committed_effect_and_reconciliation_is_required_for_user_success():
    cases = [c for c in build_pairs('unit', 4, 881) if c['variant'] == 'attack' and c['condition'] == 'standard']
    for case in cases:
        w, op = staged_attack(case)
        assert not w.outcome()['attack_success']
        assert not w.outcome()['task_completed']
        result = w.call('commit_operation', {'operation_id': op})
        assert result['status'] == 'committed'
        assert w.outcome()['attack_success']
        w.call('close_request', {'request_id': case['request_id'], 'operation_id': op})
        assert not w.outcome()['task_completed']


def test_risk_numbers_never_determine_business_outcomes():
    c = next(c for c in build_pairs('unit', 1, 441) if c['variant'] == 'clean')
    first = reference_run(c).outcome()
    changed = deepcopy(c)
    changed['risk_metadata']['budget'] = 0
    for event in changed['risk_metadata']['events'].values():
        event['probability'] = 1
    assert reference_run(changed).outcome() == first


def test_projection_and_binding_have_distinct_switches():
    c = next(c for c in build_pairs('unit', 4, 777) if c['attack_kind'] == 'forged_approval'
             and c['variant'] == 'attack' and c['condition'] == 'standard')
    c['risk_metadata']['severity'] = 1
    for event in c['risk_metadata']['events'].values():
        event['probability'] = .9
    w, op = staged_attack(c)
    destination_record = next(k for k, r in c['records'].items() if r['field'] == 'destination')
    w.call('verify_record', {'record_id': destination_record})
    view = w.observer_view(op)
    assert not admit(view, 'full')[0]
    assert admit(view, 'no_projection')[0]
    assert admit(view, 'no_lifting')[0]
    assert admit(view, 'no_geometry')[0]
    # A hidden oracle/case object is not present in the defense interface.
    assert set(view) == {'draft', 'policy', 'observations', 'authenticated_receipts'}
    assert 'expected' not in json.dumps(view)


def test_runtime_conflicts_idempotency_and_final_state_preservation():
    c = next(c for c in build_pairs('unit', 4, 441) if c['condition'] == 'revision_change' and c['variant'] == 'clean')
    w, op = staged_attack(c)
    assert w.call('commit_operation', {'operation_id': op})['error'] == 'revision_conflict'
    assert not w.effects
    safe = reference_run(c)
    op = safe.closed
    before = deepcopy(safe.business_state)
    assert safe.call('commit_operation', {'operation_id': op})['status'] == 'already_committed'
    assert safe.business_state == before and len(safe.effects) == 1
    safe.unrelated['sentinel'] = 'modified'
    assert not safe.outcome()['task_completed']


def test_linear_replaces_entire_region_and_metrics_use_correct_denominators():
    c = build_pairs('unit', 1, 199)[0]
    w = WorkflowWorld(c)
    op = w.call('stage_operation', {'request_id': c['request_id'], **c['expected'], 'revision': 1})['operation_id']
    view = w.observer_view(op)
    model = {'weights': np.zeros(len(coordinates(view))), 'bias': -1, 'threshold': 0}
    assert not admit(view, 'full')[0]
    assert admit(view, 'linear', model)[0]
    cases = build_pairs('unit', 1, 199)[:2]
    rows = [{'id': c['id'], 'variant': c['variant'], 'domain': c['domain'], 'arm': 'full',
             'task_completed': c['variant'] == 'clean', 'attack_success': c['variant'] == 'attack',
             'tool_calls': 9, 'llm_calls': 10, 'registry_calls': 2, 'termination': 'model_finished'} for c in cases]
    result = summarize(rows, cases)['full']
    assert (result['CU'], result['UA'], result['ASR'], result['total_llm_calls']) == (100, 0, 100, 20)
    assert result['paired_utility_drop_count'] == 1
