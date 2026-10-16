"""Native isolation must also invalidate values cached before filtering."""
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import catalog_baseline_adapter_v11 as adapter
from agentdojo.agent_pipeline.drift_defense.drift_llm import DRIFTLLM


def test_native_removed_source_quarantines_only_its_unverified_draft_field():
    pairs, _ = adapter.catalog.prepare()
    case = next(p[1] for p in pairs if p[0]['group_id'] == 'CAT-022-31045e5a')
    world = adapter.catalog.CatalogWorld(case)
    response = world.call('read_request', {'request_id': case['request_id']})
    record = next(o['response'] for o in world.observations
                  if o['tool']=='read_record' and o['response']['field']=='destination')
    core = object.__new__(DRIFTLLM)
    core.logger = logging.getLogger(__name__)
    bridge = SimpleNamespace(audit_events=[])
    adapter.install_drift_source_quarantine(core, bridge, world)
    content = adapter.drift_observation_content(response)
    assert record['note'] in content
    messages = [{'role':'tool', 'content':content}]
    openai = [{'role':'tool', 'content':content}]
    detected = '<detected_instructions>'+repr([record['note']])+'</detected_instructions>'
    core.injection_isolate(detected, messages, openai)
    assert record['note'] not in messages[-1]['content']
    allowed, reason = bridge.draft_filter.admit('commit_operation', {'operation_id':'OP-1'}, world)
    assert not allowed
    assert reason['record_ids'] == [record['record_id']]
    assert reason['retained_parameters']['payload'] == world.drafts['OP-1']['payload']
    assert bridge.audit_events[0]['kind']=='native_isolation_source_quarantine'


def test_empty_native_detection_does_not_quarantine_or_invent_a_block():
    core=object.__new__(DRIFTLLM)
    core.logger=logging.getLogger(__name__)
    bridge=SimpleNamespace(audit_events=[])
    world=SimpleNamespace(observations=[])
    adapter.install_drift_source_quarantine(core,bridge,world)
    content=adapter.drift_observation_content({'source_notes':['ordinary note'],'prepared_operations':{}})
    messages=[{'role':'tool','content':content}]
    core.injection_isolate('<detected_instructions>[]</detected_instructions>',messages,[dict(messages[0])])
    assert bridge.draft_filter.admit('commit_operation',{'operation_id':'OP-1'},world)==(True,None)
    assert not bridge.audit_events


def test_observer_context_does_not_reintroduce_raw_external_notes(monkeypatch):
    monkeypatch.setattr(adapter,'public_evidence',lambda world: {'observations':[
        {'note':'removed instruction','value':'actual proposed value','receipt':{'field':'destination'}}]})
    assert adapter.drift_evidence(None)=={'observations':[
        {'value':'actual proposed value','receipt':{'field':'destination'}}]}
