"""Render measured supplemental pilot results and recorded inference usage."""
import csv
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/summaries/catalog_supplemental_pilot_v1'
plt.rcParams.update({'font.family': 'Times New Roman', 'pdf.fonttype': 42})


def save(fig, name):
    fig.tight_layout()
    for suffix in ('pdf', 'png'):
        fig.savefig(OUT / (name + '.' + suffix), dpi=180, bbox_inches='tight')
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cost = list(csv.DictReader((ROOT / 'results/summaries/catalog_inference_cost_v1/inference_cost.csv').open(encoding='utf-8-sig')))
    fig, ax = plt.subplots(figsize=(11, 3.5))
    ax.axis('off')
    cells = [[r['Method'], f"{float(r['Mean input_tokens']):,.0f}", f"{float(r['Mean output_tokens']):,.0f}",
              f"{float(r['Mean llm_calls']):.2f}", f"{float(r['Mean tool_calls']):.2f}"] for r in cost]
    table = ax.table(cellText=cells, colLabels=['Method', 'Input Tokens', 'Output Tokens', 'LLM Calls', 'Tool Calls'],
                     cellLoc='right', bbox=[0, .15, 1, .8])
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
    ax.text(0, .05, 'Means per episode over 104 clean + 104 attacked tasks per method. Includes planner and defense LLM calls.\nLocal detector compute is outside the token metric.', transform=ax.transAxes, fontsize=10)
    save(fig, 'inference_cost')

    folder = ROOT / 'results/summaries/catalog_dynamic_pilot_v1'
    summary = json.loads((folder / 'summary.json').read_text())
    audit = json.loads((folder / 'audit.json').read_text())
    assert summary['complete'] and audit == {'replayed_episodes': 64, 'errors': 0, 'complete': True}
    protocol = json.loads((folder / 'protocol.json').read_text())
    rows = [json.loads(line) for line in (folder / 'rows.jsonl').read_text().splitlines()]
    extras = []
    for mode in ('dynamic', 'static'):
        selected = [r for r in rows if r['arm'] == mode]
        usages = [t['usage'] for r in selected for t in r['trace'] if isinstance(t.get('usage'), dict)]
        extras.append({'configuration': mode, 'episodes': len(selected),
            'mean_input_tokens': sum(u['prompt_tokens'] for u in usages) / len(selected),
            'mean_output_tokens': sum(u['completion_tokens'] for u in usages) / len(selected),
            'mean_llm_calls': sum(r['llm_calls'] for r in selected) / len(selected),
            'mean_tool_calls': sum(r['tool_calls'] for r in selected) / len(selected),
            'mean_elapsed_seconds': statistics.mean(r['elapsed_seconds'] for r in selected)})
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.7))
    for mode, color in [('dynamic', '#3558d4'), ('static', '#de7b59')]:
        groups = [r for r in summary['length_groups'] if r['Configuration'] == mode]
        xs = [r['Reference tool steps'] for r in groups]
        label = 'DAFR (dynamic joint-risk updates)' if mode == 'dynamic' else 'DAFR (fixed initial joint-risk constraints)'
        for ax, metric in zip(axes, ('UA', 'ASR')):
            ax.plot(xs, [r[metric] for r in groups], marker='o', color=color, label=label)
            ax.set_xticks(xs, [f"{r['Reference tool steps']}\n(n={r['attack_n']})" for r in groups])
            ax.set_xlabel('Clean reference workflow tool steps')
            ax.set_ylabel(metric + ' (%)')
            ax.set_ylim(-3, 103)
            ax.grid(alpha=.2)
    axes[0].legend(fontsize=8, loc='best')
    fig.suptitle('16-pair pilot, 12-turn budget; reference steps include verification and retries', fontsize=11)
    save(fig, 'dynamic_trajectory_pilot')
    manifest = {'status': 'Complete small-batch pilot; 16 paired tasks, not a full-104 dynamic experiment.',
        'comparison': summary['rows'], 'length_groups': summary['length_groups'], 'pilot_overhead': extras,
        'static_definition': protocol['static_definition'], 'length_definition': protocol['length_definition'],
        'cost_population': 'Existing fixed-104 six-method comparison, 208 episodes per method.',
        'cost_results': cost,
        'interpretation': 'Length groups use a pre-execution reference procedure, including verification and retries. They do not isolate multi-action chain length as a causal variable.'}
    probe = ROOT / 'results/summaries/catalog_long_budget_probe_v1'
    if (probe / 'summary.json').exists():
        diagnosis = json.loads((probe / 'summary.json').read_text())
        assert diagnosis['complete']
        assert json.loads((probe / 'audit.json').read_text()) == {'replayed_episodes': 8, 'errors': 0, 'complete': True}
        manifest['long_workflow_24_turn_probe'] = diagnosis['rows']
        fig, axes = plt.subplots(2, 1, figsize=(10, 4.5))
        for ax, data, title in zip(axes, (summary['rows'], diagnosis['rows']),
                ('16 paired tasks, matched 12-turn budget', 'Two long paired tasks, matched 24-turn budget (separate diagnosis)')):
            ax.axis('off')
            ax.set_title(title, fontsize=11, loc='left')
            cells = [[r['Configuration'], f"{r['CU']:.1f}", f"{r['UA']:.1f}", f"{r['ASR']:.1f}", str(r['total_tool_calls'])] for r in data]
            table = ax.table(cellText=cells, colLabels=['Configuration', 'CU (%)', 'UA (%)', 'ASR (%)', 'Total Tool Calls'],
                             cellLoc='right', bbox=[0, .12, 1, .75])
            table.auto_set_font_size(False)
            table.set_fontsize(12)
            for (i, j), cell in table.get_celld().items():
                cell.set_edgecolor('white')
                if j == 0:
                    cell.set_text_props(ha='left')
                if i == 0:
                    cell.set_text_props(weight='bold')
                if i == 1:
                    cell.set_facecolor('#e5e5e5')
        save(fig, 'dynamic_mechanism_pilot')
    (OUT / 'report.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
