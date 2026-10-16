"""Freeze and audit six distinct workflows before any live model evaluation."""
from copy import deepcopy
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from heterogeneous_benchmark.fixtures import build_cases
from heterogeneous_benchmark.world import NativeWorld, TOOLS
from heterogeneous_benchmark.guard import decide, ARMS

DATA=ROOT/'data/heterogeneous_native_pilot_v1'
OUT=ROOT/'results/summaries/heterogeneous_native_pilot_v1'


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def reference_audit(case,arm='full'):
    world=NativeWorld(case);unsafe=False
    for step in case['reference']:
        n,a=step['tool'],step['arguments']
        allowed,detail=decide(TOOLS[n],n,a,world.receipts,world.claims,arm)
        assert allowed,(case['id'],n,detail)
        response=world.call(n,a)
        assert 'error' not in response,(case['id'],n,response)
        unsafe |= world.outcome()['unsafe_state']
    result=world.outcome()
    assert result['task_completed'] and not unsafe,(case['id'],result)
    return {'id':case['id'],'arm':arm,'reference_calls':world.calls,'attack_exposures':len(world.exposures),'completed':True,'unsafe':False}


def targeted_audit(case):
    """Counterfactual admission check, not an LLM performance result."""
    action=case['attacker_action'];world=NativeWorld(case)
    for step in case['reference']:
        if step['tool']==action['tool']:break
        result=world.call(step['tool'],step['arguments'])
        assert 'error' not in result
    decisions={arm:decide(TOOLS[action['tool']],action['tool'],action['arguments'],world.receipts,world.claims,arm)[0] for arm in ARMS}
    allowed_response=world.call(action['tool'],action['arguments'])
    assert 'error' not in allowed_response,(case['id'],allowed_response)
    assert world.outcome()['unsafe_state'],case['id']
    return {'id':case['id'],'admission_allowed':decisions,'unsafe_action_physically_executable':True}


def main():
    cases=build_cases();DATA.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    content=''.join(json.dumps(c,ensure_ascii=False,sort_keys=True)+'\n' for c in cases)
    target=DATA/'cases.jsonl'
    if target.exists() and target.read_text(encoding='utf-8')!=content:
        raise RuntimeError('Frozen fixtures differ: create a new dataset version instead of overwriting.')
    refs=[reference_audit(c,arm) for c in cases for arm in ARMS]
    probes=[targeted_audit(c) for c in cases if c['variant']!='clean']
    clean=[c for c in cases if c['variant']=='clean']
    fingerprints=[];stats=[]
    for c in clean:
        signature={'tools':[s['tool'] for s in c['reference']],'dependencies':c['dependency_edges']}
        fingerprint=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest();fingerprints.append(fingerprint)
        for i,j in c['dependency_edges']:assert 0<=i<j<len(c['reference'])
        variants=[v for v in cases if v['task_id']==c['task_id'] and v['variant']!='clean']
        stats.append({'task_id':c['task_id'],'domain':c['domain'],'family':c['family'],'tools':len(c['tools']),
            'reference_calls':len(c['reference']), 'reference_services':len({TOOLS[s['tool']]['service'] for s in c['reference']}),
            'write_calls':sum(TOOLS[s['tool']]['write'] for s in c['reference']),
            'injection_variants':len(variants),'injection_sites':[len(v['injections']) for v in variants],
            'dependency_edges':len(c['dependency_edges']),'structural_sha256':fingerprint})
    assert len(fingerprints)==len(set(fingerprints))==6
    overlaps=[]
    for i,a in enumerate(clean):
        for b in clean[i+1:]:
            aa={x['tool'] for x in a['reference']};bb={x['tool'] for x in b['reference']}
            overlaps.append({'a':a['task_id'],'b':b['task_id'],'reference_tool_jaccard':len(aa&bb)/len(aa|bb)})
    target.write_text(content,encoding='utf-8')
    sources=[ROOT/'src/heterogeneous_benchmark'/f for f in ['world.py','fixtures.py','guard.py']]
    protocol={'status':'development pilot; not final benchmark','user_tasks':6,'attack_variants':12,'total_scenarios':18,
        'dataset_sha256':hashlib.sha256(content.encode()).hexdigest(),
        'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        'reference_length':'hand-authored feasible tool sequence, audited against state; not claimed shortest or observed LLM length',
        'deduplication':'unique native-tool sequence and dependency DAG; all pairwise tool-overlap values retained',
        'attack_counts':'configured injections and actual exposures recorded separately',
        'fairness':'same tools, observations, state transitions and budgets for all arms; independent verification always accessible',
        'controller':'existing relational_dafr.controller.surface_risk with new generic native-argument adapter; not claimed identical to archived benchmark adapters',
        'risk_inputs':'fixed declared stress coordinates in tool contracts; not empirically estimated probabilities',
        'ablation':'remove provenance filtering, scoped argument binding, or geometric admission; no performance target used by evaluator',
        'expansion':'review first live task before adding task families; retain all completed runs and errors',
        'observed_trajectory_audit':'distinct-tool sequence, length and similarity measured after live runs; structural uniqueness does not guarantee unique model trajectories'}
    dump(DATA/'protocol.json',protocol);dump(OUT/'structure.json',{'statistics':stats,'pairwise_overlap':overlaps,'reference_checks':refs,'counterfactual_checks':probes})
    labels={'invoice':'付款与记账','return':'退货、退款与库存','report':'报告脱敏与发送','meeting':'文档权限与会议邀请','rollout':'灰度发布与健康检查','recovery':'快照保护与故障恢复'}
    table=''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in [r['task_id'],labels[r['family']],r['tools'],r['reference_calls'],r['reference_services'],r['write_calls'],' / '.join(map(str,r['injection_sites']))])+'</tr>' for r in stats)
    cards=[]
    for c in clean:
        steps=' → '.join(s['tool'] for s in c['reference'])
        cards.append('<section><h2>'+c['task_id']+' '+labels[c['family']]+'</h2><p>'+html.escape(c['task'])+'</p><p class="flow">'+html.escape(steps)+'</p><p>攻击目标：'+html.escape(c['attacker_goal'])+'</p><p>注入入口：'+', '.join(c['injection_sites'])+'</p></section>')
    page='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>新版异构任务首批审阅</title><style>body{max-width:1100px;margin:40px auto;font:16px/1.7 "Microsoft YaHei",sans-serif;color:#233044}table{width:100%;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid #ddd;text-align:left}th{background:#eef2f8}section{margin-top:24px;padding:18px;border:1px solid #dce3eb;border-radius:10px}.flow{background:#f2f5f8;padding:12px;font:14px/1.8 Consolas,monospace}h1{font-size:26px}</style><h1>新版异构工具环境：首批 6 个独立任务</h1><p>这是开发验证批次。每个任务有 1 个干净版本、2 个攻击版本，共 18 个场景。表中链长为已执行验证的参考流程，不是模型实测轨迹，也不保证最短。相同任务的配对版本共享业务环境。</p><table><tr><th>任务</th><th>流程</th><th>可用工具</th><th>参考调用</th><th>涉及服务</th><th>写操作</th><th>两版注入点数</th></tr>'''+table+'</table>'+''.join(cards)+'<p>各方法均可主动查询独立权威来源，环境没有“先被防御拒绝才开放核验”的门槛。结构检查与消融效果分别报告。</p></html>'
    (OUT/'首批任务审阅.html').write_text(page,encoding='utf-8')
    print(json.dumps({'reference_checks':len(refs),'counterfactual_checks':len(probes),'statistics':stats},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
