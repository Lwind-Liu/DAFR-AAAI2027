"""Minimal causal interaction diagnostic, not a benchmark or hardware model.

100 equally weighted potential execution worlds; source manipulation controls
whether an instruction is unauthorized, financial scope controls its loss.
Safety is an explicitly declared expected-unauthorized-loss budget, not a
label produced by an algorithm. This diagnostic isolates convexity only.
"""
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def execute_worlds(manipulated_worlds, amount):
    losses = [amount if i < manipulated_worlds else 0.0 for i in range(100)]
    return sum(losses) / len(losses)


def main():
    budget = .15
    inputs = [('source_high_effect_low',90,.1), ('source_low_effect_high',10,.9),
              ('both_moderate',50,.5)]
    cases = [{'name':name,'source_probability':n/100,'financial_effect':amount,
              'expected_unauthorized_loss':execute_worlds(n,amount),
              'safe':execute_worlds(n,amount)<=budget}
             for name,n,amount in inputs]
    a,b,c = cases
    assert a['safe'] and b['safe'] and not c['safe']
    assert (a['source_probability']+b['source_probability'])/2 == c['source_probability']
    assert (a['financial_effect']+b['financial_effect'])/2 == c['financial_effect']
    matrix = np.array([[0,.5],[.5,0]])
    report = {'scope':'Minimal declared causal expected-loss model. It is not empirical phishing risk estimation or a full DAFR dataset.',
              'budget':budget,'cases':cases,'product_quadratic_eigenvalues':np.linalg.eigvalsh(matrix).tolist(),
              'conclusion':'The raw two-coordinate safe set is nonconvex: two safe endpoints have an unsafe midpoint. Any single convex feasible region, including an intersection of halfspaces or standard PSD second-order-cone constraints, that includes both endpoints must also include this midpoint.',
              'implication':'A convex curve alone cannot express all conjunctive joint-risk semantics. Conditional policy regions, disjunctions, or nonlinear relational lifting may be required. If lifting supplies a product to all baselines, a linear threshold on that feature can implement this toy policy exactly; geometry must be evaluated for an additional benefit.',
              'alternative':'Other independent safety laws can yield convex curved feasible sets. This three-case diagnosis does not prove all joint-risk policies nonconvex, nor rule out benefits from dynamic geometry.'}
    out=ROOT/'results/summaries/joint_mail_bank_witness_v1'
    out.mkdir(parents=True,exist_ok=True)
    (out/'causal_convexity_diagnosis.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
