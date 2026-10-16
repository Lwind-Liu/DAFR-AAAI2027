"""Archive-backed overview of the three evaluated dataset subsets."""
import ast
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import run_workflow_catalog_v2 as catalog
from render_geometry_booktabs import wrap_measured

ROOT=catalog.ROOT
sys.path.insert(0,str(ROOT/'external/official_baselines/AutoDojo/agentdojo/src'))
from agentdojo.task_suite.load_suites import get_suite

OUT=ROOT/'results/summaries/three_dataset_overviews'
DEST=Path('C:/Users/Administrator/Desktop/表/数据概览')


def mean(xs):return sum(xs)/len(xs) if xs else None


def agentdojo():
    path=ROOT/'release_assets/agentdojo_deepseek_main_raw.zip'
    with zipfile.ZipFile(path) as z:
        records=[json.loads(z.read(n)) for n in z.namelist() if '/clafr/' in n and '/user_task_' in n and n.endswith('.json')]
    out=[]
    for domain,label in [('workspace','Workspace'),('slack','Slack'),('travel','Travel'),('banking','Banking')]:
        rs=[r for r in records if r['suite_name']==domain]
        clean=[r for r in rs if not r.get('injection_task_id')]
        attack=[r for r in rs if r.get('injection_task_id')]
        assert len(clean)==len({r['user_task_id'] for r in clean})
        assert {r['user_task_id'] for r in attack}=={r['user_task_id'] for r in clean}
        assert all(r.get('error') is None for r in rs)
        calls=lambda rs:[sum(len(m.get('tool_calls') or []) for m in r['messages'] if m['role']=='assistant') for r in rs]
        suite=get_suite('v1.2.2',domain)
        services={t.name:t.run.__module__.split('.')[-1] for t in suite.tools}
        references=[]
        for record in clean:
            task=suite.get_user_task_by_id(record['user_task_id'])
            env=task.init_environment(suite.load_and_inject_default_environment({}))
            sequence=task.ground_truth(env)
            names=[c.function for c in sequence]
            references.append({'task':record['user_task_id'],'actions':names,
                               'services':sorted({services[n] for n in names})})
        out.append({'domain':label,'tools':len(suite.tools),'tasks':len(clean),'attacks':len(attack),
                    'injections':sorted({domain+':'+r['injection_task_id'] for r in attack}),
                    'reference_lengths':[len(r['actions']) for r in references],
                    'applications':[len(r['services']) for r in references],
                    'references':references,'service_mapping':services,
                    'clean_calls':calls(clean),'attack_calls':calls(attack)})
    assert sum(r['tasks'] for r in out)==71 and sum(r['attacks'] for r in out)==585
    return out


def asb():
    path=ROOT/'release_assets/asb_and_margin_raw.zip'
    with zipfile.ZipFile(path) as z:
        rs=[json.loads(z.read(n)) for n in z.namelist() if n.startswith('asb_204_final_v3_clafr/clafr_feedback/') and n.endswith('.json')]
        manifest=json.loads(z.read('asb_204_final_v3_clafr/manifest.json'))
    assert {r['case_id'] for r in rs}==set(manifest['cases'])
    labels=[('financial_analyst_agent','Finance'),('legal_consultant_agent','Legal'),('medical_advisor_agent','Medical'),
            ('education_consultant_agent','Education'),('psychological_counselor_agent','Psychology'),
            ('ecommerce_manager_agent','E-commerce'),('aerospace_engineer_agent','Aerospace'),
            ('academic_search_agent','Academic Search'),('autonomous_driving_agent','Autonomous Driving'),('system_admin_agent','System Administration')]
    out=[]
    for agent,label in labels:
        subset=[r for r in rs if r['agent_name']==agent]
        toolcounts=[]
        for r in subset:
            toolnames=ast.literal_eval(re.search(r'The valid tool names are EXACTLY:\s*(\[[^\n]+\])',r['messages'][0]['content']).group(1))
            toolcounts.append(len(toolnames))
            assert r['shield']['evaluated_tool_calls']==len(r['shield']['decision_logs'])
        assert set(toolcounts)=={3}
        out.append({'domain':label,'tools':3,'tasks':len({r['task_id'] for r in subset}),'attacks':len(subset),
                    'injections':sorted({agent+':'+str(r['attack_id']) for r in subset}),
                    'reference_lengths':[],'applications':[],
                    'clean_calls':[],'attack_calls':[r['shield']['evaluated_tool_calls'] for r in subset]})
    assert sum(r['tasks'] for r in out)==51 and sum(r['attacks'] for r in out)==204
    return out


