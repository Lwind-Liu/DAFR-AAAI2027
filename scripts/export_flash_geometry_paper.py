"""Export paired metrics, breakdowns and a paper section from retained traces."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LABELS = {'full_surface': 'Full upgraded DAFR', 'simple_linear': 'Simple linear rule',
          'no_projection': 'w/o Evidence Projection', 'no_lifting': 'w/o Action--Evidence Lifting',
          'no_geometry': 'w/o Geometric Constraints', 'no_feedback': 'w/o Decision and Feedback'}


def export(output):
    summary = json.loads((output / 'summary.json').read_text())
    rows = [json.loads(line) for line in (output / 'rows.jsonl').read_text().splitlines()]
    protocol = json.loads((output / 'frozen_protocol.json').read_text())
    arms = protocol['arms']
    indexed = {(r['id'], r['arm']): r for r in rows}
    ids = sorted({r['id'] for r in rows})
    assert len(rows) == len(ids) * len(arms)
    assert all((i, a) in indexed for i in ids for a in arms)
    rng = np.random.default_rng(20261022)
    draws = rng.integers(0, len(ids), (10000, len(ids)))
    paired = {}
    for arm in arms[1:]:
        values = np.array([
            [int(indexed[i, 'full_surface']['safe_success']) - int(indexed[i, arm]['safe_success']),
             indexed[i, arm]['verification_queries'] - indexed[i, 'full_surface']['verification_queries'],
             int(indexed[i, arm]['first_decision']['false_block']) - int(indexed[i, 'full_surface']['first_decision']['false_block'])]
            for i in ids])
        boot = values[draws].mean(axis=1)
        paired[arm] = {metric: {'estimate': float(values[:, j].mean()),
                               'paired_95pct': np.quantile(boot[:, j], [.025, .975]).tolist()}
                       for j, metric in enumerate(('safe_success_gain', 'verification_queries_saved', 'false_block_rate_reduction'))}
    breakdown = {}
    for key in ('domain', 'graph_family', 'variant'):
        if any(key not in r for r in rows):
            continue
        breakdown[key] = {}
        for value in sorted({r[key] for r in rows}):
            breakdown[key][value] = {}
            for arm in arms:
                selected = [r for r in rows if r[key] == value and r['arm'] == arm]
                breakdown[key][value][arm] = {
                    'cases': len(selected), 'safe_successes': sum(r['safe_success'] for r in selected),
                    'unsafe_commits': sum(r['unsafe_commit'] for r in selected),
                    'mean_verifications': float(np.mean([r['verification_queries'] for r in selected]))}
    (output / 'paired_metrics.json').write_text(json.dumps(paired, indent=2) + '\n', encoding='utf-8')
    (output / 'breakdowns.json').write_text(json.dumps(breakdown, indent=2) + '\n', encoding='utf-8')
    table_rows = []
    for arm in arms:
        s = summary['arms'][arm]
        table_rows.append({'arm': arm, 'cases': s['cases'], 'safe_success_pct': 100 * s['safe_successes'] / s['cases'],
                          'unsafe_commits': s['unsafe_commits'], 'initial_false_blocks': s['initial_false_blocks'],
                          'mean_verifications': s['mean_verifications']})
    with (output / 'paper_table.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(table_rows[0]))
        writer.writeheader()
        writer.writerows(table_rows)
    def table(selected, caption, label):
        lines = [r'\begin{table}[t]', r'\centering', r'\small', r'\setlength{\tabcolsep}{3pt}',
                 r'\begin{tabular}{lrrrr}', r'\toprule',
                 r'Configuration & S-TSR $\uparrow$ & UC $\downarrow$ & FB $\downarrow$ & VQ $\downarrow$ \\',
                 r'\midrule']
        for arm in selected:
            r = next(r for r in table_rows if r['arm'] == arm)
            lines.append(f"{LABELS[arm]} & {r['safe_success_pct']:.1f} & {r['unsafe_commits']} & {r['initial_false_blocks']} & {r['mean_verifications']:.2f}" + r' \\')
        return '\n'.join(lines + [r'\bottomrule', r'\end{tabular}', r'\caption{' + caption + '}',
                                 r'\label{' + label + '}', r'\end{table}'])
    comparison = table(arms[:2], 'Flash tool-agent comparison. S-TSR: safe task success (percent); UC: unsafe commits; FB: first-preflight false blocks; VQ: mean independent verification queries.', 'tab:flash-geometry-comparison')
    ablation = table([arms[0], *arms[2:]], 'Module ablations under the same model, tools, preflight lifecycle and query budget.', 'tab:flash-geometry-ablation')
    (output / 'comparison_table.tex').write_text(comparison + '\n', encoding='utf-8')
    (output / 'ablation_table.tex').write_text(ablation + '\n', encoding='utf-8')
    full, linear = summary['arms']['full_surface'], summary['arms']['simple_linear']
    query_ci = paired['simple_linear']['verification_queries_saved']['paired_95pct']
    success_ci = paired['simple_linear']['safe_success_gain']['paired_95pct']
    saved = 100 * (1 - full['mean_verifications'] / linear['mean_verifications']) if linear['mean_verifications'] else 0
    lines = ['# Final Flash business tool-agent results', '',
             f"Frozen test: {len(ids)} tasks, {len(rows)} paired method runs, six business domains.", '',
             '| Configuration | Safe task success | Unsafe commits | First-preflight false blocks | Mean verification queries |',
             '|---|---:|---:|---:|---:|']
    for r in table_rows:
        lines.append(f"| {r['arm']} | {r['safe_success_pct']:.1f}% | {r['unsafe_commits']} | {r['initial_false_blocks']} | {r['mean_verifications']:.3f} |")
    lines += ['', f"Safe-success gain over linear: {100*paired['simple_linear']['safe_success_gain']['estimate']:.2f} percentage points; paired 95% CI [{100*success_ci[0]:.2f}, {100*success_ci[1]:.2f}].",
              f"Verification queries saved: {paired['simple_linear']['verification_queries_saved']['estimate']:.3f} per task ({saved:.1f}%); paired 95% CI [{query_ci[0]:.3f}, {query_ci[1]:.3f}].", '',
              'Lifting removal can preserve final success through extra verification. Its contribution is measured by false blocks and query burden, rather than asserting that every ablation lowers success.', '',
              'Real LLM calls in synthetic stateful environments with declared uncertainty and causal paths. This does not validate production probability estimation, real service execution, or the original benchmark NLP encoder. Historical benchmark numbers are unchanged.', '',
              'The simpler first test and all pilots are retained separately; they are not pooled with this frozen test.']
    (output / 'final_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    body = (ROOT / 'paper/supplement/DAFR_Flash_Agent_Geometry_Template.tex').read_text(encoding='utf-8')
    substitutions = {
        '@@COMPARISON@@': comparison, '@@ABLATION@@': ablation,
        '@@FULL@@': str(full['safe_successes']), '@@LINEAR@@': str(linear['safe_successes']),
        '@@N@@': str(len(ids)), '@@FULL_UNSAFE@@': str(full['unsafe_commits']),
        '@@LINEAR_UNSAFE@@': str(linear['unsafe_commits']), '@@SAVED@@': f'{saved:.1f}',
        '@@QUERY_DELTA@@': f"{paired['simple_linear']['verification_queries_saved']['estimate']:.3f}",
        '@@QUERY_LO@@': f'{query_ci[0]:.3f}', '@@QUERY_HI@@': f'{query_ci[1]:.3f}',
        '@@SUCCESS_DELTA@@': f"{100*paired['simple_linear']['safe_success_gain']['estimate']:.2f}",
        '@@SUCCESS_LO@@': f'{100*success_ci[0]:.2f}', '@@SUCCESS_HI@@': f'{100*success_ci[1]:.2f}',
        '@@UNSEEN_UNSAFE@@': str(sum(r['unsafe_commit'] for r in rows
                                    if r['arm'] == 'simple_linear' and r.get('graph_family') in
                                    ('disjoint_sources', 'overlapping_sources')))}
    for key, value in substitutions.items():
        body = body.replace(key, value)
    assert '@@' not in body
    target = ROOT / 'paper/supplement/DAFR_Flash_Agent_Geometry_Experiment.tex'
    target.write_text(body, encoding='utf-8')
    print(json.dumps({'output': str(output), 'paper': str(target), 'paired': paired['simple_linear']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', nargs='?', default='results/summaries/flash_business_geometry_test_v1')
    export(ROOT / parser.parse_args().output)
