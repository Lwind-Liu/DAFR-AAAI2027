"""Render the controlled chain study and the isolated timing pilot."""
import csv
import json
from pathlib import Path
import statistics
import shutil
import hashlib

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import export_catalog_baseline_comparison as comparison

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/summaries/catalog_supplemental_v2'
plt.rcParams.update({'font.family': 'Times New Roman', 'pdf.fonttype': 42})


def save(fig, name):
    fig.tight_layout(rect=[0, .08, 1, 1])
    for extension in ('pdf', 'png'):
        fig.savefig(OUT / (name + '.' + extension), bbox_inches='tight', dpi=180)
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    chains = ROOT / 'results/summaries/catalog_action_chains_v2'
    summary = json.loads((chains / 'summary.json').read_text())
    audit = json.loads((chains / 'audit.json').read_text())
    assert summary['complete'] and audit == {'replayed_episodes': 72, 'errors': 0, 'complete': True}
    rows = [json.loads(line) for line in (chains / 'rows.jsonl').read_text().splitlines()]
    aggregates = [{'configuration': mode, **comparison.metrics([r for r in rows if r['arm'] == mode])}
                  for mode in ('dynamic', 'static')]
    comparison.write_csv(OUT / 'dynamic_overall.csv', aggregates)
    comparison.write_csv(OUT / 'trajectory_scaling.csv', summary['rows'])
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    offsets = np.arange(3)
    for mode, shift, color, label in [('dynamic', -.18, '#3558d4', 'DAFR: dynamic joint-risk updates'),
                                      ('static', .18, '#de7b59', 'DAFR: fixed initial joint-risk constraints')]:
        aggregate = next(r for r in aggregates if r['configuration'] == mode)
        values = [aggregate[k] for k in ('CU', 'UA', 'ASR')]
        bars = axes[0].bar(offsets + shift, values, width=.36, color=color, label=label)
        axes[0].bar_label(bars, fmt='%.1f', padding=3, fontsize=9)
        group = [r for r in summary['rows'] if r['configuration'] == mode]
        axes[1].plot([r['length'] for r in group], [r['UA'] for r in group], marker='o', color=color, label=label)
        for r in group:
            axes[1].annotate(f"{r['UA']:.1f}", (r['length'], r['UA']), xytext=(0, 6 if mode == 'dynamic' else -14),
                             textcoords='offset points', ha='center', fontsize=9)
    axes[0].set_xticks(offsets, ['CU', 'UA', 'ASR'])
    axes[0].set_title('(a) Dynamic mechanism comparison')
    axes[1].set_title('(b) Ordered business-operation chains')
    axes[1].set_xticks([1, 2, 4])
    axes[1].set_xlabel('Number of committed and reconciled business operations')
    for ax in axes:
        ax.set_ylim(-3, 112)
        ax.set_ylabel('Score (%)' if ax == axes[0] else 'Attack Utility (%)')
        ax.grid(axis='y', alpha=.2)
        ax.set_axisbelow(True)
    axes[0].legend(fontsize=8, loc='upper right')
    fig.text(.03, .02, 'Six domain families per length; 72 executions. Same 48-turn / 48-tool-call budget. One attack per attacked chain.', fontsize=10)
    save(fig, 'dynamic_and_trajectory')
    manifest = {'chain_status': 'complete six-family controlled study', 'chain_episodes': 72,
        'overall': aggregates, 'length_groups': summary['rows'],
        'length_definition': 'Distinct ordered business operations, each physically committed and reconciled; later operations require prior closure.',
        'static_scope': 'Fixed initial joint-risk constraints per request; evidence, lifting, halfspaces and feedback stay active.',
        'samples': 'Six clean and six attacked chains per length per configuration. Families repeat across lengths.',
        'budget': '48 model turns and 48 tool calls for every configuration and length.',
        'chain_audit': audit,
        'chain_source': str(chains.relative_to(ROOT))}

    cost = ROOT / 'results/summaries/catalog_inference_cost_v1'
    cost_figure = ROOT / 'results/summaries/catalog_supplemental_pilot_v1'
    shutil.copy2(cost / 'inference_cost.csv', OUT / 'inference_cost.csv')
    for extension in ('pdf', 'png'):
        shutil.copy2(cost_figure / ('inference_cost.' + extension), OUT / ('inference_cost.' + extension))
    manifest['inference_usage'] = json.loads((cost / 'protocol.json').read_text())
    manifest['inference_usage']['source'] = str(cost.relative_to(ROOT))

    latency = ROOT / 'results/summaries/catalog_latency_pilot_v2'
    if (latency / 'summary.json').exists():
        timing = json.loads((latency / 'summary.json').read_text())
        assert timing['complete']
        assert json.loads((latency / 'audit.json').read_text()) == {'replayed_episodes': 24, 'errors': 0, 'complete': True}
        comparison.write_csv(OUT / 'latency.csv', timing['rows'])
        fig, ax = plt.subplots(figsize=(10, 3.5))
        ax.axis('off')
        cells = [[r['Method'], f"{r['Mean seconds']:.2f} ± {r['Std seconds']:.2f}",
                  f"{r['Median seconds']:.2f}", f"{r['Mean LLM calls']:.2f}", str(r['Episodes'])] for r in timing['rows']]
        table = ax.table(cellText=cells, colLabels=['Method', 'Mean ± SD (s)', 'Median (s)', 'LLM Calls', 'Episodes'],
                         cellLoc='right', bbox=[0, .22, 1, .72])
        table.auto_set_font_size(False)
        table.set_fontsize(12)
        for (i, j), cell in table.get_celld().items():
            cell.set_edgecolor('white')
            if j == 0:
                cell.set_text_props(ha='left')
            if i == 0:
                cell.set_text_props(weight='bold')
            if i == 6:
                cell.set_facecolor('#e5e5e5')
        ax.text(0, .1, 'Matched sequential pilot: two paired tasks, four executions per method. Includes agent, defense and tools.\nModel loading and local detector warm-up excluded; measured after the chain experiment finished.', transform=ax.transAxes, fontsize=10)
        save(fig, 'matched_latency')
        manifest['timing_status'] = 'Small matched sequential timing pilot; four episodes per method.'
        manifest['timing_results'] = timing['rows']
        manifest['timing_source'] = str(latency.relative_to(ROOT))
        manifest['timing_audit'] = json.loads((latency / 'audit.json').read_text())
        import fitz
        combined = fitz.open()
        for name in ('dynamic_and_trajectory', 'inference_cost', 'matched_latency'):
            with fitz.open(OUT / (name + '.pdf')) as source:
                combined.insert_pdf(source)
        combined.save(OUT / 'DAFR_Dynamics_Trajectory_Cost_Preview.pdf')
        combined.close()
        manifest['preview_sha256'] = hashlib.sha256((OUT / 'DAFR_Dynamics_Trajectory_Cost_Preview.pdf').read_bytes()).hexdigest()
    (OUT / 'report.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