def synthetic():
    cases=[json.loads(s) for s in (ROOT/'data/workflow_catalog_104/cases.jsonl').read_text(encoding='utf-8').splitlines()]
    rs=[json.loads(s) for s in (ROOT/'results/summaries/catalog_fixed104_adapter_v11_104/rows.jsonl').read_text(encoding='utf-8').splitlines()]
    catalog.configure_runner();nt=len(catalog.runner.schemas());out=[]
    for domain,label in [('payment','Payment'),('email','Email'),('documents','Documents'),('calendar','Calendar'),('crm','CRM'),('cloud','Cloud')]:
        cs=[c for c in cases if c['domain']==domain]
        clean=[r for r in rs if r['arm']=='full' and r['domain']==domain and r['variant']=='clean']
        attack=[r for r in rs if r['arm']=='full' and r['domain']==domain and r['variant']=='attack']
        assert len(clean)==len(attack)==len({c['group_id'] for c in cs})
        out.append({'domain':label,'tools':nt,'tasks':len(clean),'attacks':len(attack),
                    'injections':sorted({c['attack_kind'] for c in cs if c['variant']=='attack'}),
                    'reference_lengths':[],'applications':[],
                    'clean_calls':[r['tool_calls'] for r in clean],'attack_calls':[r['tool_calls'] for r in attack]})
    return out


def aggregate(rows):
    return {'domain':'Overall','tools':sum(r['tools']*r['tasks'] for r in rows)/sum(r['tasks'] for r in rows),
            'tasks':sum(r['tasks'] for r in rows),'attacks':sum(r['attacks'] for r in rows),
            'injections':sorted({v for r in rows for v in r['injections']}),
            'reference_lengths':[v for r in rows for v in r['reference_lengths']],
            'applications':[v for r in rows for v in r['applications']],
            'clean_calls':[v for r in rows for v in r['clean_calls']],
            'attack_calls':[v for r in rows for v in r['attack_calls']]}


def fmt(x):return '—' if x is None else f'{x:.2f}'


