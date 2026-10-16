"""Writer-facing overview of the 104-case tool-protocol refinement.

Report replay-derived statistics explicitly; do not relabel them live results.
"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
from statistics import mean

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

from render_geometry_booktabs import wrap_measured

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/summaries/catalog_protocol_refinement_v1/table'
DEST = Path('C:/Users/Administrator/Desktop/表/数据概览/合成数据')
GROUPS = [('Business', ('payment', 'crm')), ('Office', ('email', 'documents', 'calendar')),
          ('Cloud', ('cloud',)), ('Overall', None)]


def collect():
    data_path = ROOT / 'data/workflow_catalog_104_protocol_v1/cases.jsonl'
    replay_path = ROOT / 'results/summaries/catalog_protocol_refinement_v1/replay_audit.jsonl'
    cases = [json.loads(s) for s in data_path.read_text(encoding='utf-8').splitlines()]
    replays = [json.loads(s) for s in replay_path.read_text(encoding='utf-8').splitlines()]
    clean = {c['id']: c for c in cases if c['variant'] == 'clean'}
    selected = [r for r in replays if r['arm'] == 'full' and r['variant'] == 'clean']
    assert len(clean) == len(selected) == len({r['id'] for r in selected}) == 104
    assert set(clean) == {r['id'] for r in selected}
    stats = []
    for r in selected:
        assert r['outcome_equal']
        assert r['source'] == 'deterministic_expansion_of_recorded_actions_not_live_llm'
        calls = r['expanded_steps']
        assert len(calls) == r['expanded_tool_steps']
        stats.append({'id': r['id'], 'domain': r['domain'],
                      'tool_types': len({c['tool'] for c in calls}),
                      'trajectory': len(calls),
                      'verification': sum(c['tool'] in ('verify_record', 'collect_verification_result') for c in calls)})
    rows = []
    for label, domains in GROUPS:
        subset = [r for r in stats if domains is None or r['domain'] in domains]
        rows.append([label, len(subset), f"{mean(r['tool_types'] for r in subset):.2f}",
                     f"{mean(r['trajectory'] for r in subset):.2f}",
                     f"{min(r['trajectory'] for r in subset)}–{max(r['trajectory'] for r in subset)}",
                     f"{mean(r['verification'] for r in subset):.2f}"])
    return rows, {'source': 'deterministic_replay', 'configuration': 'full DAFR, clean variants',
                  'denominator': 104, 'live_llm_episodes': 0, 'rows': rows, 'per_task': stats,
                  'sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in (data_path, replay_path, Path(__file__))}}


def main():
    rows, audit = collect()
    OUT.mkdir(parents=True, exist_ok=True)
    DEST.mkdir(parents=True, exist_ok=True)
    title = 'Overview of the synthetic dataset.'
    notes = [
        '数据集包含 104 个任务，每个任务配有干净与攻击两个版本。Business 包含付款与客户信息更新，Office 包含邮件、文档授权与日程，Cloud 包含云端部署。',
        'Tasks 为任务数；Tool Types 为每条轨迹实际调用的不同工具接口数的均值；Avg. Traj. 与 Range 分别为平均工具调用步数及最小—最大值；Avg. Verify. 为平均核验相关调用次数，包含提交核验与领取回执。',
        '统计采用完整 DAFR 的 104 条干净历史轨迹，经新版工具协议确定性展开并回放，包含成功、失败及重试，不含执行前自动导入。任务目标、攻击内容和几何判定保持原样；本表描述协议改造后的回放结构，不代表新模型自主执行的实测结果。'
    ]
    plt.rcParams.update({'font.family': 'Arial', 'font.size': 12, 'pdf.fonttype': 42})
    fig = plt.figure(figsize=(9.0, 5.0), facecolor='white')
    ax = fig.add_axes([.055, .435, .89, .40])
    ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis('off')
    xs = [.012, .225, .405, .603, .778, .943]
    ax.text(.5, 1.30, title, ha='center', fontsize=15)
    for y in (1.07, 1.05):
        ax.plot([0, 1.015], [y, y], color='black', lw=.7, clip_on=False)
    ax.text(.67, .92, 'Replay Statistics', ha='center', fontsize=12)
    ax.plot([.30, 1.015], [.81, .81], color='black', lw=.7, clip_on=False)
    for i, heading in enumerate(['Env.', 'Tasks', 'Tool Types', 'Avg. Traj.', 'Range', 'Avg. Verify.']):
        ax.text(xs[i], .69, heading, ha='left' if i == 0 else 'center', va='center')
    ax.plot([0, 1.015], [.57, .57], color='black', lw=.85, clip_on=False)
    for index, row in enumerate(rows):
        y = .43 - index * .19
        overall = row[0] == 'Overall'
        if overall:
            ax.plot([0, 1.015], [y+.105, y+.105], color='black', lw=.65, clip_on=False)
        for i, value in enumerate(row):
            ax.text(xs[i], y, str(value), ha='left' if i == 0 else 'center', va='center',
                    fontweight='bold' if overall else 'normal')
    for y in (-.25, -.27):
        ax.plot([0, 1.015], [y, y], color='black', lw=.7, clip_on=False)
    font = FontProperties(fname='C:/Windows/Fonts/simsun.ttc', size=9.5)
    fig.canvas.draw()
    y = .28
    for note in notes:
        wrapped = wrap_measured(fig, note, font, fig.bbox.width*.90)
        artist = fig.text(.055, y, wrapped, va='top', fontproperties=font, linespacing=1.45)
        fig.canvas.draw()
        y -= artist.get_window_extent(fig.canvas.get_renderer()).height / fig.bbox.height + .016
    fig.savefig(OUT/'数据概览.pdf', bbox_inches='tight', pad_inches=.13)
    fig.savefig(OUT/'preview.png', dpi=180, bbox_inches='tight', pad_inches=.13)
    plt.close(fig)
    body = []
    for row in rows:
        values = [str(v).replace('–', '--') for v in row]
        if row[0] == 'Overall':
            body.append(r'\midrule')
            values = [r'\textbf{'+v+'}' for v in values]
        body.append(' & '.join(values) + r' \\')
    tex = r'''% Compile with XeLaTeX. Statistics are deterministic replay, not new LLM runs.
\documentclass[UTF8]{ctexart}
\usepackage[a4paper,margin=20mm]{geometry}
\usepackage{fontspec,booktabs,caption}
\setmainfont{Arial}
\pagestyle{empty}
\begin{document}
\begin{table}[ht]
\centering
\caption{Overview of the synthetic dataset.}
\label{tab:synthetic-protocol-overview}
\renewcommand{\arraystretch}{1.2}
\setlength{\tabcolsep}{7pt}
\begin{tabular}{@{}lccccc@{}}
\hline\hline
& & \multicolumn{4}{c}{Replay Statistics} \\
\cmidrule(l){3-6}
Env. & Tasks & Tool Types & Avg. Traj. & Range & Avg. Verify. \\
\midrule
''' + '\n'.join(body) + r'''
\hline\hline
\end{tabular}
\par\medskip
\begin{minipage}{\linewidth}\small
''' + '\n\n'.join(notes) + r'''
\end{minipage}
\end{table}
\end{document}
'''
    (OUT/'数据概览.tex').write_text(tex, encoding='utf-8')
    (OUT/'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    for ext in ('pdf', 'tex'):
        target = DEST / f'数据概览.{ext}'
        if target.exists():
            backup = OUT/'previous'; backup.mkdir(exist_ok=True)
            shutil.copy2(target, backup / f'{datetime.now():%Y%m%d_%H%M%S}.{ext}')
        shutil.copy2(OUT/target.name, target)
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == '__main__':
    main()
