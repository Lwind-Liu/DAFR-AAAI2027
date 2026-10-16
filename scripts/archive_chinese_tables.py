"""Archive frozen results and Chinese table explanations on the desktop."""
import csv
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import textwrap

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

ROOT = Path(__file__).resolve().parents[1]
DEST = Path('C:/Users/Administrator/Desktop/表')
OLD = ROOT / 'archives/DAFR_Tables_Data_Records_20261013_150215'
ZH = FontProperties(fname='C:/Windows/Fonts/msyh.ttc', size=11)
plt.rcParams.update({'font.family': 'Times New Roman', 'pdf.fonttype': 42})
COPIES = []


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    COPIES.append((target, str(source)))


def tree(source, target):
    for path in source.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            copy(path, target / path.relative_to(source))


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8-sig' if path.suffix == '.txt' else 'utf-8')


def csv_write(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def tex_files(folder, fragment):
    write(folder / '表格片段.tex', fragment)
    write(folder / '表格.tex', r'''% 使用 XeLaTeX 编译；中文说明可直接供论文作者参考。
\documentclass[UTF8]{ctexart}
\usepackage[a3paper,landscape,margin=15mm]{geometry}
\usepackage{booktabs,multirow,graphicx}
\usepackage[table]{xcolor}
\begin{document}
''' + fragment + '\n' + r'\end{document}' + '\n')


def small_table(folder, headers, cells, caption, title):
    folder.mkdir(parents=True, exist_ok=True)
    # Make room for Chinese explanations without shrinking the table text.
    lines = []
    for paragraph in caption.split('\n'):
        current, units = '', 0
        for token in re.findall(r'[A-Za-z0-9_/%–.\-]+|.', paragraph):
            width = sum(2 if ord(char) > 255 else 1 for char in token)
            if current and units + width > 130:
                lines.append(current.rstrip())
                current, units = '', 0
            current += token
            units += width
        lines.append(current.rstrip())
    fig, ax = plt.subplots(figsize=(12, 4 + .25 * len(lines)))
    ax.axis('off')
    caption_height = .035 * len(lines) + .04
    table = ax.table(cellText=cells, colLabels=headers, cellLoc='right',
                     bbox=[0, caption_height + .08, 1, .78 - caption_height])
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    for (i, j), cell in table.get_celld().items():
        cell.set_edgecolor('white')
        if j == 0:
            cell.set_text_props(ha='left')
        if i == 0:
            cell.set_text_props(weight='bold')
        if i > 0 and cells[i-1][0] == 'DAFR':
            cell.set_facecolor('#e5e5e5')
            if j == 0:
                cell.set_text_props(weight='bold')
    bottom, height = caption_height + .08, .78 - caption_height
    for y, weight in ((bottom + height, 1.2),
                      (bottom + height - height/(len(cells)+1), .8), (bottom, 1.2)):
        ax.plot([0, 1], [y, y], color='black', lw=weight, transform=ax.transAxes)
    ax.text(0, .94, title, transform=ax.transAxes, fontproperties=ZH, fontsize=14)
    ax.text(0, .025, '\n'.join(lines), transform=ax.transAxes,
            fontproperties=ZH, fontsize=11, va='bottom', linespacing=1.6)
    fig.tight_layout(pad=.5)
    for extension in ('pdf', 'png'):
        fig.savefig(folder / ('表格.' + extension), bbox_inches='tight', dpi=180)
    plt.close(fig)
    header = ' & '.join(headers).replace('%', r'\%').replace('↑', r'$\uparrow$').replace('↓', r'$\downarrow$')
    body = []
    for row in cells:
        text = ' & '.join(row).replace('%', r'\%')
        if row[0] == 'DAFR':
            text = r'\rowcolor{gray!15}' + text.replace('DAFR', r'\textbf{DAFR}', 1)
        body.append(text + r' \\')
    fragment = (r'\begin{table}[!ht]' + '\n' + r'\centering\small' + '\n'
                + r'\renewcommand{\arraystretch}{1.25}' + '\n' + r'\resizebox{\linewidth}{!}{%'
                + '\n' + r'\begin{tabular}{l' + 'r' * (len(headers)-1) + '}\n'
                + r'\toprule' + '\n' + header + r' \\' + '\n' + r'\midrule' + '\n'
                + '\n'.join(body) + '\n' + r'\bottomrule' + '\n' + r'\end{tabular}}'
                + '\n' + r'\caption{' + caption.replace('\n', r'\par ').replace('%', r'\%') + '}\n'
                + r'\end{table}' + '\n')
    tex_files(folder, fragment)
    write(folder / '说明.txt', title + '\n\n' + caption + '\n\n表格.tex 是独立编译文件（XeLaTeX）；表格片段.tex 用于插入论文。\n')


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    agent = DEST / 'AgentDojo主表'
    agent.mkdir(exist_ok=True)
    original = OLD / '01_AgentDojo_Main_Table/AgentDojo_Main_Table.tex'
    raw = original.read_text(encoding='utf-8')
    caption = ('AgentDojo 主结果：在 Workspace、Slack、Travel、Banking 四个领域，比较三种规划模型下的六种方法。\n'
        'CU 为无攻击条件下的任务完成率，UA 为有攻击条件下的原任务完成率，ASR 为攻击者目标达成率；单位均为百分比。CU、UA 越高越好，ASR 越低越好。\n'
        'Overall 是四个领域结果的等权平均。每种模型分别比较各方法；加粗和下划线保留原主表的最优、次优数值标记，DAFR 行以灰色突出显示。')
    translated = re.sub(r'\\caption\{.*?\}\n\\label',
                        lambda _: '\\caption{' + caption.replace('\n', r'\par ') + '}\n\\label', raw, count=1, flags=re.S)
    # Move the translated caption below the numeric table.
    cap = re.search(r'\\caption\{.*?\}\n', translated, flags=re.S).group()
    label = re.search(r'\\label\{[^}]+\}\n', translated).group()
    translated = translated.replace(cap, '').replace(label, '').replace(r'\end{table*}', cap + label + r'\end{table*}')
    tex_files(agent, translated)
    copy(original, agent / '原始主表.tex')
    copy(OLD / '01_AgentDojo_Main_Table/main_table.csv', agent / '数值.csv')
    with (agent / '数值.csv').open(encoding='utf-8-sig') as stream:
        data = list(csv.DictReader(stream))
    assert len(data) == 90
    models = list(dict.fromkeys(r['Model'] for r in data))
    methods = list(dict.fromkeys(r['Method'] for r in data))
    domains = ['Workspace', 'Slack', 'Travel', 'Banking', 'Overall']
    numeric_lines = [line for line in raw.splitlines() if len(line.split('&')) == 17]
    numeric_lines = [line for line in numeric_lines if re.search(r'&\s*(?:\\(?:textbf|underline)\{)?\d+\.\d+', line)]
    assert len(numeric_lines) == 18
    fig, ax = plt.subplots(figsize=(24, 10))
    ax.axis('off')
    xs = [0, .09, .19] + [.19 + .81*i/15 for i in range(1, 16)]
    top, row_h = .87, .033
    ax.text(0, .97, 'AgentDojo 主表', fontproperties=ZH, fontsize=16, transform=ax.transAxes)
    ax.text(.045, .92, 'Model', ha='center', weight='bold', transform=ax.transAxes)
    ax.text(.14, .92, 'Defense', ha='center', weight='bold', transform=ax.transAxes)
    for d, domain in enumerate(domains):
        ax.text(.19 + .81*(d+.5)/5, .94, domain, ha='center', weight='bold', transform=ax.transAxes)
        for k, metric in enumerate(('CU↑', 'UA↑', 'ASR↓')):
            col = 2 + d*3+k
            ax.text((xs[col]+xs[col+1])/2, .90, metric, ha='center', transform=ax.transAxes)
    for index, (model, method) in enumerate((m, n) for m in models for n in methods):
        y = top - row_h*(index+.5)
        if method == 'DAFR':
            ax.add_patch(plt.Rectangle((.09, y-row_h/2), .91, row_h, facecolor='#e5e5e5', transform=ax.transAxes))
        if index % 6 == 2:
            ax.text(.045, top-row_h*(index-index%6+3), model.replace(' V4', '\nV4').replace(' Haiku', '\nHaiku'),
                    ha='center', va='center', transform=ax.transAxes)
        ax.text(.14, y, method, ha='center', va='center', weight='bold' if method == 'DAFR' else 'normal', transform=ax.transAxes)
        source_cells = numeric_lines[index].split('&')[2:]
        for d, domain in enumerate(domains):
            item = next(r for r in data if r['Model'] == model and r['Method'] == method and r['Domain'] == domain)
            for k, metric in enumerate(('CU (%)', 'UA (%)', 'ASR (%)')):
                col = 2+d*3+k
                cell = source_cells[d*3+k]
                x = (xs[col]+xs[col+1])/2
                ax.text(x, y, item[metric], ha='center', va='center', transform=ax.transAxes,
                        weight='bold' if r'\textbf' in cell else 'normal', fontsize=11)
                if r'\underline' in cell:
                    ax.plot([x-.009, x+.009], [y-.010, y-.010], lw=.6, color='black', transform=ax.transAxes)
    for y in (.96, top, top-row_h*6, top-row_h*12, top-row_h*18):
        ax.plot([0, 1], [y, y], color='black', lw=1, transform=ax.transAxes)
    ax.text(0, .09, '\n'.join(textwrap.fill(p, width=100) for p in caption.split('\n')),
            fontproperties=ZH, fontsize=11, transform=ax.transAxes, va='bottom', linespacing=1.7)
    for ext in ('pdf', 'png'):
        fig.savefig(agent / ('表格.'+ext), bbox_inches='tight', dpi=180)
    plt.close(fig)
    write(agent / '说明.txt', caption + '\n\n数值来自用户确定的主表原稿；原始主表.tex 保留原稿。表格.tex 为中文说明的独立 XeLaTeX 文件。\n')
    tree(OLD / '04_AgentDojo_Records', agent / '记录')

    synthetic = ROOT / 'results/summaries/catalog_fixed104_adapter_v11_104'
    summary = json.loads((synthetic / 'summary.json').read_text())
    assert summary['complete']
    labels = dict(zip(('no_defense','piguard','protectai','progent','drift','full'),
                      ('No Defense','PIGuard','ProtectAI','Progent','DRIFT','DAFR')))
    rows = summary['rows']
    cells = [[labels[r['method']], *[f"{r[k]:.1f}" for k in ('CU','UA','ASR')], str(r['total_tool_calls'])] for r in rows]
    caption = ('合成数据主结果：使用 DeepSeek-v4-flash-0731，在同一批 104 个任务上比较六种方法；每个任务包含干净与攻击两个版本，每种方法共执行 208 次。\n'
        'CU 为 104 次干净执行的原任务完成率，UA 为 104 次攻击执行的原任务完成率，ASR 为攻击执行中攻击者目标达成率。三个指标独立统计，单位为百分比。\n'
        '各方法使用相同工具接口和执行预算。Total Tool Calls 为全部 208 次执行的工具调用总数，包含被防御层拒绝的有效提交。任务完成与攻击目标均根据环境实际状态判定。')
    folder = DEST / '合成主表'
    small_table(folder, ['Method','CU (%) ↑','UA (%) ↑','ASR (%) ↓','Total Tool Calls'], cells, caption, '合成数据主表')
    csv_write(folder / '数值.csv', rows)
    tree(synthetic, folder / '记录')

    ablation = ROOT / 'results/summaries/workflow_catalog_104'
    rows = json.loads((ablation / 'summary.json').read_text())['rows']
    labels = {'full':'DAFR','no_projection':'w/o Evidence Projection','no_lifting':'w/o Action--Evidence Lifting',
              'linear':'w/o Geometric Modeling','no_geometry':'w/o Feasibility Constraints'}
    cells = [[labels[r['arm']], *[f"{r[k]:.1f}" for k in ('CU','UA','ASR')], str(r['total_tool_calls'])] for r in rows]
    caption = ('模块消融：使用与合成主表相同的 104 个配对任务、模型、工具和预算，每种配置执行 104 次干净任务与 104 次攻击任务。CU、UA、ASR 的定义与合成主表一致。工具次数为 208 次执行的总数。\n'
        'w/o Evidence Projection：取消按证据来源区分可信度，工具观察中的声明也进入证据表示。\n'
        'w/o Action–Evidence Lifting：取消证据与具体动作参数、请求、版本及执行权限的严格绑定。\n'
        'w/o Geometric Modeling：在相同动作–证据坐标上，以线性判别替代完整几何可行域，包括半空间约束和联合风险曲面。\n'
        'w/o Feasibility Constraints：关闭半空间和联合风险的执行准入检查。各配置均保留工具参数校验及反馈机制。')
    folder = DEST / '合成消融'
    small_table(folder, ['Configuration','CU (%) ↑','UA (%) ↑','ASR (%) ↓','Total Tool Calls'], cells, caption, '合成数据模块消融')
    csv_write(folder / '数值.csv', rows)
    tree(OLD / '03_Synthetic_Ablation/records', folder / '记录')

    cost = ROOT / 'results/summaries/catalog_resource_cost_104'
    rows = json.loads((cost / 'protocol.json').read_text())['rows']
    cells = [[r['Method'], *[f"{r[k]:,.2f}" for k in ('Input Tokens','Output Tokens','Total Tokens','Tool Calls')]] for r in rows]
    caption = ('完整 104 个任务的资源开销：每种方法统计 104 次干净执行与 104 次攻击执行，表中所有数值均为单次执行的平均值。\n'
        'Input Tokens、Output Tokens 分别为输入与输出 token 数，包含 agent 规划和防御方法额外产生的大模型调用；Total Tokens 为输入与输出之和。\n'
        'Tool Calls 为单次执行平均发起的工具调用次数，包含被防御层拒绝的有效请求；不同于合成主表和消融表中的总调用次数。\n'
        '数值从已完成的六方法执行记录汇总，按原始数值计算后保留两位小数。此表展示 token 与工具调用开销，执行时间另行统计。')
    folder = DEST / '开销表'
    small_table(folder, ['Method','Input Tokens ↓','Output Tokens ↓','Total Tokens ↓','Tool Calls ↓'], cells, caption, '合成数据资源开销')
    csv_write(folder / '数值.csv', rows)
    tree(ROOT / 'results/summaries/catalog_inference_cost_v1', folder / '记录')
    copy(cost / 'protocol.json', folder / '记录/制表口径.json')

    dataset = DEST / '合成数据'
    tree(ROOT / 'data/workflow_catalog_104', dataset)
    cases = [json.loads(line) for line in (dataset / 'cases.jsonl').read_text().splitlines()]
    groups = {r['group_id'] for r in cases}
    assert len(cases) == 208 and len(groups) == 104
    counts = Counter(r['domain'] for r in cases if r['variant'] == 'clean')
    domain_names = {'payment':'支付','email':'邮件','documents':'文档','calendar':'日历','crm':'客户管理','cloud':'云资源'}
    explanation = ('数据规模：104 个任务、208 条配对记录。每个任务各有一个干净版本和一个攻击版本。\n'
        '领域分布：' + '、'.join(domain_names[k] + str(v) + '个' for k,v in counts.items()) + '。\n'
        '定位：面向多领域业务流程构建的可执行合成 agent 工具调用环境。大模型通过读取请求、核验证据、准备操作、提交操作和核对关闭等接口完成任务；工具环境记录操作造成的实际状态变化。\n'
        '配对设计：同一任务的原始业务目标、工具和风险设置保持一致；攻击版本在外部记录中引入重定向或验证绕过内容。任务完成和攻击成功分别根据环境状态判断。\n'
        'cases.jsonl 每行一个任务版本。task 是原任务说明，expected 是正确目标状态，attacker_destination/attacker_payload 是攻击目标，records 是可读取和核验的业务记录，risk_metadata 是联合风险输入，group_id 对应配对任务。\n'
        '主表和消融均按完整 104 对任务统计。环境代码目录保留本次实验所用工具环境与风险检查实现。\n')
    write(dataset / '数据说明.txt', explanation)
    csv_write(dataset / '领域统计.csv', [{'领域':domain_names[k], '任务数':v, '执行版本数':v*2} for k,v in counts.items()])
    tree(OLD / '05_Method_Snapshot', dataset / '环境代码')
    write(DEST / '目录说明.txt', '本目录为当前确定版本的表格与数据归档。\n\n'
        'AgentDojo主表：用户确定的三模型、四领域主表，附原稿、中文表下说明和记录。\n'
        '合成数据：104 个任务的干净/攻击配对数据、领域统计和环境代码。\n'
        '合成主表：完整 104 个任务上六种方法的 CU、UA、ASR 与工具调用总数。\n'
        '合成消融：同一批任务上的完整方法与四个模块消融配置。\n'
        '开销表：同一批任务的输入/输出/总 token 和平均工具调用次数。\n\n'
        '各表目录：表格.pdf 供查看；表格.tex 使用 XeLaTeX 独立编译；表格片段.tex 供插入论文；数值.csv 供取数；说明.txt 为中文解释；记录目录保留原始来源。\n'
        '所有表下说明已写成中文。合成数据表使用固定 104 任务版本；阶段性动态试验及小样本耗时表不纳入本次归档。\n')
    source_map = {str(p.relative_to(DEST)): source for p,source in COPIES}
    manifest = []
    for path in sorted(DEST.rglob('*')):
        if path.is_file() and path.name != '清单.csv':
            manifest.append({'文件':str(path.relative_to(DEST)), '字节数':path.stat().st_size,
                'SHA256':hashlib.sha256(path.read_bytes()).hexdigest(),
                '来源':source_map.get(str(path.relative_to(DEST)), '按已归档来源重新制表或编写中文说明')})
    csv_write(DEST / '清单.csv', manifest)
    print(json.dumps({'destination':str(DEST), 'files':len(manifest), 'dataset_pairs':104, 'tables':4}, ensure_ascii=True))


if __name__ == '__main__':
    main()
