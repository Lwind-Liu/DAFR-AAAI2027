"""Descriptive per-anchor regression results; no replacement main-test claim."""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/summaries/flash_failure_neighbors_v1'


def main():
    rows = [json.loads(line) for line in (OUT / 'rows.jsonl').read_text().splitlines()]
    protocol = json.loads((OUT / 'frozen_protocol.json').read_text())
    summary = json.loads((OUT / 'summary.json').read_text())['arms']
    anchors = sorted({r['ancestor_id'] for r in rows})
    assert len(rows) == 7 * 4 * len(protocol['arms'])
    result = {}
    for anchor in anchors:
        selected = [r for r in rows if r['ancestor_id'] == anchor]
        result[anchor] = {'domain': selected[0]['domain'], 'graph_family': selected[0]['graph_family']}
        for arm in protocol['arms']:
            arm_rows = [r for r in selected if r['arm'] == arm]
            assert len(arm_rows) == 4
            result[anchor][arm] = {'cases': 4, 'safe_successes': sum(r['safe_success'] for r in arm_rows),
                                 'unsafe_commits': sum(r['unsafe_commit'] for r in arm_rows),
                                 'mean_verifications': float(np.mean([r['verification_queries'] for r in arm_rows]))}
    payload = {'targeted_known_failure_regression': True, 'anchors': result,
               'aggregate': summary, 'not_representative_main_test': True}
    (OUT / 'neighbor_analysis.json').write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    lines = ['# Known-failure neighbor regression', '',
             'Seven previously observed linear-failure anchors; four retained new neighbors each.',
             'Same frozen affine model and threshold. Not an independently sampled main-test result.', '',
             '| Arm | Safe success | Unsafe commits | Mean verification |',
             '|---|---:|---:|---:|']
    for arm, s in summary.items():
        lines.append(f"| {arm} | {s['safe_successes']}/{s['cases']} ({100*s['safe_successes']/s['cases']:.1f}%) | {s['unsafe_commits']} | {s['mean_verifications']:.3f} |")
    lines += ['', '| Ancestor | Domain | Surface safe success | Linear safe success |', '|---|---|---:|---:|']
    for anchor, s in result.items():
        lines.append(f"| {anchor} | {s['domain']} | {s['full_surface']['safe_successes']}/4 | {s['simple_linear']['safe_successes']}/4 |")
    (OUT / 'final_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(payload))


if __name__ == '__main__':
    main()
