"""Dataset overview for the writer, calculated from fixed cases and traces."""
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

ROOT=catalog.ROOT
OUT=ROOT/'results/summaries/synthetic_dataset_overview'
DEST=Path('C:/Users/Administrator/Desktop/表/数据概览')


def main():
    OUT.mkdir(parents=True,exist_ok=True);DEST.mkdir(parents=True,exist_ok=True)
    dp=ROOT/'data/workflow_catalog_104/cases.jsonl'
    rp=ROOT/'results/summaries/catalog_fixed104_adapter_v11_104/rows.jsonl'
    cases=[json.loads(s) for s in dp.read_text(encoding='utf-8').splitlines()]
    records=[json.loads(s) for s in rp.read_text(encoding='utf-8').splitlines()]
    catalog.configure_runner()
    toolnames=[t['function']['name'] for t in catalog.runner.schemas()]
    rows=[]
    for domain,label in [('payment','Payment'),('email','Email'),('documents','Documents'),
                         ('calendar','Calendar'),('crm','CRM'),('cloud','Cloud'),(None,'Overall')]:
        cs=[c for c in cases if domain is None or c['domain']==domain]
        clean=[c for c in cs if c['variant']=='clean'];attack=[c for c in cs if c['variant']=='attack']
        ids={c['id'] for c in clean}
        rs=[r for r in records if r['arm']=='full' and r['id'] in ids]
        assert len(rs)==len(ids)==len(clean)==len(attack)
        assert {r['id'] for r in rs}==ids
        assert all(r['termination'] not in ('api_error','infrastructure_error','budget_exhausted') for r in rs)
        rows.append({'domain':label,'tools':len(toolnames),'user_tasks':len(clean),'attack_cases':len(attack),
                     'mean_tool_calls':sum(r['tool_calls'] for r in rs)/len(rs),
                     'total_tool_calls':sum(r['tool_calls'] for r in rs)})
    caption=('合成工具调用数据集概览。数据集覆盖付款、邮件、文档授权、日程、客户信息与云端发布六个领域，'
             '共 104 个用户任务；每个任务包含一个干净场景和一个攻击场景，每种配置共执行 208 次。'
             'Tools 为可用工具接口数，六个领域共用同一套 6 个参数化接口，Overall 按去重后的接口数统计。'
             'Attack Cases 为配对攻击场景数，不是攻击类型数。Avg. Calls 为 DeepSeek V4 Flash（0731）运行完整 DAFR 时，'
             '104 次干净执行的平均工具调用数，包含核验与被拦截的有效请求，并纳入成功和失败执行；Overall 按任务数加权。'
             '该列描述实测执行开销，未将其视为任务的最短参考轨迹长度。')
    plt.rcParams.update({'font.family':'Times New Roman','font.size':15,'pdf.fonttype':42})
    fig=plt.figure(figsize=(9.0,5.6));ax=fig.add_axes([.07,.34,.86,.58]);ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
    x=[.02,.32,.51,.70,.91]
    ax.text(.5,1.06,'Overview of the Synthetic Tool-Agent Dataset',ha='center',fontsize=16)
    ax.text(.605,.94,'Tasks',ha='center');ax.text(.91,.94,'Statistics',ha='center')
    ax.plot([.42,.79],[.885,.885],color='black',lw=.7);ax.plot([.82,1],[.885,.885],color='black',lw=.7)
    for pos,label in zip(x,['Domain','Tools','User','Attack','Avg. Calls']):
        ax.text(pos,.825,label,ha='left' if pos==x[0] else 'center',va='center')
    ax.plot([0,1],[1,1],color='black',lw=1.4);ax.plot([0,1],[.76,.76],color='black',lw=.8)
    for i,r in enumerate(rows):
        y=.70-i*.098
        vals=[r['domain'],str(r['tools']),str(r['user_tasks']),str(r['attack_cases']),f"{r['mean_tool_calls']:.2f}"]
        if r['domain']=='Overall':ax.plot([0,1],[y+.05,y+.05],color='black',lw=.7)
        for j,(pos,val) in enumerate(zip(x,vals)):
            ax.text(pos,y,val,ha='left' if j==0 else 'center',va='center',fontweight='bold' if r['domain']=='Overall' else 'normal')
    ax.plot([0,1],[.05,.05],color='black',lw=1.4)
    fp=FontProperties(fname='C:/Windows/Fonts/simsun.ttc',size=10)
    fig.canvas.draw();fig.text(.07,.30,wrap_measured(fig,caption,fp,fig.bbox.width*.86),fontproperties=fp,va='top',linespacing=1.5)
    fig.savefig(OUT/'数据概览.pdf',bbox_inches='tight',pad_inches=.12)
    fig.savefig(OUT/'preview.png',dpi=160,bbox_inches='tight',pad_inches=.12);plt.close(fig)
    body=[]
    for r in rows:
        if r['domain']=='Overall':body.append(r'\midrule')
        vals=[r['domain'],str(r['tools']),str(r['user_tasks']),str(r['attack_cases']),f"{r['mean_tool_calls']:.2f}"]
        body.append(' & '.join(vals)+r' \\')
    tex=r'''% XeLaTeX. Editable table.
\documentclass[UTF8]{ctexart}
\usepackage[a4paper,margin=20mm]{geometry}
\usepackage{fontspec,booktabs,caption}
\setmainfont{Times New Roman}\pagestyle{empty}
\begin{document}\begin{table}[ht]\centering
{\large Overview of the Synthetic Tool-Agent Dataset}\par\medskip
\renewcommand{\arraystretch}{1.2}
\begin{tabular*}{.95\linewidth}{@{\extracolsep{\fill}}lcccc@{}}
\toprule
 & & \multicolumn{2}{c}{Tasks} & Statistics \\
\cmidrule(lr){3-4}\cmidrule(l){5-5}
Domain & Tools & User & Attack & Avg. Calls \\
\midrule
'''+ '\n'.join(body)+r'''
\bottomrule\end{tabular*}
\caption{'''+caption+r'''}
\label{tab:synthetic-dataset-overview}
\end{table}\end{document}
'''
    (OUT/'数据概览.tex').write_text(tex,encoding='utf-8')
    (OUT/'audit.json').write_text(json.dumps({'rows':rows,'tools':toolnames,'api_requests':0,
        'dataset_sha256':hashlib.sha256(dp.read_bytes()).hexdigest(),'records_sha256':hashlib.sha256(rp.read_bytes()).hexdigest()},indent=2),encoding='utf-8')
    for ext in ['pdf','tex']:shutil.copy2(OUT/('数据概览.'+ext),DEST/('数据概览.'+ext))
    print(json.dumps(rows))


if __name__=='__main__':main()
