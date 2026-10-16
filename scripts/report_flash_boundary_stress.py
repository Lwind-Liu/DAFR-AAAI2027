"""Report every stress stratum without replacing the unchanged main test."""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/summaries/flash_boundary_geometry_test_v1'


def main():
    rows = [json.loads(line) for line in (OUT / 'rows.jsonl').read_text().splitlines()]
    protocol = json.loads((OUT / 'frozen_protocol.json').read_text())
    arms = protocol['arms']
    lookup = {(r['id'], r['arm']): r for r in rows}
    ids = sorted({r['id'] for r in rows})
    assert len(rows) == len(ids) * len(arms)
    breakdown = {}
    for key in ('stress_stratum', 'graph_family', 'domain'):
        breakdown[key] = {}
        for value in sorted({r[key] for r in rows}):
            breakdown[key][value] = {}
            for arm in arms:
                selected = [r for r in rows if r[key] == value and r['arm'] == arm]
                breakdown[key][value][arm] = {
                    'cases': len(selected), 'safe_successes': sum(r['safe_success'] for r in selected),
                    'unsafe_commits': sum(r['unsafe_commit'] for r in selected),
                    'initial_false_blocks': sum(r['first_decision']['false_block'] for r in selected),
                    'mean_verifications': float(np.mean([r['verification_queries'] for r in selected]))}
    rng = np.random.default_rng(20261023)
    draws = rng.integers(0, len(ids), (10000, len(ids)))
    intervals = {}
    for arm in arms[1:]:
        delta = np.array([int(lookup[i, 'full_surface']['safe_success']) - int(lookup[i, arm]['safe_success']) for i in ids])
        queries = np.array([lookup[i, arm]['verification_queries'] - lookup[i, 'full_surface']['verification_queries'] for i in ids])
        intervals[arm] = {'safe_success_gain': float(delta.mean()),
                          'success_paired_95pct': np.quantile(delta[draws].mean(axis=1), [.025, .975]).tolist(),
                          'queries_saved': float(queries.mean()),
                          'queries_paired_95pct': np.quantile(queries[draws].mean(axis=1), [.025, .975]).tolist()}
    composition = {}
    for split in ('train', 'dev', 'test'):
        cases = [json.loads(line) for line in (ROOT / 'data' / OUT.name / f'{split}.jsonl').read_text().splitlines()]
        composition[split] = {}
        for c in cases:
            key = c['graph_family'] + '/' + c['stress_stratum']
            composition[split][key] = composition[split].get(key, 0) + 1
    payload = {'separate_stress_test_not_main_replacement': True, 'breakdowns': breakdown,
               'paired_intervals': intervals, 'split_composition': composition}
    (OUT / 'stress_analysis.json').write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    s = json.loads((OUT / 'summary.json').read_text())['arms']
    lines = ['# Independent follow-up boundary stress results', '',
             '96 new tasks; 75% oracle-boundary cases and 25% broad cases. The previous 144-task main result is unchanged.', '',
             '| Configuration | Safe success | Unsafe commits | Initial false blocks | Mean verification |',
             '|---|---:|---:|---:|---:|']
    for arm in arms:
        a = s[arm]
        lines.append(f"| {arm} | {100*a['safe_successes']/a['cases']:.1f}% | {a['unsafe_commits']} | {a['initial_false_blocks']} | {a['mean_verifications']:.3f} |")
    result = intervals['simple_linear']
    lo, hi = result['success_paired_95pct']
    lines += ['', f"Full-minus-linear safe-success gain: {100*result['safe_success_gain']:.2f} percentage points; paired 95% CI [{100*lo:.2f}, {100*hi:.2f}].", '',
              'All strata and split composition are reported in stress_analysis.json; no sample was selected by an affine prediction or method outcome.',
              'This is an exploratory synthetic boundary stress distribution, not an estimate of production frequencies or a replacement main result.']
    (OUT / 'final_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'arms': s, 'paired_linear': result, 'strata': breakdown['stress_stratum']}))


if __name__ == '__main__':
    main()
