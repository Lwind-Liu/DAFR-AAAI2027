"""Export the complete fixed-104 comparison, with coverage and replay checks."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METHODS = [('no_defense', 'No Defense'), ('piguard', 'PIGuard'),
           ('protectai', 'ProtectAI'), ('progent', 'Progent'),
           ('drift', 'DRIFT'), ('full', 'DAFR')]
CAPTION = ('Method comparison on 104 paired synthetic tool-agent tasks across six domains '
           'with DeepSeek V4 Flash. Each method uses 104 clean and 104 attacked episodes '
           'with the same tools and execution budgets. CU and UA measure correct task '
           'completion; ASR measures attacker-goal attainment. Total tool calls include '
           'denied submissions.')


def render_preview(result, paper):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import textwrap
    plt.rcParams.update({'font.family': 'Times New Roman', 'pdf.fonttype': 42})
    figure, axis = plt.subplots(figsize=(11.7, 4.2))
    axis.axis('off')
    cells = [[r['label'], *(f"{r[k]:.1f}" for k in ('CU', 'UA', 'ASR')),
              str(r['total_tool_calls'])] for r in result]
    table = axis.table(cellText=cells, colLabels=['Method', r'CU (%) $\uparrow$',
        r'UA (%) $\uparrow$', r'ASR (%) $\downarrow$', 'Total Tool Calls'],
        colWidths=[.30, .16, .16, .16, .22], bbox=[0, .29, 1, .69], cellLoc='right')
    table.auto_set_font_size(False)
    table.set_fontsize(13)
    for (i, j), cell in table.get_celld().items():
        cell.set_edgecolor('white')
        if j == 0:
            cell.set_text_props(ha='left')
        if i == 0:
            cell.set_text_props(weight='bold')
        elif result[i-1]['method'] == 'full':
            cell.set_facecolor('#e5e5e5')
            if j == 0:
                cell.set_text_props(weight='bold')
        if i and j in (1, 2, 3):
            key = ('CU', 'UA', 'ASR')[j-1]
            best = (min if key == 'ASR' else max)(r[key] for r in result)
            if abs(result[i-1][key]-best) < 1e-9:
                cell.set_text_props(weight='bold')
    for y, width in ((.98, 1.5), (.98-.69/7, 1), (.29, 1.5)):
        axis.plot([0, 1], [y, y], transform=axis.transAxes, color='black', lw=width)
    axis.text(0, .235, 'Table 1. ' + '\n'.join(textwrap.wrap(CAPTION, 134)),
        transform=axis.transAxes, fontsize=10.5, va='top', linespacing=1.3)
    figure.subplots_adjust(left=.035, right=.975, top=.97, bottom=.045)
    for extension in ('pdf', 'png'):
        figure.savefig(paper / ('DAFR_Custom_Dataset_Comparison_Preview.' + extension), dpi=160)
    plt.close(figure)


def metrics(rows):
    clean = [r for r in rows if r['variant'] == 'clean']
    attacked = [r for r in rows if r['variant'] == 'attack']
    return {'clean_n': len(clean), 'attack_n': len(attacked),
            'CU': 100 * sum(r['task_completed'] for r in clean) / len(clean),
            'UA': 100 * sum(r['task_completed'] for r in attacked) / len(attacked),
            'ASR': 100 * sum(r['attack_success'] for r in attacked) / len(attacked),
            'total_tool_calls': sum(r['tool_calls'] for r in rows),
            'total_llm_calls': sum(r['llm_calls'] for r in rows)}


def read_complete(folder):
    protocol = json.loads((folder / 'protocol.json').read_text())
    summary = json.loads((folder / 'summary.json').read_text())
    assert protocol['pairs'] == 104 and protocol['episodes'] == 1248
    assert summary['complete'], 'Full 104-pair comparison is still incomplete.'
    audit = json.loads((folder / 'audit.json').read_text())
    assert audit == {'replayed_episodes': 1248, 'errors': 0, 'complete': True}
    dataset = ROOT / 'data/workflow_catalog_104/cases.jsonl'
    assert hashlib.sha256(dataset.read_bytes()).hexdigest() == protocol['data_sha256']
    rows = [json.loads(line) for line in (folder / 'rows.jsonl').read_text().splitlines()]
    ids = set(protocol['ids'])
    expected = {(case_id, method) for case_id in ids for method, _ in METHODS}
    assert len(ids) == 208 and len(rows) == len(expected) == 1248
    assert {(r['id'], r['arm']) for r in rows} == expected
    assert all(r['termination'] not in ('infrastructure_error', 'api_error', 'budget_exhausted') for r in rows)
    result = []
    for method, label in METHODS:
        values = metrics([r for r in rows if r['arm'] == method])
        assert values['clean_n'] == values['attack_n'] == 104
        reported = next(r for r in summary['rows'] if r['method'] == method)
        assert all(abs(values[k] - reported[k]) < 1e-9 for k in values)
        result.append({'method': method, 'label': label, **values})
    return rows, result, protocol


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def export(folder, paper=False):
    rows, result, protocol = read_complete(folder)
    write_csv(folder / 'main_table.csv', [{'Method': r['label'], 'CU (%)': round(r['CU'], 1),
        'UA (%)': round(r['UA'], 1), 'ASR (%)': round(r['ASR'], 1),
        'Total Tool Calls': r['total_tool_calls']} for r in result])
    domains = sorted({r['domain'] for r in rows})
    assert len(domains) == 6
    domain_rows = [{'method': method, 'domain': domain,
        **metrics([r for r in rows if r['arm'] == method and r['domain'] == domain])}
        for method, _ in METHODS for domain in domains]
    write_csv(folder / 'per_domain.csv', domain_rows)
    full = next(r for r in result if r['method'] == 'full')
    no_defense = result[0]
    comparisons = {r['label']: {'CU_gain': full['CU'] - r['CU'],
        'UA_gain': full['UA'] - r['UA'], 'ASR_reduction': r['ASR'] - full['ASR'],
        'UA_gain_over_No_Defense': r['UA'] - no_defense['UA'],
        'ASR_reduction_vs_No_Defense': no_defense['ASR'] - r['ASR']}
        for r in result[1:-1]}
    manifest = {'complete': True, 'paired_tasks': 104, 'replayed_episodes': 1248,
        'model': protocol['model'], 'data_sha256': protocol['data_sha256'],
        'rows_sha256': hashlib.sha256((folder / 'rows.jsonl').read_bytes()).hexdigest(),
        'aggregation': 'Pooled task counts, matching the frozen 104-task ablation.',
        'DAFR_CU_highest': all(full['CU'] >= r['CU'] for r in result),
        'DAFR_UA_highest': all(full['UA'] >= r['UA'] for r in result),
        'DAFR_ASR_lowest': all(full['ASR'] <= r['ASR'] for r in result),
        'comparisons': comparisons, 'results': result}
    (folder / 'final_comparison.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    if paper:
        lines = [r'\begin{table}[!ht]', r'\centering', r'\small',
            r'\setlength{\tabcolsep}{8pt}', r'\renewcommand{\arraystretch}{1.22}',
            r'\resizebox{\linewidth}{!}{%', r'\begin{tabular}{lrrrr}', r'\toprule',
            r'Method & CU (\%) $\uparrow$ & UA (\%) $\uparrow$ & ASR (\%) $\downarrow$ & Total Tool Calls \\', r'\midrule']
        for r in result:
            if r['method'] == 'full':
                lines.append(r'\rowcolor{black!12}')
                label = r'\textbf{DAFR}'
            else:
                label = r['label']
            numbers = []
            for key in ('CU', 'UA', 'ASR'):
                value = f"{r[key]:.1f}"
                best = (min if key == 'ASR' else max)(v[key] for v in result)
                numbers.append(r'\textbf{' + value + '}' if abs(r[key]-best) < 1e-9 else value)
            lines.append(label + ' & ' + ' & '.join(numbers) + f" & {r['total_tool_calls']} " + r'\\')
        lines.extend([r'\bottomrule', r'\end{tabular}%', '}',
            r'\caption{' + CAPTION + '}',
            r'\label{tab:custom-dataset-comparison}', r'\end{table}'])
        target = ROOT / 'paper/supplement/DAFR_Custom_Dataset_Comparison_Table.tex'
        target.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        render_preview(result, target.parent)
    print(json.dumps(manifest))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=ROOT / 'results/summaries/catalog_fixed104_adapter_v11_104')
    parser.add_argument('--paper', action='store_true')
    args = parser.parse_args()
    export(args.source, args.paper)
