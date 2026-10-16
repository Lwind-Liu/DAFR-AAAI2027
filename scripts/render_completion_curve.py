"""Empirical completion curves from frozen trajectories; no budget reruns."""
import csv
import hashlib
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from render_geometry_booktabs import wrap_measured

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/summaries/catalog_completion_curve'
DEST = Path('C:/Users/Administrator/Desktop/表/调用次数曲线')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    DEST.mkdir(parents=True, exist_ok=True)
    dataset = ROOT / 'data/workflow_catalog_104/cases.jsonl'
    cases = [json.loads(s) for s in dataset.read_text(encoding='utf-8').splitlines()]
    ids = {c['id'] for c in cases if c['variant'] == 'attack'}
    assert len(ids) == 104
    main_path = ROOT / 'results/summaries/catalog_fixed104_adapter_v11_104/rows.jsonl'
    records = [json.loads(s) for s in main_path.read_text(encoding='utf-8').splitlines()]
    sources = [dataset, main_path]
    for folder in ('workflow_catalog_v2', 'workflow_catalog_104'):
        for p in sorted((ROOT / 'results/summaries' / folder).glob('CAT-*.jsonl')):
            rows = [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines()]
            selected = [r for r in rows if r['arm'] == 'linear' and r['id'] in ids]
            if selected:
                sources.append(p)
                records.extend(selected)
    arms = [('no_defense', 'No Defense', '#999999', '^'),
            ('linear', 'Linear Rules', '#64B5CD', 's'),
            ('full', 'DAFR', '#E87D82', 'o')]
    selected = {arm: [r for r in records if r['arm'] == arm and r['id'] in ids] for arm, *_ in arms}
    for arm, rows in selected.items():
        assert len(rows) == len({r['id'] for r in rows}) == 104
        assert {r['id'] for r in rows} == ids
        for r in rows:
            assert r['termination'] not in ('api_error', 'infrastructure_error', 'budget_exhausted')
            assert r['tool_calls'] == sum(len(t.get('results', [])) for t in r['trace'])
    max_calls = max(r['tool_calls'] for rows in selected.values() for r in rows)
    curve = []
    for k in range(max_calls + 1):
        for arm, label, *_ in arms:
            count = sum(r['task_completed'] and r['tool_calls'] <= k for r in selected[arm])
            curve.append({'tool_calls': k, 'arm': arm, 'method': label, 'completed': count,
                          'total': 104, 'cumulative_UA': 100 * count / 104})
    with (OUT / 'curve.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(curve[0]))
        writer.writeheader(); writer.writerows(curve)
    audit = {'api_requests': 0, 'n_tasks': 104,
             'definition': 'Fraction of all attack episodes that completed the original task and used at most k total recorded tool calls. Includes blocked submissions and verification calls. Empirical distribution of completed trajectories, not reruns under changed budgets; not intrinsic task length.',
             'source_hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
             'episodes': [{'id': r['id'], 'arm': arm, 'task_completed': r['task_completed'], 'tool_calls': r['tool_calls']} for arm, rows in selected.items() for r in rows]}
    (OUT / 'audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    plt.rcParams.update({'font.family': 'Times New Roman', 'font.size': 12, 'pdf.fonttype': 42})
    fig, ax = plt.subplots(figsize=(7.8, 4.6))
    fig.subplots_adjust(left=.12, right=.96, bottom=.17, top=.86)
    for arm, label, color, marker in arms:
        series = [r for r in curve if r['arm'] == arm and r['tool_calls'] >= 2]
        x = [r['tool_calls'] for r in series]
        y = [r['cumulative_UA'] for r in series]
        ax.plot(x, y, drawstyle='steps-post', color=color, marker=marker, markersize=5,
                linewidth=2, label=label, zorder=4 if arm == 'full' else 3)
        offset = {'full': 2.0, 'linear': 2.1, 'no_defense': -5.5}[arm]
        ax.text(max_calls-.05, y[-1]+offset, f'{y[-1]:.1f}%', ha='right', color=color, weight='bold')
    ax.set(xlim=(1.8, max_calls+.3), ylim=(0, 100), xlabel='Tool calls per recorded trajectory (k)',
           ylabel='Cumulative task completion under attack (%)')
    ax.set_xticks(range(2, max_calls+1)); ax.set_yticks(range(0,101,20))
    ax.grid(axis='y', color='#e1e1e1', linewidth=.7)
    ax.spines[['top', 'right']].set_visible(False)
    ax.legend(loc='lower right', frameon=True, edgecolor='#dddddd', fontsize=11)
    ax.set_title('Task completion versus tool calls (104 attacked tasks)', pad=12)
    for ext in ('pdf', 'png'):
        fig.savefig(OUT / ('调用次数曲线.'+ext), dpi=220, bbox_inches='tight', pad_inches=.12)
    caption = ('固定 104 条攻击任务上的累计任务完成曲线。横轴为一次已记录执行的工具调用总数上限 k，'
               '纵轴为成功完成原任务且调用总数不超过 k 的任务数占全部 104 条任务的比例；最终平台值等于 UA。'
               '工具调用计数包含核验与被拦截的提交，不含 LLM 调用。DAFR 在五次调用以内的累计完成率为 49.0%，'
               '到八次调用时升至 76.9%，最终达到 77.9%；线性规则最终为 55.8%。'
               '该图由原始完整轨迹统计，展示任务完成与调用开销的关系，并非改变调用预算后的重跑实验，也不表示任务固有长度。')
    cn = FontProperties(fname='C:/Windows/Fonts/simsun.ttc', size=9)
    fig.text(.08, -.025, wrap_measured(fig, caption, cn, fig.bbox.width*.88),
             fontproperties=cn, va='top', linespacing=1.45)
    fig.savefig(OUT / '调用次数曲线.pdf', bbox_inches='tight', pad_inches=.12)
    fig.savefig(OUT / 'preview.png', dpi=160, bbox_inches='tight', pad_inches=.12)
    plt.close(fig)
    colors = '\n'.join(r'\definecolor{'+arm+'color}{HTML}{'+color.lstrip('#')+'}' for arm, _, color, _ in arms)
    plots = []
    for arm, label, _, marker in arms:
        coords = ' '.join(f"({r['tool_calls']},{r['cumulative_UA']:.8f})" for r in curve if r['arm']==arm and r['tool_calls']>=2)
        mark = {'^':'triangle*', 's':'square*', 'o':'*'}[marker]
        plots.append(r'\addplot+[const plot,thick,color='+arm+r'color,mark='+mark+r'] coordinates {'+coords+'};\n'+r'\addlegendentry{'+label+'}')
    tex = r'''% XeLaTeX; editable vector plot, no external data or image dependency.
\documentclass[UTF8]{ctexart}
\usepackage[a4paper,margin=15mm]{geometry}
\usepackage{fontspec,pgfplots,caption}
\pgfplotsset{compat=1.18}
\setmainfont{Times New Roman}
\pagestyle{empty}
''' + colors + r'''
\begin{document}
\begin{figure}[ht]\centering
\begin{tikzpicture}
\begin{axis}[width=.96\linewidth,height=9cm,xmin=1.8,xmax=12.3,ymin=0,ymax=100,
xtick={2,...,12},ytick={0,20,...,100},ymajorgrids=true,grid style={gray!20},
xlabel={Tool calls per recorded trajectory ($k$)},ylabel={Cumulative task completion under attack (\%)},
title={Task completion versus tool calls (104 attacked tasks)},legend pos=south east]
''' + '\n'.join(plots) + r'''
\end{axis}\end{tikzpicture}
\caption{''' + caption.replace('%', r'\%') + r'''}
\end{figure}\end{document}
'''
    (OUT / '调用次数曲线.tex').write_text(tex, encoding='utf-8')
    for ext in ('pdf','png','tex'):
        shutil.copy2(OUT / ('调用次数曲线.'+ext), DEST / ('调用次数曲线.'+ext))
    print(json.dumps({'n':104, 'max_calls': max_calls, 'destination':str(DEST)}, ensure_ascii=True))


if __name__ == '__main__':
    main()
