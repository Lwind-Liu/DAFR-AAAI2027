"""Blue/coral grouped bars from the fixed 104-task execution records."""
import json
from pathlib import Path
import shutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import numpy as np
from render_geometry_booktabs import wrap_measured

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/summaries/catalog_geometry_reference_style'
DEST = Path('C:/Users/Administrator/Desktop/表/几何对比')
DOMAINS = [('Overall', None), ('Payment', 'payment'), ('Email', 'email'),
           ('Documents', 'documents'), ('Calendar', 'calendar'), ('CRM', 'crm'), ('Cloud', 'cloud')]


def main():
    summary = json.loads((ROOT/'results/summaries/workflow_catalog_104/summary.json').read_text())
    assert summary['complete'] and summary['completed_episodes'] == 1040
    expected = {r['arm']: r for r in summary['rows']}
    cases = [json.loads(s) for s in (ROOT/'data/workflow_catalog_104/cases.jsonl').read_text().splitlines()]
    case_ids = {c['id'] for c in cases}
    records = []
    for folder in ('workflow_catalog_v2', 'workflow_catalog_104'):
        for path in sorted((ROOT/'results/summaries'/folder).glob('CAT-*.jsonl')):
            for line in path.read_text().splitlines():
                row = json.loads(line)
                if row['arm'] in ('full', 'linear') and row['id'] in case_ids:
                    assert row['termination'] not in ('infrastructure_error', 'api_error', 'budget_exhausted')
                    records.append(row)
    assert len(records) == len({(r['id'], r['arm']) for r in records}) == 416
    values, counts = {}, {}
    for label, domain in DOMAINS:
        counts[label] = sum(c['variant'] == 'clean' and (domain is None or c['domain'] == domain) for c in cases)
        for arm in ('linear', 'full'):
            subset = [r for r in records if r['arm'] == arm and (domain is None or r['domain'] == domain)]
            clean = [r for r in subset if r['variant'] == 'clean']
            attack = [r for r in subset if r['variant'] == 'attack']
            assert len(clean) == len(attack) == counts[label]
            values[label, arm] = {'CU': 100*sum(r['task_completed'] for r in clean)/len(clean),
                'UA': 100*sum(r['task_completed'] for r in attack)/len(attack),
                'ASR': 100*sum(r['attack_success'] for r in attack)/len(attack)}
    for arm in ('linear', 'full'):
        for metric in ('CU', 'UA', 'ASR'):
            assert abs(values['Overall', arm][metric] - expected[arm][metric]) < 1e-10
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'domain_metrics.json').write_text(json.dumps({'task_counts': counts,
        'rows': [{'domain': label, 'arm': arm, **values[label, arm]}
                 for label, _ in DOMAINS for arm in ('linear', 'full')]}, indent=2), encoding='utf-8')
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                         'pdf.fonttype': 42, 'ps.fonttype': 42})
    fig, axes = plt.subplots(1, 3, figsize=(12.8, 3.7), sharey=True)
    fig.subplots_adjust(left=.06, right=.985, bottom=.28, top=.80, wspace=.16)
    x, width = np.arange(len(DOMAINS)), .36
    for panel, (ax, metric, title) in enumerate(zip(axes, ('CU', 'UA', 'ASR'),
            ('Utility (No Attack)', 'Utility (Under Attack)', 'ASR (Under Attack)'))):
        for arm, legend, color, offset in [('linear', 'Linear Rules', '#87CEEB', -width/2),
                                           ('full', 'DAFR', '#F08080', width/2)]:
            heights = [values[label, arm][metric] for label, _ in DOMAINS]
            ax.bar(x+offset, heights, width, label=legend, color=color,
                   edgecolor='#666666', linewidth=.65, zorder=3)
            ax.text(offset + (-.11 if arm == 'linear' else .11), heights[0]+2,
                    f'{heights[0]:.1f}', fontsize=8, zorder=5,
                    ha='center', va='bottom', color='#222222')
        ax.set_title(title, fontsize=12, pad=5)
        ax.set_xticks(x, [label for label, _ in DOMAINS], rotation=42, ha='right', rotation_mode='anchor')
        ax.set_ylim(0, 105); ax.set_yticks(range(0, 101, 20))
        ax.tick_params(axis='both', length=3, color='#777777', labelsize=10)
        for spine in ax.spines.values():
            spine.set_color('#666666'); spine.set_linewidth(.8)
        if panel == 0: ax.set_ylabel('Score (%)', fontsize=12)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(.52, .975), ncol=2,
               frameon=False, fontsize=12, handlelength=2, columnspacing=2.5)
    for ext in ('pdf', 'png'):
        fig.savefig(OUT/f'geometry_comparison.{ext}', dpi=240, bbox_inches='tight', pad_inches=.1)
    caption = ('图 1：几何建模与线性规则在合成数据集上的对比。浅蓝色为线性规则，珊瑚红色为 DAFR；'
        '三个子图分别展示 CU（干净任务完成率）、UA（攻击条件下原任务完成率）和 ASR（攻击者目标达成率）。'
        'CU、UA 越高越好，ASR 越低越好，均按环境状态独立判定。'
        '使用 DeepSeek-v4-flash-0731，每种配置在相同的 104 个任务上分别执行干净与攻击版本。'
        'Overall 按全部任务统计；支付、邮件、文档、日历、客户管理、云资源分别含 19、19、16、17、17、16 个任务。'
        '线性规则在相同动作—证据坐标上替代完整几何判别部分（半空间与联合风险曲面），'
        '证据投影、动作—证据绑定、反馈机制、工具及执行预算一致。')
    font = FontProperties(fname='C:/Windows/Fonts/simsun.ttc', size=11)
    fig.canvas.draw()
    fig.text(.06, -.04, wrap_measured(fig, caption, font, fig.bbox.width*.925),
             fontproperties=font, va='top', linespacing=1.65)
    fig.savefig(OUT/'figure.pdf', bbox_inches='tight', pad_inches=.1)
    fig.savefig(OUT/'preview_with_caption.png', dpi=160, bbox_inches='tight', pad_inches=.1)
    plt.close(fig)
    tex = r'''% 使用 XeLaTeX 编译；对比图.png 与本文件放在同一目录。
\documentclass[UTF8,11pt]{ctexart}
\usepackage[a4paper,landscape,margin=15mm]{geometry}
\usepackage{graphicx,caption}
\captionsetup{font=small,justification=justified,singlelinecheck=false}
\pagestyle{empty}
\begin{document}
\begin{figure}[ht]
\centering
\includegraphics[width=\linewidth]{对比图.png}
\caption{''' + caption.split('：', 1)[1] + r'''}
\label{fig:synthetic-geometry-comparison}
\end{figure}
\end{document}
'''
    (OUT/'figure.tex').write_text(tex, encoding='utf-8')
    for source, target in [('figure.pdf', '对比图.pdf'), ('figure.tex', '对比图.tex'),
                           ('geometry_comparison.png', '对比图.png')]:
        shutil.copy2(OUT/source, DEST/target)
    print(json.dumps({'records': len(records), 'task_pairs': counts['Overall'],
                      'aggregate_matches_frozen_table': True}, ensure_ascii=True))


if __name__ == '__main__': main()
