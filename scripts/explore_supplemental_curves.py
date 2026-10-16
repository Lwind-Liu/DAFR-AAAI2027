"""Offline threshold diagnostic and measured chain-cost curves; no API calls."""
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import shutil
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import run_workflow_catalog_v2 as catalog
from render_geometry_booktabs import wrap_measured

ROOT=catalog.ROOT
OUT=ROOT/'results/summaries/supplemental_curve_exploration'
DESKTOP=Path('C:/Users/Administrator/Desktop/表')


def csv_save(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def deliver(fig,name,caption,axes_tex):
    dest=DESKTOP/name;dest.mkdir(parents=True,exist_ok=True)
    fig.savefig(OUT/(name+'.png'),dpi=220,bbox_inches='tight',pad_inches=.12)
    fp=FontProperties(fname='C:/Windows/Fonts/simsun.ttc',size=9)
    fig.text(.06,-.04,wrap_measured(fig,caption,fp,fig.bbox.width*.9),va='top',fontproperties=fp,linespacing=1.4)
    fig.savefig(OUT/(name+'.pdf'),bbox_inches='tight',pad_inches=.12)
    fig.savefig(OUT/(name+'_preview.png'),dpi=150,bbox_inches='tight',pad_inches=.12)
    plt.close(fig)
    tex=r'''% XeLaTeX. Editable vector plot; data embedded.
\documentclass[UTF8]{ctexart}
\usepackage[a4paper,landscape,margin=18mm]{geometry}
\usepackage{fontspec,pgfplots,caption}
\pgfplotsset{compat=1.18}\setmainfont{Times New Roman}\pagestyle{empty}
\definecolor{curveblue}{HTML}{287FA1}\definecolor{curveorange}{HTML}{EF8A32}
\begin{document}\begin{figure}[ht]\centering
'''+axes_tex+r'''
\caption{'''+caption.replace('%',r'\%')+r'''}
\end{figure}\end{document}
'''
    (OUT/(name+'.tex')).write_text(tex,encoding='utf-8')
    for ext in ['pdf','png','tex']:shutil.copy2(OUT/(name+'.'+ext),dest/(name+'.'+ext))


def threshold():
    path=ROOT/'data/workflow_catalog_104/cases.jsonl'
    cases=[json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
    snapshots=[]
    for case in cases:
        world=catalog.CatalogWorld(case)
        world.call('read_request',{'request_id':case['request_id']})
        view=world.observer_view('OP-1')
        correct=all(view['draft'][field]==case['expected'][field] for field in ('destination','payload'))
        snapshots.append({'id':case['id'],'group_id':case['group_id'],'variant':case['variant'],
                          'correct_parameters':correct,'view':view})
    assert len(snapshots)==208 and len({s['group_id'] for s in snapshots})==104
    positives=sum(s['correct_parameters'] for s in snapshots);negatives=len(snapshots)-positives
    rows=[];decisions=[]
    # Fixed grid across the default threshold, all cases included.
    thresholds=sorted(set([i/100 for i in range(31)]+[.225,.245]))
    for tau in thresholds:
        good_admitted=bad_blocked=0
        for s in snapshots:
            view=deepcopy(s['view']);view['policy']['risk_metadata']['budget']=tau
            allowed,_=catalog.admit(view,'full')
            good_admitted+=bool(allowed and s['correct_parameters'])
            bad_blocked+=bool(not allowed and not s['correct_parameters'])
            decisions.append({'id':s['id'],'threshold':tau,'allowed':bool(allowed),'correct_parameters':s['correct_parameters']})
        rows.append({'threshold':tau,'correct_drafts':positives,'incorrect_drafts':negatives,
                     'correct_admitted':good_admitted,'incorrect_blocked':bad_blocked,
                     'correct_acceptance':100*good_admitted/positives,'incorrect_rejection':100*bad_blocked/negatives})
    csv_save(OUT/'threshold_metrics.csv',rows)
    catalog.dump(OUT/'threshold_snapshots.json',snapshots)
    catalog.dump(OUT/'threshold_decisions.json',decisions)
    fig,ax=plt.subplots(figsize=(7.4,4.5));fig.subplots_adjust(bottom=.18,left=.13,right=.96,top=.94)
    specs=[('correct_acceptance','Correct-draft acceptance','#287FA1','o','curveblue'),
           ('incorrect_rejection','Incorrect-draft rejection','#EF8A32','s','curveorange')]
    plots=[]
    for key,label,color,mark,texcolor in specs:
        ax.plot([r['threshold'] for r in rows],[r[key] for r in rows],color=color,marker=mark,markersize=3.5,linewidth=1.8,label=label)
        coords=' '.join(f"({r['threshold']},{r[key]:.8f})" for r in rows)
        plots.append(r'\addplot[thick,color='+texcolor+',mark='+('*' if mark=='o' else 'square*')+'] coordinates {'+coords+'};'+r'\addlegendentry{'+label+'}')
    ax.axvline(.2,color='#777777',linestyle='--',linewidth=1)
    ax.text(.197,53,'Default = 0.20',rotation=90,ha='right',color='#555555',fontsize=10)
    ax.set(xlabel='Joint-risk threshold',ylabel='Rate (%)',xlim=(0,.305),ylim=(-2,105))
    ax.set_xticks([0,.05,.1,.15,.2,.25,.3]);ax.set_yticks(range(0,101,20));ax.grid(color='#e1e1e1',linewidth=.7)
    ax.legend(loc='lower left',fontsize=10,framealpha=.95)
    caption=('联合风险阈值的准入层敏感性分析。对固定 104 个任务的干净／攻击配对场景，共 208 个初始草稿，'
             '保持动作、证据、半空间约束及场景风险输入不变，仅改变联合风险阈值。依据独立的批准参数标注，'
             '其中 143 个草稿参数正确、65 个参数错误；正确参数放行率和错误参数拦截率分别在这两组内计算。'
             '默认阈值 0.20 时，两者分别为 91.6% 和 95.4%；在 0.10–0.225 的所测阈值点上结果相同。'
             '这是首次提交前的离线准入诊断，未重跑代理的后续核验与恢复，指标不等同于 CU、UA 或 ASR；风险输入沿用原合成场景的声明值。')
    axis=r'''\begin{tikzpicture}\begin{axis}[width=16cm,height=9cm,xmin=0,xmax=.305,ymin=-2,ymax=105,
xlabel={Joint-risk threshold},ylabel={Rate (\%)},grid=major,legend pos=south west]
'''+ '\n'.join(plots)+r'''
\addplot[dashed,gray,forget plot] coordinates {(.2,0) (.2,100)};
\end{axis}\end{tikzpicture}'''
    deliver(fig,'阈值敏感性',caption,axis)
    return rows


def chain_cost():
    path=ROOT/'results/summaries/ustc_chain_pilot_v1/rows.jsonl'
    episodes=[json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
    assert len(episodes)==12
    rows=[]
    for length in [1,2,4]:
        for arm in ['no_defense','full']:
            sub=[r for r in episodes if r['length']==length and r['arm']==arm]
            assert len(sub)==2
            for r in sub:assert all(isinstance(t.get('usage'),dict) for t in r['trace'])
            rows.append({'length':length,'arm':arm,'n':2,'tool_calls':statistics.mean(r['tool_calls'] for r in sub),
                'tokens':statistics.mean(sum(t['usage']['total_tokens'] for t in r['trace']) for r in sub),
                'UA':100*statistics.mean(r['task_completed'] for r in sub),'ASR':100*statistics.mean(r['attack_success'] for r in sub)})
    csv_save(OUT/'chain_cost_metrics.csv',rows)
    fig,axes=plt.subplots(1,2,figsize=(10.4,4.1));fig.subplots_adjust(left=.07,right=.97,bottom=.18,top=.82,wspace=.28)
    tex=[]
    for ax,key,ylabel in zip(axes,['tool_calls','tokens'],['Tool calls per task','Total tokens per task (thousands)']):
        plots=[]
        for arm,label,color,mark,tc in [('no_defense','No Defense','#287FA1','o','curveblue'),('full','DAFR','#EF8A32','s','curveorange')]:
            rs=[r for r in rows if r['arm']==arm];ys=[r[key]/(1000 if key=='tokens' else 1) for r in rs]
            ax.plot([1,2,4],ys,color=color,marker=mark,label=label,linewidth=1.8)
            for x,y in zip([1,2,4],ys):ax.annotate(f'{y:.1f}',(x,y),xytext=(0,7),textcoords='offset points',ha='center',fontsize=10,color=color)
            coords=' '.join(f'({x},{y})' for x,y in zip([1,2,4],ys))
            plots.append(r'\addplot[thick,color='+tc+',mark='+('*' if mark=='o' else 'square*')+'] coordinates {'+coords+'};'+r'\addlegendentry{'+label+'}')
        ax.set(xlabel='Business-chain length',ylabel=ylabel,xlim=(.8,4.25),ylim=(0,38 if key=='tool_calls' else 155));ax.set_xticks([1,2,4]);ax.grid(color='#dddddd',linewidth=.7)
        tex.append(r'\begin{tikzpicture}\begin{axis}[width=10.5cm,height=8cm,xmin=.8,xmax=4.25,ymin=0,xtick={1,2,4},xlabel={Business-chain length},ylabel={'+ylabel+r'},grid=major,legend pos=north west]'+ '\n'.join(plots)+r'\end{axis}\end{tikzpicture}')
    fig.legend(*axes[0].get_legend_handles_labels(),loc='upper center',ncol=2,frameon=False)
    caption=('同类任务不同业务链长的开销试验。科大 API 的 deepseek-v4-flash-ascend，在付款、文档授权两个实例上，'
             '分别执行 1、2、4 个依次解锁的业务操作；每个点为两个实例的平均值，总计 12 次执行。'
             '每条链仅在最后一个操作放置攻击，调用预算按链长同比增加。DAFR 平均工具调用数为 9、16.5、31，'
             '平均输入加输出 token 数为 20.3k、49.4k、130.4k。工具交互随链长近似线性增长，累计 token 增长更快。'
             'DAFR 六次均完成原任务并阻止攻击；No Defense 六次均任务失败且攻击成功。两条开销曲线对应不同质量的执行结果，不能据此视为等效任务完成的效率比较。')
    deliver(fig,'链长开销',caption,'\n'.join(tex))
    return rows


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'Times New Roman','font.size':12,'pdf.fonttype':42})
    thresholds=threshold();cost=chain_cost()
    sources=[Path(__file__),ROOT/'data/workflow_catalog_104/cases.jsonl',ROOT/'results/summaries/ustc_chain_pilot_v1/rows.jsonl',
             ROOT/'src/workflow_benchmark/defense.py',ROOT/'src/workflow_benchmark/repair_feedback.py',ROOT/'src/relational_dafr/controller.py',
             ROOT/'scripts/run_workflow_catalog_v2.py',ROOT/'scripts/run_queued_workflow_case.py']
    catalog.dump(OUT/'audit.json',{'api_requests':0,'threshold_metrics':thresholds,'chain_cost_metrics':cost,
                 'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}})
    print(json.dumps({'threshold_default':next(r for r in thresholds if r['threshold']==.2),'chain_cost':cost}))


if __name__=='__main__':main()
