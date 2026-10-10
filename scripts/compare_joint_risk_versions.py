"""Paired risk-only comparison; same typed evidence and verification loop.

The cone uses production RiskBudgetCone, with a shared causal-path adapter.
This compares risk forms, NOT the original production semantic pipeline.
Both union-law and cone-law worlds are evaluated; neither dataset is empirical.
"""
from collections import defaultdict
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from clafr.geometry import RiskBudgetCone
from clafr.schemas import FeatureVector
from relational_dafr.controller import active_paths, surface_risk
from relational_dafr.episodes import build_episodes, EpisodeRuntime
from relational_dafr import pipeline
from relational_dafr.worlds import expected_loss
from geometry_capacity.backends import calibrate
from run_relational_dafr_complete_ablation import feedback_training, dump

OUT=ROOT/'results/summaries/joint_risk_old_new_v1'


def path_vector(context):
    paths=active_paths(context)
    values=[context['severity']*math.prod(context['events'][e]['probability'] for e in set(p)) for p in paths]
    return np.array(values+[0.]*(4-len(values)))


def cone_control_loss(world):
    # Independent arithmetic policy evaluator: deliberately no calls to
    # RiskBudgetCone, surface_risk, active_paths, or controller grant helpers.
    risks=[]
    for p in world['paths']:
        covered=any(g['issuer']=='user' and g['effect']==world['action']['effect']
                    and g['field']==p['field'] and g['value']==world['action']['arguments'][p['field']]
                    and g['revision']==world['revision'] for g in world['grants'])
        if not covered:
            risks.append(math.prod(world['events'][e]['probability'] for e in set(p['events'])))
    return world['severity']*math.sqrt(sum(r*r for r in risks))


def cone_allowed(context,weights,threshold):
    c=pipeline.upper_context(context)
    values=path_vector(c)
    cone=RiskBudgetCone('risk_form_comparison',{f'path{i}':float(w) for i,w in enumerate(weights)},
                        {},float(threshold*c['budget']),'Shared path risks, cone-form budget','Verify exact scope')
    return cone.margin(FeatureVector.from_mapping({f'path{i}':float(v) for i,v in enumerate(values)})).slack>=0


def fit_cone(train,dev):
    def matrix(es):
        return np.array([path_vector(pipeline.upper_context(pipeline.extract_context(e['input'])))
                         / e['input']['policy']['risk_budget'] for e in es])
    # Stronger old-form control: fit nonnegative per-path weights on training,
    # with independent union-world labels. No test tuning or seed search.
    x,xd=matrix(train),matrix(dev)
    y=np.array([expected_loss(e['hidden_world'])>e['hidden_world']['budget']+1e-12 for e in train],float)
    yd=np.array([expected_loss(e['hidden_world'])>e['hidden_world']['budget']+1e-12 for e in dev])
    balance=np.where(y==1,.5/max(y.mean(),1e-6),.5/max(1-y.mean(),1e-6))
    def objective(theta):
        a=np.exp(theta[:4]);strength=np.exp(theta[4]);offset=theta[5]
        norm=np.sqrt(np.sum((x*a)**2,axis=1)+1e-24)
        score=strength*norm+offset
        return np.mean(balance*(np.logaddexp(0,score)-y*score))+.001*np.sum(theta[:5]**2)
    result=minimize(objective,np.array([0.,0.,0.,0.,0.,-1.]),method='L-BFGS-B',
                    bounds=[(-5,5)]*5+[(-20,20)],options={'maxiter':500})
    weights=np.exp(result.x[:4])
    scores=np.sqrt(np.sum((xd*weights)**2,axis=1))
    return {'weights':weights,'thresholds':{regime:calibrate(scores,yd,regime)
             for regime in ('weighted','safety_1pct')},
            'optimization':{'converged':bool(result.success),'message':str(result.message),'iterations':int(result.nit)}}


@contextmanager
def replace_joint(evaluator):
    original=pipeline.allows
    def judge(context,*args,**kwargs):return evaluator(context)
    pipeline.allows=judge
    try:yield
    finally:pipeline.allows=original


class PolicyRuntime(EpisodeRuntime):
    def __init__(self,episode,loss):
        super().__init__(episode)
        self.loss=loss

    def execute(self,action):
        if action!=self.episode['input']['action']:raise ValueError('Action changed')
        world=deepcopy(self.episode['hidden_world']);world['grants']=deepcopy(self.grants)
        value=self.loss(world)
        outcome={'committed':True,'policy_safe':value<=world['budget']+1e-12,
                 'expected_unauthorized_loss':value,'budget':world['budget']}
        self.executions.append(outcome)
        return outcome


def aggregate(rows):
    return {'cases':len(rows),'initial_errors':sum(r['initial_allowed']!=r['safe_original'] for r in rows),
            'safe_executions':sum(r['policy_safe'] for r in rows),
            'unsafe_executions':sum(r['committed'] and not r['policy_safe'] for r in rows),
            'verification_queries':sum(r['queries'] for r in rows)}


