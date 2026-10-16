import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_catalog_dynamic_pilot as pilot


def make_world():
    cases = [json.loads(line) for line in (ROOT / 'data/workflow_catalog_104/cases.jsonl').read_text().splitlines()]
    case = next(c for c in cases if c['variant'] == 'clean' and c['lane'] == 'joint_risk')
    world = pilot.catalog.CatalogWorld(case)
    world.call('read_request', {'request_id': case['request_id']})
    return case, world


def test_static_freezes_paths_but_uses_new_evidence_and_common_feedback():
    case, world = make_world()
    static = pilot.JointRiskGuard('static')
    dynamic = pilot.JointRiskGuard('dynamic')
    view = world.observer_view('OP-1')
    assert static(view) == dynamic(view)
    assert not static(view)[0]
    world.on_admission_blocked('OP-1')
    for rid in case['records']:
        world.call('verify_record', {'record_id': rid})
    view = world.observer_view('OP-1')
    assert dynamic(view)[0]
    allowed, feedback = static(view)
    assert not allowed
    assert feedback['current_authenticated_facts'] == case['expected']
    assert static.decisions[-1]['dynamic_risk'] == 0
    assert static.decisions[-1]['static_risk'] > case['risk_metadata']['budget']


def test_static_does_not_remove_current_halfspace_checks():
    case, world = make_world()
    view = world.observer_view('OP-1')
    # Initial authorization removes risk paths in both methods.
    world.on_admission_blocked('OP-1')
    for rid in case['records']:
        world.call('verify_record', {'record_id': rid})
    view = world.observer_view('OP-1')
    guard = pilot.JointRiskGuard('static')
    assert guard(view)[0]
    view['draft']['revision'] = 999
    assert not guard(view)[0]
    assert guard.decisions[-1]['frozen_paths'] == 0
