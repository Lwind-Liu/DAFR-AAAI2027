from pathlib import Path
import sys

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from compare_joint_risk_versions import cone_control_loss, cone_allowed, replace_joint
from relational_dafr.episodes import build_episodes, EpisodeRuntime
from relational_dafr import pipeline
from relational_dafr.controller import surface_risk


def test_shared_cone_adapter_matches_independent_quadratic_policy_at_upper_state():
    for e in build_episodes(per_domain=8):
        c=pipeline.extract_context(e['input'])
        upper=pipeline.upper_context(c)
        loss=cone_control_loss(upper)
        assert cone_allowed(c,np.ones(4),1.) == (loss<=c['budget']+1e-12)


def test_risk_only_override_restores_pipeline_even_after_exception():
    original=pipeline.allows
    try:
        with replace_joint(lambda c:True):
            assert pipeline.allows is not original
            raise RuntimeError('interrupted experiment')
    except RuntimeError:
        pass
    assert pipeline.allows is original


def test_equivalent_risk_override_preserves_all_execution_records():
    for e in build_episodes(per_domain=8)[:35]:
        baseline=pipeline.run_episode(e['input'],EpisodeRuntime(e))
        with replace_joint(lambda c:surface_risk(pipeline.upper_context(c))<=c['budget']+1e-12):
            counterfactual=pipeline.run_episode(e['input'],EpisodeRuntime(e))
        assert baseline==counterfactual
