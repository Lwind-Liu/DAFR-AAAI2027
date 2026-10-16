"""Protocol changes cannot alter existing risk inputs or business outcomes."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from catalog_protocol_refinement import RefinedCatalogWorld, digest, make_profiles, catalog


def case():
    cases = [json.loads(s) for s in (ROOT / 'data/workflow_catalog_104/cases.jsonl').read_text(encoding='utf-8').splitlines()]
    c = next(c for c in cases if c.get('extension_kind') == 'explicit_parameters' and c['variant'] == 'clean')
    return {**deepcopy(c), 'core_case_sha256': digest(c),
            'protocol_refinement': {'request_sections': 3, 'verification_sections': 2, 'reconciliation_steps': 2}}


def test_read_sections_reassemble_exactly_and_preserve_observer_state():
    c = case()
    w = RefinedCatalogWorld(c)
    old = deepcopy(c)
    old.pop('protocol_refinement'); old.pop('core_case_sha256')
    reference = catalog.CatalogWorld(old)
    args = {'request_id': c['request_id']}
    expected = reference.call('read_request', args)
    response, steps, _ = w.expand_cached_call('read_request', args)
    assert response == expected
    assert len(steps) == 3
    assert w.core.__dict__ == reference.__dict__


def test_incomplete_result_and_wrong_ticket_do_not_allow_execution():
    c = case(); w = RefinedCatalogWorld(c)
    r = w.call('read_request', {'request_id': c['request_id']})
    state = deepcopy(w.core.__dict__)
    assert w.call('commit_operation', {'operation_id': 'OP-1'})['error'] == 'complete_pending_tool_result'
    assert w.call(r['next_tool'], {'ticket': 'another-case'})['error'] == 'invalid_continuation_ticket'
    assert w.core.__dict__ == state
    assert not w.core.effects


def test_reconciliation_finishes_only_after_continuation():
    c = case(); w = RefinedCatalogWorld(c)
    w.expand_cached_call('read_request', {'request_id': c['request_id']})
    w.expand_cached_call('commit_operation', {'operation_id': 'OP-1'})
    assert w.core.effects
    response = w.call('close_request', {'request_id': c['request_id'], 'operation_id': 'OP-1'})
    assert w.core.closed is None
    assert not w.core.outcome()['task_completed']
    w.call(response['next_tool'], {'ticket': response['ticket']})
    assert w.core.outcome()['task_completed']
    assert w.call(response['next_tool'], {'ticket': response['ticket']})['error'] == 'invalid_continuation_ticket'


def test_tampering_risk_metadata_rejected():
    c = case()
    c['risk_metadata']['budget'] = 100
    with pytest.raises(ValueError, match='Core case'):
        RefinedCatalogWorld(c)


def test_profile_assignment_independent_of_variants_and_scores():
    c = case(); c.pop('protocol_refinement'); c.pop('core_case_sha256')
    a = deepcopy(c); a['variant'] = 'attack'; a['task_completed'] = False
    assert make_profiles([c]) == make_profiles([c, a]) == make_profiles([a, c])
