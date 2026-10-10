from copy import deepcopy

from geometry_capacity.paper_pipeline import build,run,project,lift,evaluate_world


def test_full_matches_world_and_preserves_episode():
    for e in build(groups=6):
        before=deepcopy(e)
        result=run(e)
        assert result['initial_allowed']==evaluate_world(e,e['input']['action']['arguments'])['safe']
        assert not result['unsafe_admission']
        assert e==before
        assert all(0<=v<=1 for t in result['trace'] for v in t['features'].values())


def test_untrusted_target_cannot_gain_trusted_task_support():
    for e in build(groups=6):
        if e['evidence_variant']=='injected_target':
            result=run(e)
            assert not result['admitted']
            assert 'task_support' in result['trace'][0]['violated']


def test_projection_fallback_keeps_observations_and_known_targets():
    for e in build(groups=6):
        evidence=project(e['input'],False)
        assert evidence['record']==project(e['input'])['record']
        if e['evidence_variant']=='known_target':
            assert run(e,projection=False)==run(e)
        elif e['evidence_variant']=='lookup_target':
            assert 'critical_grounding' in run(e,projection=False)['trace'][0]['violated']


def test_feedback_ablation_preserves_initial_decisions():
    differences=0
    for e in build(groups=6):
        full,off=run(e),run(e,feedback=False)
        assert full['initial_allowed']==off['initial_allowed']
        assert off['revision_checks']==0
        differences+=full['success'] and not off['success']
    assert differences>0


def test_geometry_ablation_removes_all_geometric_filters():
    violations=0
    for e in build(groups=6):
        result=run(e,geometry=False)
        assert result['initial_allowed'] and result['admitted']
        assert result['trace'][0]['minimum_margin'] is None
        violations+=result['unsafe_admission']
    assert violations>0


def test_six_channel_adapter_exactly_matches_independent_simulator():
    for e in build(groups=6,channels=6):
        result=run(e)
        assert result['initial_allowed']==evaluate_world(e,e['input']['action']['arguments'])['safe']
        assert not result['unsafe_admission']
        assert len(result['trace'][0]['features'])==10
