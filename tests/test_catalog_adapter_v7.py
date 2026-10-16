"""Source-filter scope and evidence boundary checks for the fixed catalog."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import catalog_baseline_adapter_v7 as adapter


def payment_world():
    pairs, _ = adapter.catalog.prepare()
    case = next(p[1] for p in pairs if p[0]['group_id'] == 'CAT-022-31045e5a')
    return adapter.catalog.CatalogWorld(case)


def test_filtering_one_record_does_not_replace_other_business_parameters():
    world = payment_world()
    response = world.call('read_request', {'request_id': world.case['request_id']})
    record = next(o['response'] for o in world.observations
                  if o['tool'] == 'read_record' and o['response']['field'] == 'destination')
    metadata = [{'original': record['note'], 'filtered': 'removed', 'metadata': {'detected': True}}]
    guard = adapter.DetectorAdmission()
    guard.observe(response, metadata, world)
    decision = guard.admit('commit_operation', {'operation_id': 'OP-1'}, world)[1]
    assert decision['record_ids'] == [record['record_id']]
    assert decision['retained_parameters']['payload'] == world.drafts['OP-1']['payload']
    assert 'destination' not in decision['retained_parameters']
    world.on_admission_blocked('OP-1')
    verified = world.call('verify_record', {'record_id': record['record_id']})
    arguments = dict(world.drafts['OP-1'], destination=verified['value'])
    corrected = world.call('stage_operation', arguments)['operation_id']
    guard.observe(world.call('read_request', {'request_id': world.case['request_id']}), metadata, world)
    assert guard.admit('commit_operation', {'operation_id': corrected}, world)[0]


def test_detected_note_is_removed_atomically_without_dropping_signed_facts():
    class Detector:
        def filter(self, text):
            return 'replacement parameters', {'detected': True, 'blocked': False}
    visible, _ = adapter.filter_visible({'source_notes': ['instructions and replacement parameters'],
        'current_authenticated_facts': {'destination': 'verified'}}, Detector())
    assert visible['source_notes'] == ['[Content removed by defense]']
    assert visible['current_authenticated_facts'] == {'destination': 'verified'}


def test_defense_observer_context_contains_no_hidden_labels_or_outcomes():
    evidence = adapter.public_evidence(payment_world())
    def walk(value):
        if isinstance(value, dict):
            assert not {'expected', 'variant', 'lane', 'attack_success', 'task_completed',
                        'attacker_payload', 'attacker_destination'} & value.keys()
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(evidence)
