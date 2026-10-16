"""Describe the frozen synthetic dataset from fixtures, without model outcomes."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

import run_workflow_catalog_v2 as catalog
from render_geometry_booktabs import wrap_measured

ROOT = catalog.ROOT
OUT = ROOT / 'results/summaries/synthetic_dataset_profile'
DEST = Path('C:/Users/Administrator/Desktop/表/数据概览/合成数据')
DOMAINS = [(('payment', 'crm'), 'Finance and CRM'),
           (('email', 'documents', 'calendar'), 'Office Collaboration'),
           (('cloud',), 'Cloud Operations')]
ATTACKS = ['destination_redirect', 'payload_substitution', 'forged_approval']


def collect():
    path = ROOT / 'data/workflow_catalog_104/cases.jsonl'
    cases = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    clean = {c['group_id']: c for c in cases if c['variant'] == 'clean'}
    attacked = {c['group_id']: c for c in cases if c['variant'] == 'attack'}
    assert len(cases) == 208 and len(clean) == len(attacked) == 104
    assert clean.keys() == attacked.keys()
    catalog.configure_runner()
    tools = [t['function']['name'] for t in catalog.runner.schemas()]
    assert len(tools) == 6
    tasks = []
    for group, case in clean.items():
        attack = attacked[group]
        for field in ['domain', 'lane', 'records', 'registry_failures', 'attack_kind', 'task', 'expected']:
            assert case[field] == attack[field], (group, field)
        assert len(case['records']) == 2
        assert case['attack_kind'] in ATTACKS
        # Check the initial visible evidence, not model-dependent execution traces.
        world = catalog.CatalogWorld(case)
        evidence = [o['response'] for o in world.observations if o['tool'] == 'read_record']
        signed = any(r.get('channel') == 'signed_snapshot' and 'receipt' in r for r in evidence)
        assert signed == (case['lane'] == 'signed_snapshot')
        tasks.append({'group_id': group, 'domain': case['domain'],
                      'attack_label': case['attack_kind'], 'signed_snapshot': signed,
                      'stale_cache': any(r['cached_value'] != r['value'] for r in case['records'].values()),
                      'transient_registry_fault': case['registry_failures'] > 0,
                      'configured_failures_per_record': case['registry_failures'],
                      'record_count': len(case['records'])})
    rows = []
    for domains, label in DOMAINS + [(None, 'Overall')]:
        subset = [t for t in tasks if domains is None or t['domain'] in domains]
        row = [label, len(subset), 2*len(subset)] + [
            sum(t[k] for t in subset) for k in ['signed_snapshot', 'stale_cache', 'transient_registry_fault']]
        rows.append(row)
    assert rows[-1][1:] == [104, 208, 64, 25, 70]
    assert all(sum(row[i] for row in rows[:-1]) == rows[-1][i] for i in range(1, 6))
    sources = [path, Path(__file__), ROOT/'scripts/run_workflow_catalog_v2.py',
               ROOT/'scripts/run_mixed_workflow_pilot.py', ROOT/'scripts/run_queued_workflow_case.py']
    audit = {'rows': rows, 'tasks': tasks, 'tool_interfaces': tools,
             'counting_unit': 'distinct user task, clean/attack pair counted once',
             'domain_groups': {label: domains for domains, label in DOMAINS},
             'scenarios': 'one clean and one attacked variant per task',
             'scenario_columns': 'overlapping initial evidence and environment properties; not execution outcomes',
             'api_requests': 0,
             'sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    return rows, audit


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    DEST.mkdir(parents=True, exist_ok=True)
    profile_rows, audit = collect()
    trace_path = ROOT / 'results/summaries/catalog_fixed104_adapter_v11_104/rows.jsonl'
    records = [json.loads(s) for s in trace_path.read_text(encoding='utf-8').splitlines()]
    records = [r for r in records if r['arm'] == 'full' and r['variant'] == 'clean']
    assert len(records) == len({r['group_id'] for r in records}) == 104
    assert {r['group_id'] for r in records} == {t['group_id'] for t in audit['tasks']}
    for r in records:
        calls = [c for turn in r['trace'] for c in turn.get('results', [])]
        assert len(calls) == r['tool_calls'], r['id']
        r['verification_requests'] = sum(c['tool'] == 'verify_record' for c in calls)
    rows = []
    for (domains, _), name, counts in zip(DOMAINS, ['Business', 'Office', 'Cloud'], profile_rows):
        subset = [r for r in records if r['domain'] in domains]
        assert len(subset) == counts[1]
        rows.append([name, 6, len(subset), len(subset),
                     f"{sum(r['tool_calls'] for r in subset)/len(subset):.2f}",
                     f"{sum(r['verification_requests'] for r in subset)/len(subset):.2f}"])
    audit['display_rows'] = rows
    audit['sha256'][str(trace_path.relative_to(ROOT))] = hashlib.sha256(trace_path.read_bytes()).hexdigest()
    audit['execution_statistics'] = [{'group_id': r['group_id'], 'tool_calls': r['tool_calls'],
                                     'verification_requests': r['verification_requests']} for r in records]
    title = 'Overview of the synthetic dataset.'
    headings = ['Env.', 'Tools', 'User', 'Injection', 'Avg. Traj.', 'Avg. Verify.']
    paragraphs = [
        'Business 包含付款与客户信息更新，Office 包含邮件、文档授权与日程，Cloud 包含云端部署。Tools 为每类可用工具接口数，三类共用同一套 6 个接口；User 为用户任务数，Injection 为配对攻击场景数，共 104 个任务、104 个攻击场景。',
        'Avg. Traj. 为每任务平均工具调用请求数，Avg. Verify. 为其中的平均核验请求数。两列统计 DeepSeek V4 Flash（0731）运行完整 DAFR 的全部 104 次干净执行，包含成功、失败任务及被拦截、重试请求，不含代理执行前的自动导入。它们是固定配置下的实测轨迹统计，非最短参考轨迹。'
    ]
    plt.rcParams.update({'font.family': 'Arial', 'font.size': 12, 'pdf.fonttype': 42})
    fig = plt.figure(figsize=(8.1, 4.5))
    ax = fig.add_axes([.055, .40, .89, .43])
    ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis('off')
    x = [.015, .255, .39, .555, .755, .94]
    ax.text(.5, 1.30, title, ha='center', fontsize=14)
    ax.text(.4725, .90, 'Tasks', ha='center')
    ax.text(.8475, .90, 'Statistics', ha='center')
    ax.plot([.325, .645], [.79, .79], color='black', lw=.65)
    ax.plot([.665, 1.015], [.79, .79], color='black', lw=.65, clip_on=False)
    for y in [1.06, 1.04]:
        ax.plot([0, 1.015], [y, y], color='black', lw=.65, clip_on=False)
    for j, label in enumerate(headings):
        ax.text(x[j], .665, label, ha='left' if j == 0 else 'center', va='center')
    ax.plot([0, 1.015], [.55, .55], color='black', lw=.8, clip_on=False)
    for i, row in enumerate(rows):
        y = .405 - i * .20
        overall = row[0] == 'Overall'
        if overall:
            ax.plot([0, 1], [y+.085, y+.085], color='black', lw=.65)
        for j, value in enumerate(row):
            ax.text(x[j], y, str(value), ha='left' if j == 0 else 'center', va='center',
                    fontweight='bold' if overall else 'normal')
    for y in [-.105, -.125]:
        ax.plot([0, 1.015], [y, y], color='black', lw=.65, clip_on=False)
    font = FontProperties(fname='C:/Windows/Fonts/simsun.ttc', size=9)
    fig.canvas.draw()
    y = .30
    for paragraph in paragraphs:
        wrapped = wrap_measured(fig, paragraph, font, fig.bbox.width * .90)
        text = fig.text(.055, y, wrapped, fontproperties=font, va='top', linespacing=1.4)
        fig.canvas.draw()
        y -= text.get_window_extent(fig.canvas.get_renderer()).height / fig.bbox.height + .018
    fig.savefig(OUT/'数据概览.pdf', bbox_inches='tight', pad_inches=.12)
    fig.savefig(OUT/'preview.png', dpi=160, bbox_inches='tight', pad_inches=.12)
    plt.close(fig)
    body = []
    for row in rows:
        if row[0] == 'Overall':
            body.append(r'\midrule')
            values = [r'\textbf{'+str(v)+'}' for v in row]
        else:
            values = list(map(str, row))
        body.append(' & '.join(values) + r' \\')
    tex = r'''% Compile with XeLaTeX. All statistics are computed from the frozen 104-task dataset.
\documentclass[UTF8]{ctexart}
\usepackage[a4paper,margin=22mm]{geometry}
\usepackage{fontspec,booktabs,caption}
\setmainfont{Arial}
\pagestyle{empty}
\begin{document}
\begin{table}[ht]
\centering
\caption{Overview of the synthetic dataset.}
\label{tab:synthetic-dataset-profile}
\renewcommand{\arraystretch}{1.2}
\setlength{\tabcolsep}{7pt}
\begin{tabular}{@{}lccccc@{}}
\hline\hline
& & \multicolumn{2}{c}{Tasks} & \multicolumn{2}{c}{Statistics} \\
\cmidrule(lr){3-4}\cmidrule(l){5-6}
Env. & Tools & User & Injection & Avg. Traj. & Avg. Verify. \\
\midrule
''' + '\n'.join(body) + r'''
\hline\hline
\end{tabular}
\par\medskip
\begin{minipage}{\linewidth}\small
''' + paragraphs[0] + '\n\n' + paragraphs[1] + r'''
\end{minipage}
\end{table}
\end{document}
'''
    (OUT/'数据概览.tex').write_text(tex, encoding='utf-8')
    (OUT/'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    for suffix in ['pdf', 'tex']:
        target = DEST / ('数据概览.'+suffix)
        if target.exists():
            backup = OUT / 'previous'; backup.mkdir(exist_ok=True)
            shutil.copy2(target, backup/(datetime.now().strftime('%Y%m%d_%H%M%S')+'.'+suffix))
        shutil.copy2(OUT/target.name, target)
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == '__main__':
    main()