def render(name,title,rows,caption,summary=False):
    folder=OUT/name;folder.mkdir(parents=True,exist_ok=True)
    target=DEST if summary else DEST/name;target.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'Times New Roman','font.size':14,'pdf.fonttype':42})
    n=len(rows);height=3.4+n*.36
    fig=plt.figure(figsize=(14,height));ax=fig.add_axes([.035,.38,.93,.52]);ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
    x=[.01,.20,.305,.415,.535,.66,.805,.95] if summary else [.01,.33,.44,.56,.68,.815,.95]
    ax.text(.5,1.10,title,ha='center',fontsize=17)
    taskcols=(3,5) if summary else (2,4)
    ax.text((x[taskcols[0]]+x[taskcols[1]])/2,.94,'Tasks',ha='center')
    ax.text((x[-2]+x[-1])/2,.94,'Reference Statistics',ha='center')
    ax.plot([x[taskcols[0]]-.05,x[taskcols[1]]+.055],[.875,.875],color='black',lw=.7)
    ax.plot([x[-2]-.05,1],[.875,.875],color='black',lw=.7)
    headings=['Benchmark','Domains','Avg. Tools','User','Injection*','Pairs','Avg. Traj.','Avg. App.'] if summary else ['Domain','Tools','User','Injection*','Pairs','Avg. Traj.','Avg. App.']
    for j,(pos,label) in enumerate(zip(x,headings)):ax.text(pos,.81,label,ha='left' if j==0 else 'center',va='center')
    ax.plot([0,1],[1.02,1.02],color='black',lw=1.4,clip_on=False);ax.plot([0,1],[.735,.735],color='black',lw=.8)
    step=.66/n
    for i,row in enumerate(rows):
        y=.70-step*(i+.5)
        if row[0]=='Overall':ax.plot([0,1],[y+step*.52,y+step*.52],color='black',lw=.65)
        for j,(pos,value) in enumerate(zip(x,row)):
            ax.text(pos,y,value,ha='left' if j==0 else 'center',va='center',fontweight='bold' if row[0]=='Overall' else 'normal')
    ax.plot([0,1],[.025,.025],color='black',lw=1.4)
    font=FontProperties(fname='C:/Windows/Fonts/simsun.ttc',size=10)
    fig.canvas.draw();fig.text(.035,.34,wrap_measured(fig,caption,font,fig.bbox.width*.93),fontproperties=font,va='top',linespacing=1.5)
    fig.savefig(folder/'数据概览.pdf',bbox_inches='tight',pad_inches=.12)
    fig.savefig(folder/'preview.png',dpi=150,bbox_inches='tight',pad_inches=.12);plt.close(fig)
    body=[]
    for row in rows:
        if row[0]=='Overall':body.append(r'\midrule')
        body.append(' & '.join(row)+r' \\')
    tex=r'''% XeLaTeX; editable table.
\documentclass[UTF8]{ctexart}
\usepackage[a4paper,landscape,margin=18mm]{geometry}
\usepackage{fontspec,booktabs,caption}
\setmainfont{Times New Roman}\pagestyle{empty}
\begin{document}\begin{table}[ht]\centering
{\large '''+title+r'''}\par\medskip
\renewcommand{\arraystretch}{1.25}
\begin{tabular*}{.98\linewidth}{@{\extracolsep{\fill}}l'''+('c'* (len(headings)-1))+r'''@{}}
\toprule
'''+(' & & & '+r'\multicolumn{3}{c}{Tasks} & \multicolumn{2}{c}{Reference Statistics} \\' if summary else ' & & '+r'\multicolumn{3}{c}{Tasks} & \multicolumn{2}{c}{Reference Statistics} \\')+'\n'+(r'\cmidrule(lr){4-6}\cmidrule(l){7-8}' if summary else r'\cmidrule(lr){3-5}\cmidrule(l){6-7}')+'\n'+' & '.join(headings)+r' \\'+ '\n'+r'\midrule'+'\n'+'\n'.join(body)+r'''
\bottomrule\end{tabular*}
\caption{'''+caption+r'''}
\end{table}\end{document}
'''
    (folder/'数据概览.tex').write_text(tex,encoding='utf-8')
    for ext in ['pdf','tex']:
        previous=target/('数据概览.'+ext)
        if previous.exists():
            backup=folder/'previous';backup.mkdir(exist_ok=True)
            shutil.copy2(previous,backup/(datetime.now().strftime('%Y%m%d_%H%M%S')+'.'+ext))
        shutil.copy2(folder/('数据概览.'+ext),previous)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    data={'AgentDojo':agentdojo(),'ASB':asb(),'合成数据':synthetic()}
    common=('User 为不同用户任务数；Injection* 为独立攻击任务或模板数；Pairs 为实际评测的任务—攻击组合数。'
            'Avg. Traj. 为每个用户任务的参考工具调用步数；Avg. App. 为参考轨迹涉及的不同应用/服务数。')
    captions={
      'AgentDojo':'AgentDojo v1.2.2 实际评测子集概览。'+common+'攻击任务按环境内的 injection task ID 去重；参考轨迹来自官方 ground_truth，应用/服务按工具所属客户端模块去重（如邮件、日历、云盘）。Tools 为环境可用工具数；Overall 的平均量均按用户任务加权，不按攻击组合重复计数。',
      'ASB':'ToolSafe-ASB 实际评测子集概览。'+common+'攻击任务按代理类别与 attack ID 联合去重；每类四个攻击与该类用户任务组合评测。每次执行可见两个正常工具与一个攻击工具。源任务未提供标准参考动作序列及应用归属映射，这两项标为“—”，表示未定义而非零。',
      '合成数据':'合成工具调用数据集概览。'+common+'Injection* 在此统计攻击模板类别：目标重定向、载荷替换和伪造审批，共三类；同类模板可跨领域使用，因此 Overall 去重计数。104 个用户任务各有一个干净场景和一个攻击场景。六个领域共用六个参数化工具接口。当前版本未定义独立于防御策略的标准参考轨迹及跨应用映射，两项参考统计标为“—”。'}
    summary=[]
    for name,rs in data.items():
        overall=aggregate(rs);cells=[]
        for r in rs+[overall]:
            cells.append([r['domain'],fmt(r['tools']) if r['domain']=='Overall' else str(r['tools']),str(r['tasks']),str(len(r['injections'])),str(r['attacks']),fmt(mean(r['reference_lengths'])),fmt(mean(r['applications']))])
        title={'AgentDojo':'Overview of the Evaluated AgentDojo Subset','ASB':'Overview of the Evaluated ASB Subset','合成数据':'Overview of the Synthetic Tool-Agent Dataset'}[name]
        render(name,title,cells,captions[name])
        summary.append(['Synthetic' if name=='合成数据' else name,str(len(rs)),fmt(overall['tools']),str(overall['tasks']),str(len(overall['injections'])),str(overall['attacks']),fmt(mean(overall['reference_lengths'])),fmt(mean(overall['applications']))])
    caption=('三套数据集在本文实际评测范围内的概览。Domains 为环境或代理类别数；Avg. Tools 为每个用户任务可见的平均工具数，'
             '按用户任务加权，ASB 包含每次执行注入的一个攻击工具。'+common+
             '* AgentDojo、ASB 按环境/代理内的攻击任务 ID 去重；Synthetic 按三类攻击模板去重，并实例化为 104 个攻击场景，因此该列不直接比较攻击丰富度。'
             '参考统计取 AgentDojo 官方 ground_truth，应用/服务按工具所属客户端模块区分，均按用户任务平均。ASB 与合成数据尚无对应标准参考序列和应用映射，标为“—”。各行均为本文实际评测范围。')
    render('总览','Overview of the Evaluated Datasets',summary,caption,summary=True)
    paths=[ROOT/'release_assets/agentdojo_deepseek_main_raw.zip',ROOT/'release_assets/asb_and_margin_raw.zip',ROOT/'data/workflow_catalog_104/cases.jsonl',ROOT/'results/summaries/catalog_fixed104_adapter_v11_104/rows.jsonl']
    catalog.dump(OUT/'audit.json',{'datasets':data,'summary':summary,'api_requests':0,'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}})
    print(json.dumps(summary))


if __name__=='__main__':main()
