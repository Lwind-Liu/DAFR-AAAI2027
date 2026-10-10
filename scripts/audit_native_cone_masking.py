"""LP diagnostics for existing cones; witnesses need not be encoder-reachable."""
import json
from pathlib import Path
import sys
import numpy as np
from scipy.optimize import linprog

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'external/official_baselines/AutoDojo/agentdojo/src')]
from clafr import PolicyCompiler, FeatureVector, RuntimeEvidence, RiskBudgetCone, LinearFacet
from clafr.features import FEATURE_NAMES
from agentdojo.agent_pipeline.clafr_defense import AGENTDOJO_POLICY_TEXTS


def main():
    evidence = RuntimeEvidence(policies=AGENTDOJO_POLICY_TEXTS)
    region = PolicyCompiler().compile(evidence.policies, evidence)
    facets = [c for c in region.constraints if isinstance(c, LinearFacet) and not c.soft]
    cones = [c for c in region.constraints if isinstance(c, RiskBudgetCone)]
    names = list(FEATURE_NAMES)
    A = np.array([[f.weights.get(n,0) for n in names] for f in facets])
    b = np.array([f.bound for f in facets])
    rng = np.random.default_rng(20261009)
    reports = {}
    for cone in cones:
        risks = list(cone.risk_weights)
        credit = np.array([cone.credit_weights.get(n,0) for n in names])
        l1 = np.array([cone.risk_weights.get(n,0) for n in names]) - credit
        upper = linprog(-l1, A_ub=A, b_ub=b, bounds=[(0,1)]*len(names), method='highs')
        best, witness = float('-inf'), None
        directions = np.vstack((np.eye(len(risks)), rng.uniform(0,1,(256,len(risks)))))
        for u in directions:
            u /= np.linalg.norm(u)
            score = -credit.copy()
            for key, weight, direction in zip(risks, cone.risk_weights.values(), u):
                score[names.index(key)] += weight * direction
            fit = linprog(-score, A_ub=A, b_ub=b, bounds=[(0,1)]*len(names), method='highs')
            if fit.success:
                vector = FeatureVector.from_mapping(dict(zip(names,fit.x)))
                excess = -cone.margin(vector).slack
                if excess > best:
                    best, witness = excess, vector.as_dict()
        reports[cone.id] = {'l1_excess_upper_bound': float(-upper.fun - cone.bound),
                            'best_found_actual_excess': best,
                            'global_redundancy_proved_by_l1_bound': bool(-upper.fun <= cone.bound + 1e-9),
                            'linear_feasible_cone_violation_found': best > 1e-8,
                            'abstract_witness': witness if best > 1e-8 else None}
    out = ROOT / 'results/summaries/native_semantic_probe_v1'
    out.mkdir(parents=True,exist_ok=True)
    report = {'scope':'All native coordinates relaxed independently to [0,1]. Positive witnesses do not establish encoder reachability; negative direction searches do not prove redundancy.', 'cones':reports}
    (out/'lp_masking.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:{n:v for n,v in r.items() if n!='abstract_witness'} for k,r in reports.items()},indent=2))


if __name__ == '__main__':
    main()
