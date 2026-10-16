"""Readable pilot progress from retained raw episodes, without result selection."""
import csv
import html
import json
from pathlib import Path
import shutil

from build_heterogeneous_pilot import ROOT, DATA, OUT, dump
from run_heterogeneous_pilot import summarize, apply
from heterogeneous_benchmark.world import NativeWorld
from heterogeneous_benchmark.evaluation import attacker_goal_achieved


def main():
    cases=[json.loads(s) for s in (DATA/'cases.jsonl').read_text(encoding='utf-8').splitlines()]
    by_id={c['id']:c for c in cases}
    reports=[]
    for run in sorted(OUT.glob('live_*')):
        if not (run/'protocol.json').exists():continue
        protocol=json.loads((run/'protocol.json').read_text(encoding='utf-8'))
        rows=[json.loads(p.read_text(encoding='utf-8')) for p in run.glob('HET*.json') if '.partial.' not in p.name]
        if not rows:continue
        scored=[]
        for row in rows:
            case=by_id[row['id']];world=NativeWorld(case);success=False
            for step in row['trace']:
                response,decision,_=apply(world,step['tool'],step['arguments'],row['arm'])
                assert response==step['response'] and decision==step['decision']
                success |= attacker_goal_achieved(case['family'],world.state)
            # Do not confuse generic unsafe execution with the specific attacker goal.
            row['attack_success']=case['variant']!='clean' and success
            row['scoring']='explicit attacker goal over every executed state transition'
            scored.append({k:row[k] for k in ('id','arm','task_completed','attack_success','unsafe_execution','scoring')})
        dump(run/'goal_scoring.json',scored)
        summary=summarize(rows,len(protocol['arms'])*len(protocol['case_ids']))
        dump(run/'summary.json',summary)
        reports.append((run,rows,summary))
    esc=lambda v:html.escape(str(v))
    blocks=[]
    labels={'full':'完整方法','no_projection':'去掉证据投影','no_lifting':'去掉动作—证据绑定','no_geometry':'去掉几何约束','no_defense':'No Defense'}
    for run,rows,summary in reports:
        block='<section><h2>'+esc(run.name)+'</h2><p>已留存 '+str(summary['recorded_episodes'])+'/'+str(summary['expected_episodes'])+' 次执行；API 中断或暂停 '+str(summary['api_error_episodes'])+' 次（单独记录，不计入效果指标）。</p>'
        if summary['metrics']:
            block+='<table><tr><th>配置</th><th>干净/攻击执行数</th><th>CU</th><th>UA</th><th>ASR</th><th>接触攻击的执行数</th></tr>'
            for m in summary['metrics']:
                vals=[labels[m['arm']],str(m['clean_n'])+'/'+str(m['attack_n'])]+['—' if m[k] is None else f'{m[k]:.1f}%' for k in ('CU','UA','ASR')]+[m['attack_reached_n']]
                block+='<tr>'+''.join('<td>'+esc(v)+'</td>' for v in vals)+'</tr>'
            block+='</table>'
        for row in sorted(rows,key=lambda r:(r['id'],r['arm'])):
            if row['termination'] in ('api_error','provider_stop'):continue
            block+='<details><summary>'+esc(row['id'])+' / '+esc(labels[row['arm']])+'：完成='+str(row['task_completed'])+'，攻击成功='+str(row['attack_success'])+'</summary>'
            for i,step in enumerate(row['trace'],1):
                block+='<p><b>Step '+str(i)+' · '+esc(step['tool'])+'</b><br>'+esc(json.dumps(step['arguments'],ensure_ascii=False))+'</p><pre>'+esc(json.dumps(step['response'],ensure_ascii=False,indent=2))+'</pre>'
            block+='</details>'
        block+='</section>';blocks.append(block)
    page=(OUT/'首批任务审阅.html').read_text(encoding='utf-8')
    page=page.replace('</html>','<h1>实测进度与完整轨迹</h1><p>参考流程检查与模型效果分开报告。这里保留成功、失败和 API 异常记录；小样本只用于调试，尚不作为最终消融结论。</p>'+''.join(blocks)+'</html>')
    page=page.replace('</style>','details{margin:12px 0;padding:10px;background:#f6f8fa}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}</style>')
    (OUT/'实验审阅.html').write_text(page,encoding='utf-8')
    desktop=Path('C:/Users/Administrator/Desktop/新版数据集')
    desktop.mkdir(parents=True,exist_ok=True)
    shutil.copy2(OUT/'实验审阅.html',desktop/'首批任务审阅.html')
    dump(OUT/'status.json',{'runs':[{'path':str(p.relative_to(ROOT)),**s} for p,_,s in reports]})
    print(json.dumps({'review':str(desktop/'首批任务审阅.html'),'runs':len(reports)},ensure_ascii=False))


if __name__=='__main__':main()
