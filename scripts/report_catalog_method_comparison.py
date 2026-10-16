"""Merge independent baseline batches and audit all 1,248 outcome traces."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import run_catalog_other_methods as baseline

ROOT = baseline.ROOT


def main():
    pairs, model = baseline.catalog.prepare()
    pairs += baseline.added_pairs(pairs)
    cases = {c['id']: c for p in pairs for c in p}
    sources = [ROOT/'results/summaries'/name for name in (
        'catalog_baseline_matrix_104', 'catalog_policy_baseline_matrix_104')]
    indexed = {}
    for source in sources:
        path = source/'rows.jsonl'
        if not path.exists(): continue
        for row in map(json.loads, path.read_text().splitlines()):
            key = (row['id'],row['arm'])
            if key in indexed:
                # DAFR/No Defense and pilot rows are deliberately reused in both
                # batches, and must represent the same recorded execution.
                old = indexed[key]
                for field in ('task_completed','attack_success','trace','tool_calls','llm_calls'):
                    assert old[field] == row[field], (key,field)
            else: indexed[key]=row
    rows = list(indexed.values())
    assert all(r['id'] in cases for r in rows)
    for row in rows:
        if row['arm'] in baseline.METHODS:
            baseline.audit(cases[row['id']],row)
        else:
            copied=deepcopy(row)
            if copied['arm']=='no_defense': copied['arm']='no_geometry'
            baseline.dafr_replay(cases[row['id']],copied,model)
    out=ROOT/'results/summaries/catalog_method_comparison_104'
    out.mkdir(parents=True,exist_ok=True)
    result=baseline.summarize(rows,list(cases.values()),out,baseline.METHODS)
    complete=len(rows)==1248 and all(r['clean_n']==r['attack_n']==104 for r in result)
    baseline.catalog.dump(out/'audit.json',{'complete':complete,'replayed_episodes':len(rows),'errors':0})
    baseline.catalog.dump(out/'provenance.json',{'inputs':{
        str(s.relative_to(ROOT)):hashlib.sha256((s/'rows.jsonl').read_bytes()).hexdigest()
        for s in sources if (s/'rows.jsonl').exists()},
        'note':'Pilot and reused DAFR/No Defense executions deduplicated by case and method; all outcome traces replayed.'})
    if not complete:
        print(json.dumps({'complete':False,'episodes':len(rows),'rows':result}));return
    full=next(r for r in result if r['method']=='full')
    no=next(r for r in result if r['method']=='no_defense')
    checks={'DAFR_best_UA':all(full['UA']>=r['UA'] for r in result),
            'DAFR_lowest_ASR':all(full['ASR']<=r['ASR'] for r in result),
            'baselines_vs_no_defense':{r['method']:{
                'UA_gain':r['UA']-no['UA'],'ASR_reduction':no['ASR']-r['ASR']}
                for r in result if r['method'] in baseline.METHODS}}
    baseline.catalog.dump(out/'comparison_checks.json',checks)
    labels={'no_defense':'No Defense','piguard':'PIGuard','protectai':'ProtectAI',
            'progent':'Progent','drift':'DRIFT','full':'DAFR'}
    paper=ROOT/'paper/supplement'
    tex=r'''% Generated from 1,248 audited tool-agent episodes.
\begin{table}[!ht]
\centering\small
\setlength{\tabcolsep}{8pt}
\resizebox{\linewidth}{!}{%
\begin{tabular}{lrrrr}
\toprule
Defense & CU (\%) $\uparrow$ & UA (\%) $\uparrow$ & ASR (\%) $\downarrow$ & Total Tool Calls \\
\midrule
'''
    for r in result:
        name=labels[r['method']]
        if r['method']=='full':tex+=r'\rowcolor{black!12}\textbf{DAFR}'
        else:tex+=name
        tex+=f" & {r['CU']:.1f} & {r['UA']:.1f} & {r['ASR']:.1f} & {r['total_tool_calls']} " + r'\\'+'\n'
    tex+=r'''\bottomrule
\end{tabular}}
\caption{Defense comparison on 104 paired synthetic tool-agent tasks across six domains with DeepSeek-v4-flash-0731. All methods run the same 104 clean and 104 attacked episodes with matched tools and execution budgets. CU and UA measure correct task completion, and ASR measures concrete attacker-goal attainment. Total tool calls include denied submissions.}
\label{tab:synthetic-method-comparison}
\end{table}
'''
    (paper/'DAFR_Custom_Dataset_Method_Comparison.tex').write_text(tex,encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'Times New Roman','pdf.fonttype':42})
    fig,ax=plt.subplots(figsize=(10,4));ax.axis('off')
    values=[[labels[r['method']],f"{r['CU']:.1f}",f"{r['UA']:.1f}",f"{r['ASR']:.1f}",str(r['total_tool_calls'])] for r in result]
    table=ax.table(cellText=values,colLabels=['Defense','CU (%) ↑','UA (%) ↑','ASR (%) ↓','Total Tool Calls'],
        colWidths=[.32,.16,.16,.16,.20],cellLoc='right',bbox=[0,.20,1,.78])
    table.auto_set_font_size(False);table.set_fontsize(13)
    for (i,j),cell in table.get_celld().items():
        cell.set_edgecolor('white')
        if j==0:cell.set_text_props(ha='left')
        if i==6:cell.set_facecolor('#e5e5e5');cell.set_text_props(weight='bold')
    for y in (.98,.869,.20):ax.plot([0,1],[y,y],transform=ax.transAxes,color='black',lw=1)
    ax.text(0,.14,'104 paired tasks; 104 clean and 104 attacked episodes per method. DeepSeek-v4-flash-0731.\n'
        'CU/UA: correct task completion. ASR: concrete attacker-goal attainment. Tool calls include denied submissions.',
        transform=ax.transAxes,fontsize=10,va='top')
    fig.subplots_adjust(left=.04,right=.96,top=.96,bottom=.06)
    fig.savefig(paper/'DAFR_Custom_Dataset_Method_Comparison.pdf');plt.close(fig)
    print(json.dumps({'complete':True,'rows':result,'checks':checks}))


if __name__=='__main__':main()
