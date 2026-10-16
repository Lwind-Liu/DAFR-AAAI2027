"""Fresh offline comparison on the frozen jianghao mechanism datasets.

The affine baseline is trained and calibrated on separate seeded samples.
No task-level CU/UA/ASR is inferred from these action/vector measurements.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression


ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('privacy_egress', 'financial_risk', 'state_write_risk', 'scope_risk')


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def write_rows(path, rows):
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')


def confusion(allow, safe):
    allow, safe = np.asarray(allow, dtype=bool), np.asarray(safe, dtype=bool)
    values = {
        'safe_allow': int(np.sum(allow & safe)),
        'false_block': int(np.sum(~allow & safe)),
        'unsafe_block': int(np.sum(~allow & ~safe)),
        'false_allow': int(np.sum(allow & ~safe)),
        'cases': len(safe),
    }
    values['accuracy'] = (values['safe_allow'] + values['unsafe_block']) / len(safe)
    values['unsafe_false_allow_rate'] = values['false_allow'] / int(np.sum(~safe))
    values['safe_false_block_rate'] = values['false_block'] / int(np.sum(safe))
    return values


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--branch-dir', type=Path, required=True)
    p.add_argument('--output-dir', type=Path,
                   default=ROOT / 'results/summaries/jianghao_geometry_rules_audit_20261012')
    args = p.parse_args()
    branch, out = args.branch_dir.resolve(), args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(branch / 'src'))
    bench = module(branch / 'scripts/run_geometry_repair_benchmark_v1.py', 'jianghao_repair_bench')
    bench.RNG = random.Random(bench.SEED)
    joint, joint_summary = bench.run_joint_suite()
    repair, repair_summary = bench.run_action_repair_suite()
    safe = np.array([sum(r[k] ** 2 for k in FIELDS) <= 1.0 for r in joint])
    comparisons = {name: confusion([r[name + '_allow'] for r in joint], safe)
                   for name in ('axis_ifelse', 'geometry')}

    # Independent same-distribution samples; the frozen 512 rows are never
    # used for fitting, calibration, method selection, or threshold selection.
    bench.RNG = random.Random(2026101201)
    train, _ = bench.run_joint_suite(8192)
    bench.RNG = random.Random(2026101202)
    dev, _ = bench.run_joint_suite(4096)
    def xy(rows):
        x = np.array([[r[k] for k in FIELDS] for r in rows])
        return x, (np.sum(x * x, axis=1) > 1.0).astype(int)
    xt, yt = xy(train)
    xd, yd = xy(dev)
    fitted = LogisticRegression(C=1e6, class_weight='balanced', max_iter=2000,
                                solver='lbfgs', random_state=20261012).fit(xt, yt)
    scores = fitted.decision_function(xd)
    distinct = np.unique(scores)
    thresholds = np.concatenate(([distinct[0] - 1], (distinct[:-1] + distinct[1:]) / 2,
                                 [distinct[-1] + 1]))
    candidates = []
    for t in thresholds:
        false_allow = np.mean(scores[yd == 1] <= t)
        false_block = np.mean(scores[yd == 0] > t)
        candidates.append(((false_allow + false_block) / 2, false_allow, false_block, float(t)))
    selected = min(candidates)
    threshold = selected[-1]
    x_test, _ = xy(joint)
    test_scores = fitted.decision_function(x_test)
    linear_allow = test_scores <= threshold
    comparisons['single_affine_rule'] = confusion(linear_allow, safe)
    for i, row in enumerate(joint):
        row.update(policy_safe=bool(safe[i]), single_affine_allow=bool(linear_allow[i]),
                   single_affine_score=float(test_scores[i]))
    frozen = [json.loads(s) for s in (branch / 'results/summaries/geometry_repair_benchmark_v1/joint_rows.jsonl').read_text(encoding='utf-8').splitlines()]
    keys = (*FIELDS, 'axis_ifelse_allow', 'geometry_allow', 'equivalent_predicate_allow')
    mismatches = sum(any(a[k] != b[k] for k in keys) for a, b in zip(joint, frozen))
    assert len(joint) == len(frozen) and mismatches == 0
    assert joint_summary['geometry_predicate_disagreements'] == 0
    assert comparisons['geometry']['false_allow'] == comparisons['geometry']['false_block'] == 0
    assert repair_summary['geometry_predicate_block_disagreements'] == 0

    # Reevaluate the frozen small pilot with branch runtime code.
    from clafr.geometry import FeasibleRegion, RiskBudgetCone
    from clafr.schemas import FeatureVector
    small = [json.loads(s) for s in (branch / 'results/summaries/geometry_joint_risk_pilot_v1/rows.jsonl').read_text(encoding='utf-8').splitlines()]
    region = FeasibleRegion((RiskBudgetCone(id='audit-small',
        risk_weights={'privacy_egress': 1., 'financial_risk': 1.}, credit_weights={}, bound=1.,
        description='Frozen two-dimensional unit risk budget', repair_hint='Reduce joint risk'),))
    for r in small:
        allow = region.feasible(FeatureVector.from_mapping({k: r[k] for k in FIELDS[:2]}))
        assert allow == r['geometry_allow']
        assert r['axis_ifelse_allow'] == all(r[k] <= .8 for k in FIELDS[:2])

    boundary = module(branch / 'scripts/run_agentdojo_geometry_boundary_replay.py', 'jianghao_boundary')
    boundary.OUT = out / 'agentdojo_boundary_replay'
    with contextlib.redirect_stdout(io.StringIO()):
        boundary.main()
    boundary_summary = json.loads((boundary.OUT / 'summary.json').read_text(encoding='utf-8'))
    isolation = module(branch / 'scripts/geometry_isolation_ifelse_ablation.py', 'jianghao_isolation')
    with contextlib.redirect_stdout(io.StringIO()):
        isolation_results = isolation.run(out / 'shape_isolation')
    linear_model = {
        'input_fields': FIELDS, 'weights': fitted.coef_[0].tolist(),
        'bias': float(fitted.intercept_[0]), 'threshold': threshold,
        'train_cases': len(train), 'dev_cases': len(dev),
        'train_seed': 2026101201, 'dev_seed': 2026101202,
        'calibration': 'minimize mean of unsafe false-allow and safe false-block rates on dev only',
        'dev_balanced_error': selected[0],
        'test_scope': 'original branch 512 test vectors, unchanged',
    }
    source_files = ['scripts/run_geometry_repair_benchmark_v1.py',
                    'scripts/run_agentdojo_geometry_boundary_replay.py',
                    'scripts/geometry_isolation_ifelse_ablation.py',
                    'src/clafr/geometry.py', 'src/clafr/selector.py',
                    'results/summaries/geometry_repair_benchmark_v1/joint_rows.jsonl']
    report = {
        'branch': 'jianghao', 'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=branch, text=True).strip(),
        'scope': 'Offline mechanism rerun; 0 LLM/API calls. Not CU/UA/ASR or a new end-to-end agent evaluation.',
        'policy_labels': 'Declared unit L2 budget, checked independently as sum of squared coordinates <= 1.',
        'joint_cases': len(joint), 'policy_safe_cases': int(np.sum(safe)),
        'policy_unsafe_cases': int(np.sum(~safe)), 'joint_comparisons': comparisons,
        'joint_frozen_row_mismatches': mismatches,
        'small_pilot': {'cases': len(small), 'axis_allow': sum(r['axis_ifelse_allow'] for r in small),
                        'geometry_allow': sum(r['geometry_allow'] for r in small),
                        'decision_differences': sum(r['axis_ifelse_allow'] != r['geometry_allow'] for r in small)},
        'action_repair': repair_summary, 'agentdojo_boundary_replay': boundary_summary,
        'shape_isolation': {'case_count': isolation_results['case_count'],
                            'label_counts': isolation_results['label_counts'],
                            'blocks': isolation_results['blocks']},
        'single_affine_model': linear_model,
        'source_hashes': {f: hashlib.sha256((branch / f).read_bytes()).hexdigest() for f in source_files},
    }
    write_rows(out / 'joint_rows.jsonl', joint)
    write_rows(out / 'repair_rows.jsonl', repair)
    write_json(out / 'summary.json', report)
    write_json(out / 'single_affine_model.json', linear_model)
    print(json.dumps({'commit': report['commit'], 'joint_comparisons': comparisons,
                      'small_pilot': report['small_pilot'],
                      'repair_success': repair_summary['geometry_repair_success']['successes'],
                      'boundary_calls': boundary_summary['valid_rows'], 'output': str(out)}, indent=2))


if __name__ == '__main__':
    main()
