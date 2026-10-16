"""Monochrome three-rule geometry comparison, matching the reference table."""
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/summaries/geometry_booktabs'
DEST = Path('C:/Users/Administrator/Desktop/表/几何对比')

CAPTION = (
    '几何建模与线性规则的比较。使用 DeepSeek-v4-flash-0731，在同一批 104 个配对任务上评估，每种配置包含 104 次干净执行与 104 次攻击执行。'
    '线性规则在相同动作—证据坐标上替代完整几何判别部分（半空间约束与联合风险曲面）；证据投影、动作—证据绑定、反馈机制、工具接口及执行预算一致。'
    'CU、UA、ASR 分别为干净任务完成率、攻击条件下原任务完成率和攻击者目标达成率，均为百分比，按环境状态独立判定。'
    'Tool Calls 为全部 208 次执行的工具调用总数，包含被防御层拒绝的有效请求。'
)


def wrap_measured(fig, text, font, width_pixels):
    """Wrap the mixed Chinese/Latin caption to the actual figure text width."""
    renderer = fig.canvas.get_renderer()
    lines, current = [], ''
    for char in text:
        trial = current + char
        width = renderer.get_text_width_height_descent(trial, font, False)[0]
        if width > width_pixels and current:
            # Keep a line-start Chinese punctuation mark with its preceding text.
            if char in '，。；：、）':
                lines.append(trial); current = ''
            else:
                lines.append(current); current = char
        else:
            current = trial
    if current: lines.append(current)
    return '\n'.join(lines)


def main():
    source = json.loads((ROOT / 'results/summaries/workflow_catalog_104/summary.json').read_text())
    assert source['complete']
    rows = {row['arm']: row for row in source['rows']}
    cells = [[label, *[f"{rows[arm][metric]:.1f}" for metric in ('CU', 'UA', 'ASR')],
              str(rows[arm]['total_tool_calls'])]
             for arm, label in [('full', 'DAFR'), ('linear', 'Linear Rules')]]
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family': 'Times New Roman', 'pdf.fonttype': 42,
                         'mathtext.fontset': 'stix', 'text.color': 'black'})
    fig = plt.figure(figsize=(10.8, 4.25), facecolor='white')
    ax = fig.add_axes([.055, .49, .89, .45])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
    x = [.025, .435, .595, .755, .965]
    headings = ['Configuration', r'CU$\uparrow$', r'UA$\uparrow$', r'ASR$\downarrow$', 'Tool Calls']
    for px, label in zip(x, headings):
        ax.text(px, .79, label, ha='left' if px == x[0] else ('right' if px == x[-1] else 'center'),
                va='center', fontsize=21, fontweight='bold')
    for y, row in zip([.45, .14], cells):
        for index, (px, value) in enumerate(zip(x, row)):
            ax.text(px, y, value, ha='left' if index == 0 else ('right' if index == 4 else 'center'),
                    va='center', fontsize=21)
    for y, lw in [(1, 1.65), (.61, 1.05), (-.045, 1.65)]:
        ax.plot([0, 1], [y, y], color='black', lw=lw, clip_on=False)
    font = FontProperties(fname='C:/Windows/Fonts/simsun.ttc', size=11)
    fig.canvas.draw()
    wrapped = wrap_measured(fig, '表 1：' + CAPTION, font, fig.bbox.width*.89)
    fig.text(.055, .40, wrapped, fontproperties=font, va='top', linespacing=1.65)
    for ext in ('pdf', 'png'):
        fig.savefig(OUT/f'表格.{ext}', dpi=220, bbox_inches='tight', pad_inches=.12, facecolor='white')
    plt.close(fig)
    body = '\n'.join(' & '.join(row) + r' \\' for row in cells)
    tex = r'''% 使用 XeLaTeX 编译。黑白三线表，中文说明置于表下。
\documentclass[UTF8,11pt]{ctexart}
\usepackage[paperwidth=280mm,paperheight=120mm,margin=12mm]{geometry}
\usepackage{booktabs,caption,array}
\pagestyle{empty}
\captionsetup{font=small,labelsep=colon,justification=justified,singlelinecheck=false}
\begin{document}
\begin{table}[!ht]
\centering
{\fontsize{20}{25}\selectfont
\renewcommand{\arraystretch}{1.35}
\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}lcccr@{}}
\toprule[1.1pt]
\textbf{Configuration} & \textbf{CU}$\uparrow$ & \textbf{UA}$\uparrow$ & \textbf{ASR}$\downarrow$ & \textbf{Tool Calls} \\
\midrule[0.7pt]
''' + body + '\n' + r'''\bottomrule[1.1pt]
\end{tabular*}}
\caption{''' + CAPTION + r'''}
\label{tab:synthetic-geometry-comparison}
\end{table}
\end{document}
'''
    (OUT/'表格.tex').write_text(tex, encoding='utf-8')
    for ext in ('pdf', 'tex'):
        shutil.copy2(OUT/f'表格.{ext}', DEST/f'表格.{ext}')
        shutil.copy2(OUT/f'表格.{ext}', ROOT/f'paper/supplement/DAFR_Custom_Dataset_Geometry_Comparison_Preview.{ext}')
    shutil.copy2(OUT/'表格.png', ROOT/'paper/supplement/DAFR_Custom_Dataset_Geometry_Comparison_Preview.png')
    fragment = tex[tex.index(r'\begin{table}') : tex.index(r'\end{document}')]
    (ROOT/'paper/supplement/DAFR_Custom_Dataset_Geometry_Comparison_Table.tex').write_text(fragment, encoding='utf-8')
    print(str(DEST/'表格.pdf'))


if __name__ == '__main__': main()