def paired_intervals(rows):
    groups=sorted({r['group'] for r in rows})
    indexed={(r['arm'],r['id']):r for r in rows}
    comparisons={}
    rng=np.random.default_rng(20261014)
    sampled=rng.integers(0,len(groups),(4000,len(groups)))
    for arm in sorted({r['arm'] for r in rows}-{'new_union_surface'}):
        bygroup=defaultdict(list)
        for old in rows:
            if old['arm']!=arm:continue
            new=indexed['new_union_surface',old['id']]
            bygroup[old['group']].append([float(new['policy_safe'])-float(old['policy_safe']),
               float(new['committed'] and not new['policy_safe'])-float(old['committed'] and not old['policy_safe'])])
        delta=np.array([np.mean(bygroup[g],axis=0) for g in groups])
        resampled=delta[sampled].mean(axis=1)
        comparisons[arm]={key:{'new_minus_old':float(delta[:,i].mean()),
                              'group_bootstrap_95pct':np.quantile(resampled[:,i],[.025,.975]).tolist()}
             for i,key in enumerate(('safe_execution_rate','unsafe_execution_rate'))}
    return comparisons


def main():
    # New diagnostic seed, untouched by the previous dataset's gate.
    episodes=build_episodes(seed=20261014)
    splits={s:[e for e in episodes if e['split']==s] for s in ('train','dev','test')}
    model=fit_cone(feedback_training(splits['train']),feedback_training(splits['dev']))
    arms={'new_union_surface':lambda c:surface_risk(pipeline.upper_context(c))<=c['budget']+1e-12,
          'old_cone_equal_weights':lambda c:cone_allowed(c,np.ones(4),1.)}
    for regime,threshold in model['thresholds'].items():
        arms['old_cone_fitted_'+regime]=lambda c,t=threshold:cone_allowed(c,model['weights'],t)
    OUT.mkdir(parents=True,exist_ok=True)
    dump(OUT/'protocol.json',{'scope':'Risk forms only, shared causal-path lifting and provenance/repair; cone is the native RiskBudgetCone implementation with a NEW adapter, not frozen old 45-D production policy.',
          'seed':20261014,'counts':{s:len(es) for s,es in splits.items()},'fitted_cone':model,
          'worlds':['Independently enumerated union-of-path causal risk','Independent quadratic cone-policy control'],
          'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                     [Path(__file__),ROOT/'src/clafr/geometry.py',*sorted((ROOT/'src/relational_dafr').glob('*.py'))]},
          'limitations':['Synthetic declared probabilities and explicit traces, no empirical calibration.',
                         'Union world intentionally matches the new risk law; cone control matches the old form.',
                         'Both arms share nonlinear path lifting; this is a favorable adaptation for the cone.',
                         'Controls diagnose model assumptions, not real-world superiority or universal geometry superiority.']})
    rows=[];results={}
    for world_name,loss in [('union_world',expected_loss),('cone_policy_control',cone_control_loss)]:
        subset=[]
        for e in splits['test']:
            for arm,evaluator in arms.items():
                with replace_joint(evaluator):r=pipeline.run_episode(e['input'],PolicyRuntime(e,loss))
                r.update(world=world_name,arm=arm,id=e['id'],group=e['group'],domain=e['domain'],
                         safe_original=loss(e['hidden_world'])<=e['hidden_world']['budget']+1e-12)
                subset.append(r)
        rows.extend(subset)
        results[world_name]={'test':{a:aggregate([r for r in subset if r['arm']==a]) for a in arms},
                'by_domain':{d:{a:aggregate([r for r in subset if r['arm']==a and r['domain']==d]) for a in arms}
                             for d in sorted({e['domain'] for e in splits['test']})},
                'paired_intervals':paired_intervals(subset)}
        print(world_name,json.dumps(results[world_name]['test']),flush=True)
    dump(OUT/'summary.json',results)
    (OUT/'rows.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
    lines=['# 新旧联合风险：同流程对照','',
           '仅替换联合风险判定，来源、授权、版本、误差区间、核验预算、字段顺序、动作和执行流程相同。',
           '旧形状调用原生 RiskBudgetCone，但使用新的共享因果路径适配器；不等于原版完整 45 维生产方法。',
           '独立新种子 20261014；训练/开发/测试按基础实例分组。旧锥形状提供等权及仅训练/开发校准的两个配置，训练包含核验后状态。','',
           '| 环境法则 | 风险方法 | 初始错误 | 安全完成 | 越界执行 |','|---|---|---:|---:|---:|']
    for world_name,res in results.items():
        for arm,r in res['test'].items():
            lines.append(f"| {world_name} | {arm} | {r['initial_errors']} | {r['safe_executions']} | {r['unsafe_executions']} |")
    lines+=['','两个环境法则各使用全部 1,200 条测试，不混合加权得出“全面更好”。联合概率环境与新法则一致、二次预算控制环境与旧形状一致，均为受控机制诊断。',
            '只有真实工具轨迹上的配对结果、干净任务效用、攻击成功率及必要消融支持收益且控制场景无重大退化，才足以考虑改变论文主线。API 自然语言测试尚未执行。','']
    (OUT/'comparison_report.md').write_text('\n'.join(lines),encoding='utf-8')


if __name__=='__main__':main()
