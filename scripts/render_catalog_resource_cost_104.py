"""Render the full-104 token and tool-call table from recorded episode usage."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import export_catalog_baseline_comparison as comparison

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/summaries/catalog_resource_cost_104'
PAPER = ROOT / 'paper/supplement'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'results/summaries/catalog_inference_cost_v1/episode_usage.csv'
    with source.open(encoding='utf-8-sig', newline='') as stream:
        episodes = list(csv.DictReader(stream))
    rows = []
    for method, label in comparison.METHODS:
        selected = [r for r in episodes if r['method'] == method]
        assert len(selected) == 208
        assert len({r['id'] for r in selected}) == 208
        assert all(sum(r['variant'] == variant for r in selected) == 104
                   for variant in ('clean', 'attack'))
        inputs = statistics.mean(int(r['input_tokens']) for r in selected)
        outputs = statistics.mean(int(r['output_tokens']) for r in selected)
        rows.append({'Method': label, 'Episodes': 208, 'Input Tokens': inputs,
                     'Output Tokens': outputs, 'Total Tokens': inputs + outputs,
                     'Tool Calls': statistics.mean(int(r['tool_calls']) for r in selected)})
    comparison.write_csv(OUT / 'resource_cost.csv', rows)
    headers = ['Method', 'Input Tokens', 'Output Tokens', 'Total Tokens', 'Tool Calls']
    cells = [[r['Method']] + [f"{r[k]:,.2f}" for k in headers[1:]] for r in rows]
    plt.rcParams.update({'font.family': 'Times New Roman', 'pdf.fonttype': 42})
    fig, ax = plt.subplots(figsize=(11.8, 3.65))
    ax.axis('off')
    table = ax.table(cellText=cells,
                     colLabels=['Method'] + [h + r' $\downarrow$' for h in headers[1:]],
                     colWidths=[.23, .20, .19, .20, .18], cellLoc='right',
                     bbox=[0, .22, 1, .74])
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    for (i, j), cell in table.get_celld().items():
        cell.set_edgecolor('white')
        cell.PAD = .055
        if j == 0:
            cell.set_text_props(ha='left')
        if i == 0:
            cell.set_text_props(weight='bold')
        if i == len(rows):
            cell.set_facecolor('#e7e7e7')
            if j == 0:
                cell.set_text_props(weight='bold')
    for y, width in ((.96, 1.2), (.22 + .74 * 6 / 7, .8), (.22, 1.2)):
        ax.plot([0, 1], [y, y], color='black', lw=width, transform=ax.transAxes)
    caption = ('Per-episode means on 104 task pairs (104 clean + 104 attacked executions per method).\n'
               'Tokens include agent and defense LLM calls; total tokens = input + output.\n'
               'Tool calls include valid requests blocked by the defense. Values are rounded to two decimal places.')
    ax.text(0, .04, caption, transform=ax.transAxes, fontsize=10, va='bottom')
    fig.tight_layout(pad=.4)
    for extension in ('pdf', 'png'):
        path = OUT / ('DAFR_Custom_Dataset_Cost_Preview.' + extension)
        fig.savefig(path, bbox_inches='tight', dpi=200)
        shutil.copy2(path, PAPER / path.name)
    plt.close(fig)
    body = '\n'.join(' & '.join(cell) + r' \\' for cell in cells)
    # Literal labels/numbers mirror the preview; booktabs provides the rules.
    latex = (r'\begin{table}[t]' + '\n' + r'\centering' + '\n' + r'\small' + '\n'
             + r'\begin{tabular}{lrrrr}' + '\n' + r'\toprule' + '\n'
             + r'Method & Input Tokens $\downarrow$ & Output Tokens $\downarrow$ & Total Tokens $\downarrow$ & Tool Calls $\downarrow$ \\'
             + '\n' + r'\midrule' + '\n' + body + '\n' + r'\bottomrule' + '\n'
             + r'\end{tabular}' + '\n'
             + r'\caption{Resource overhead on the 104-task synthetic dataset. Values are means per episode over 104 clean and 104 attacked executions for each method. Token counts include agent and defense LLM calls; total tokens sum input and output tokens. Tool calls include valid requests blocked by the defense. Values are rounded to two decimal places.}'
             + '\n' + r'\label{tab:synthetic-resource-overhead}' + '\n' + r'\end{table}' + '\n')
    (PAPER / 'DAFR_Custom_Dataset_Cost_Table.tex').write_text(latex, encoding='utf-8')
    preview = (r'\documentclass{article}' + '\n' + r'\usepackage[margin=1in,landscape]{geometry}'
               + '\n' + r'\usepackage{booktabs}' + '\n' + r'\begin{document}' + '\n'
               + latex + r'\end{document}' + '\n')
    (PAPER / 'DAFR_Custom_Dataset_Cost_Preview.tex').write_text(preview, encoding='utf-8')
    (OUT / 'protocol.json').write_text(json.dumps({
        'source': str(source.relative_to(ROOT)),
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'methods': 6, 'task_pairs': 104, 'episodes_per_method': 208,
        'episodes_total': 1248, 'aggregation': 'Mean per episode over clean and attack variants.',
        'total_tokens': 'Mean input tokens + mean output tokens, computed before display rounding.',
        'new_api_calls': 0, 'rows': rows}, indent=2), encoding='utf-8')
    print(json.dumps(rows))


if __name__ == '__main__':
    main()
