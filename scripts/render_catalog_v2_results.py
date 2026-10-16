"""Render measured, fully audited catalog results; never insert target scores."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/summaries/workflow_catalog_v2'
PAPER = ROOT / 'paper/supplement'
LABELS = ['DAFR', 'w/o Evidence Projection', 'w/o Action--Evidence Lifting',
          'w/o Geometric Modeling', 'w/o Feasibility Constraints']


def main():
    global OUT
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', choices=['workflow_catalog_v2', 'workflow_catalog_104'], default='workflow_catalog_v2')
    args = parser.parse_args()
    OUT = ROOT / 'results/summaries' / args.dataset
    summary = json.loads((OUT / 'summary.json').read_text())
    audit = json.loads((OUT / 'audit.json').read_text())
    n = 104 if args.dataset == 'workflow_catalog_104' else 100
    assert summary['complete'] and summary['completed_episodes'] == n*10
    assert audit == {'replayed_episodes': n*10, 'errors': 0, 'complete': True}
    rows = summary['rows']
    assert all(r['clean_n'] == r['attack_n'] == n for r in rows)
    full = rows[0]
    contribution = {r['arm']: {'CU_gain': full['CU'] - r['CU'],
                              'UA_gain': full['UA'] - r['UA'],
                              'ASR_reduction': r['ASR'] - full['ASR']}
                    for r in rows[1:]}
    gates = {'all_paired_episodes_complete': True, 'all_traces_replayed': True,
             'all_modules_positive': all(all(v > 0 for v in d.values()) for d in contribution.values()),
             'full_CU_80_to_90': 80 <= full['CU'] <= 90,
             'full_UA_at_least_80': full['UA'] >= 80,
             'full_ASR_above_zero': full['ASR'] > 0,
             'geometry_UA_advantage_15_to_25_points': 15 <= full['UA'] - rows[3]['UA'] <= 25}
    (OUT / 'completion_requirements.json').write_text(json.dumps(
        {'gates': gates, 'contribution': contribution}, indent=2) + '\n')
    caption = (f'Component ablations on {n} paired synthetic tool-agent tasks across six domains '
               f'with DeepSeek-v4-flash-0731. Each configuration runs {n} clean and {n} attacked '
               'episodes with identical tools and execution budgets. CU and UA measure correct '
               'task completion on clean and attacked episodes; ASR measures concrete attacker-goal '
               'attainment on attacked episodes. Total tool calls include denied submissions.')
    settings = ('The evidence-projection ablation removes source-based trust differentiation. '
                'The action--evidence-lifting ablation removes exact binding of evidence to action '
                'parameters and scope. The geometric-modeling ablation replaces both halfspaces '
                'and the joint-risk surface with a single affine decision rule over the same '
                'coordinates. The feasibility-constraint ablation disables both execution checks. '
                'Schema validation and common repair feedback are retained across configurations.')
    header = f'% Generated from {args.dataset}/summary.json after {n*10}-episode replay audit.\n' + r'''
\begin{table}[!ht]
\centering
\small
\setlength{\tabcolsep}{8pt}
\renewcommand{\arraystretch}{1.22}
\resizebox{\linewidth}{!}{%
\begin{tabular}{lrrrr}
\toprule
Configuration & CU (\%) $\uparrow$ & UA (\%) $\uparrow$ & ASR (\%) $\downarrow$ & Total Tool Calls \\
\midrule
'''
    lines = []
    for label, row in zip(LABELS, rows):
        label = label.replace('–', '--')
        if label == 'DAFR':
            lines.append(r'\rowcolor{black!12}')
            label = r'\textbf{DAFR}'
        lines.append(f"{label} & {row['CU']:.1f} & {row['UA']:.1f} & {row['ASR']:.1f} & {row['total_tool_calls']} " + r'\\')
    table = header + '\n'.join(lines) + '\n' + r'''\bottomrule
\end{tabular}%
}
\caption{''' + caption + r'''}
\label{tab:custom-dataset-ablation}
\end{table}
'''
    (PAPER / 'DAFR_Custom_Dataset_Ablation_Table.tex').write_text(table, encoding='utf-8')
    preview = r'''\documentclass[10pt]{article}
\usepackage[paperwidth=210mm,paperheight=145mm,margin=12mm]{geometry}
\usepackage{booktabs,graphicx}
\usepackage[table]{xcolor}
\usepackage[T1]{fontenc}
\usepackage{mathptmx}
\usepackage[font=small,labelfont=bf]{caption}
\pagestyle{empty}
\begin{document}
\input{DAFR_Custom_Dataset_Ablation_Table.tex}
\noindent\footnotesize\textit{Ablation settings.} ''' + settings + '\n' + r'\end{document}' + '\n'
    (PAPER / 'DAFR_Custom_Dataset_Ablation_Preview.tex').write_text(preview, encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import textwrap
    plt.rcParams.update({'font.family': 'Times New Roman', 'pdf.fonttype': 42})
    fig, ax = plt.subplots(figsize=(11.7, 5.5))
    ax.axis('off')
    cells = [[label.replace('--', '–'), f"{r['CU']:.1f}", f"{r['UA']:.1f}", f"{r['ASR']:.1f}", str(r['total_tool_calls'])]
             for label, r in zip(LABELS, rows)]
    tab = ax.table(cellText=cells, colLabels=['Configuration', 'CU (%) ↑', 'UA (%) ↑', 'ASR (%) ↓', 'Total Tool Calls'],
                   colWidths=[.46,.12,.12,.12,.18], bbox=[0,.40,1,.58], cellLoc='right')
    tab.auto_set_font_size(False)
    tab.set_fontsize(13)
    for (i,j), cell in tab.get_celld().items():
        cell.set_edgecolor('white')
        if j == 0:
            cell.set_text_props(ha='left')
        if i == 1:
            cell.set_facecolor('#e5e5e5')
            cell.set_text_props(weight='bold')
    for y, width in [(0.98,1.5),(.883,1),(.40,1.5)]:
        ax.plot([0,1],[y,y],transform=ax.transAxes,color='black',lw=width)
    ax.text(0,.355,'Table 1. '+ '\n'.join(textwrap.wrap(caption, 137)),transform=ax.transAxes,
            fontsize=10.5,va='top',linespacing=1.3)
    ax.text(0,.16,'Ablation settings. '+ '\n'.join(textwrap.wrap(settings, 137)),transform=ax.transAxes,
            fontsize=10.5,va='top',linespacing=1.3)
    fig.subplots_adjust(left=.035,right=.975,top=.97,bottom=.045)
    fig.savefig(PAPER / 'DAFR_Custom_Dataset_Ablation_Preview.pdf')
    plt.close(fig)
    print(json.dumps({'gates': gates, 'pdf': str(PAPER / 'DAFR_Custom_Dataset_Ablation_Preview.pdf')}))


if __name__ == '__main__':
    main()
