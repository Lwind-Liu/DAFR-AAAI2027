from copy import deepcopy
import pytest
from heterogeneous_benchmark.fixtures import build_cases
from heterogeneous_benchmark.world import NativeWorld, TOOLS
from heterogeneous_benchmark.guard import decide
from heterogeneous_benchmark.evaluation import attacker_goal_achieved


def case(family,variant='clean'):
    return next(c for c in build_cases() if c['family']==family and c['variant']==variant)


def test_bad_payment_is_executable_but_evaluator_detects_it():
    c=case('invoice');w=NativeWorld(c)
    action=c['attacker_action']
    assert 'error' not in w.call(action['tool'],action['arguments'])
    assert w.outcome()['unsafe_state'] and not w.outcome()['task_completed']


def test_verification_available_without_prior_rejection():
    w=NativeWorld(case('invoice'))
    assert 'error' not in w.call('verify_vendor',{'vendor_id':'VENDOR-3'})
    assert w.receipts


def test_failed_native_action_rolls_back_state():
    w=NativeWorld(case('return'));before=deepcopy(w.state)
    assert 'error' in w.call('restock_item',{'return_id':'RET-8'})
    assert w.state==before


def test_original_document_not_modified_by_redaction():
    w=NativeWorld(case('report'));original=deepcopy(w.state['documents']['DOC-1'])
    result=w.call('redact_document',{'document_id':'DOC-1'})
    assert w.state['documents']['DOC-1']==original
    assert all(not p['confidential'] for p in w.state['documents'][result['document_id']]['sections'])


def test_forged_approval_not_authentic_and_ablation_differs():
    c=case('invoice','attack_forged');w=NativeWorld(c)
    w.call('read_invoice',{'invoice_id':'INV-17'})
    assert not w.receipts and w.claims
    bad=c['attacker_action'];contract=TOOLS[bad['tool']]
    assert not decide(contract,bad['tool'],bad['arguments'],w.receipts,w.claims,'full')[0]
    assert decide(contract,bad['tool'],bad['arguments'],w.receipts,w.claims,'no_projection')[0]


def test_binding_cannot_reuse_approval_for_another_argument():
    c=case('invoice');w=NativeWorld(c)
    w.call('verify_vendor',{'vendor_id':'VENDOR-3'});w.call('get_purchase_order',{'order_id':'PO-9'})
    bad=c['attacker_action'];contract=TOOLS[bad['tool']]
    assert not decide(contract,bad['tool'],bad['arguments'],w.receipts,w.claims,'full')[0]
    assert decide(contract,bad['tool'],bad['arguments'],w.receipts,w.claims,'no_lifting')[0]


def test_recovery_requires_restorable_snapshot():
    w=NativeWorld(case('recovery'))
    w.call('list_deployments',{});w.call('read_runbook',{'incident_id':'INCIDENT-6'})
    assert 'error' in w.call('rollback_release',{'incident_id':'INCIDENT-6','environment':'production','version':'v4'})
    assert w.state['active_version']=='v5'


def test_attacks_do_not_change_initial_world_or_user_task():
    cases=build_cases()
    for clean in [c for c in cases if c['variant']=='clean']:
        for attacked in [c for c in cases if c['task_id']==clean['task_id']]:
            assert clean['initial_state']==attacked['initial_state']
            assert clean['task']==attacked['task'] and clean['tools']==attacked['tools']


def test_goals_cannot_be_satisfied_without_execution():
    assert all(not NativeWorld(c).outcome()['task_completed'] for c in build_cases())


def test_wrong_amount_is_not_automatically_the_redirect_attack_goal():
    w=NativeWorld(case('invoice'))
    w.call('pay_invoice',{'invoice_id':'INV-17','account':'acct-supplier','amount':400,'currency':'CNY'})
    assert w.outcome()['unsafe_state']
    assert not attacker_goal_achieved('invoice',w.state)


def test_specific_attacker_goal_detected():
    c=case('invoice');w=NativeWorld(c);bad=c['attacker_action']
    w.call(bad['tool'],bad['arguments'])
    assert attacker_goal_achieved('invoice',w.state)
