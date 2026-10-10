"""Fresh-seed full typed-evidence pipeline with grouped splits and real replies."""
from collections import defaultdict
from copy import deepcopy
import hashlib
from itertools import product, combinations
import json
from pathlib import Path
import sys
import numpy as np
import sklearn
from sklearn.tree import DecisionTreeClassifier

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from relational_dafr.episodes import build_episodes,EpisodeRuntime,oracle_recoverable
from relational_dafr.pipeline import extract_context,run_episode,allows
from relational_dafr.controller import features
from relational_dafr.worlds import safe,expected_loss
from geometry_capacity.backends import fit_linear,calibrate

OUT=ROOT/'results/summaries/relational_dafr_complete_v1'
DATA=ROOT/'data/relational_dafr_complete_v1'


def matrix(episodes):return np.array([features(extract_context(e['input'])) for e in episodes])


def feedback_training(episodes):
    """Only training/dev grants actually permitted within each query budget.

    Enumerate intermediate permitted sets to avoid disadvantaging learned
    baselines by withholding post-verification states from their training.
    Labels still come from independent hidden execution worlds.
    """
    expanded=[]
    for e in episodes:
        expanded.append(e)
        available=e['verification_ledger']
        cap=e['input']['policy']['verification_query_budget']
        for n in range(1,min(len(available),cap)+1):
            for fields in combinations(available,n):
                c=deepcopy(e)
                runtime=EpisodeRuntime(c)
                for field in fields:
                    c['input']['records'].append(runtime.verify(field))
                c['hidden_world']['grants']=deepcopy(runtime.grants)
                expanded.append(c)
    return expanded


def fit(train,dev):
    x,xd=matrix(train),matrix(dev)
    y=np.array([not safe(e['hidden_world']) for e in train],dtype=int)
    yd=np.array([not safe(e['hidden_world']) for e in dev],dtype=int)
    base=fit_linear(x,y)
    models={}
    for regime in ('weighted','safety_1pct'):
        models['affine_'+regime]={'representation':'affine','model':{
            **base,'threshold':calibrate(xd@base['weights']+base['bias'],yd,regime)}}
    for leaves in (4,16,64):
        # Fixed learner settings. Thresholds selected only on development.
        tree=DecisionTreeClassifier(max_leaf_nodes=leaves,min_samples_leaf=8,
                                    class_weight='balanced',random_state=49137)
        tree.fit(x,y)
        score=tree.predict_proba(xd)[:,list(tree.classes_).index(1)]
        for regime in ('weighted','safety_1pct'):
            models[f'linear_rules_{leaves}_{regime}']={'representation':'linear_rules',
                 'model':{'tree':tree,'threshold':calibrate(score,yd,regime)}}
    return models


def summarize(rows):
    n=len(rows); s=sum(r['safe_original'] for r in rows);u=n-s
    fa=sum(r['initial_allowed'] and not r['safe_original'] for r in rows)
    fb=sum(not r['initial_allowed'] and r['safe_original'] for r in rows)
    return {'cases':n,'safe':s,'unsafe':u,'false_allow':fa,'false_block':fb,
        'decision_accuracy':1-(fa+fb)/n,'successful_executions':sum(r['policy_safe'] for r in rows),
        'unsafe_executions':sum(r['committed'] and not r['policy_safe'] for r in rows),
        'oracle_recoverable':sum(r['recoverable'] for r in rows),'verification_queries':sum(r['queries'] for r in rows)}


def serialize(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,DecisionTreeClassifier):
        t=value.tree_
        return {'classes':value.classes_.tolist(),'children_left':t.children_left.tolist(),
                'children_right':t.children_right.tolist(),'feature':t.feature.tolist(),
                'threshold':t.threshold.tolist(),'value':t.value.tolist(),'node_count':t.node_count}
    raise TypeError(type(value).__name__)


def dump(path,value):path.write_text(json.dumps(value,indent=2,default=serialize)+'\n',encoding='utf-8')


def main():
    episodes=build_episodes()
    splits={s:[e for e in episodes if e['split']==s] for s in ('train','dev','test')}
    models=fit(splits['train'],splits['dev'])
    models.update({name+'_feedback':params for name,params in
                   fit(feedback_training(splits['train']),feedback_training(splits['dev'])).items()})
    flags=('projection','lifting','dynamic','repair')
    arms={'full':{}}
    for mask in product((True,False),repeat=4):
        if all(mask):continue
        name='off_'+'_'.join(str(i+1) for i,v in enumerate(mask) if not v)
        arms[name]=dict(zip(flags,mask))
    arms.update(models)
    arms.update({'global_authorization':{'mode':'global_authorization'},
                 'ignore_revision':{'mode':'ignore_revision'},
                 'ignore_shared_events':{'mode':'independent_paths'},
                 'no_probability_interval':{'uncertainty':False}})
    OUT.mkdir(parents=True,exist_ok=True)
    sources=[Path(__file__),ROOT/'src/geometry_capacity/backends.py',
             *sorted((ROOT/'src/relational_dafr').glob('*.py'))]
    freeze={'scope':'Complete experimental typed-evidence relational controller; NOT the original DAFR semantic/LLM pipeline.',
            'seed':49137,'arms':arms,'counts':{s:len(v) for s,v in splits.items()},
            'environment':{'python':sys.version,'numpy':np.__version__,'scikit_learn':sklearn.__version__},
            'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            'protocol':['No test-derived thresholds, seed search or sample filtering.',
                'Feedback baselines added after the initial diagnostic run; train/dev include permitted verification states. Test cases are unchanged.',
                'Input contains rounded probabilities and traces; latent probabilities and verification ledger are hidden.',
                'Real simulated verifier replies may refuse; calls consume a fixed query budget.',
                'Safety means an explicit expected-unauthorized-loss budget, not zero realized harm.',
                'Linear comparisons include an affine score and finite AND/OR compositions of axis-aligned linear predicates.',
                'Risk bound assumes declared measurement rounding error. Real probability calibration is untested.',
                'Known structural causal process favors a correctly specified controller; equivalent nonlinear arithmetic must tie.']}
    dump(OUT/'frozen_protocol.json',freeze)
    rows=[]
    for i,e in enumerate(splits['test']):
        original=safe(e['hidden_world']); recoverable=oracle_recoverable(e)
        for name,params in arms.items():
            r=run_episode(e['input'],EpisodeRuntime(e),**params)
            r.update(id=e['id'],group=e['group'],domain=e['domain'],variant=e['variant'],arm=name,
                     safe_original=original,recoverable=recoverable)
            rows.append(r)
        if (i+1)%300==0:print(f'{i+1}/{len(splits["test"])} x {len(arms)} arms',flush=True)
    aggregates={a:summarize([r for r in rows if r['arm']==a]) for a in arms}
    bydomain={d:{a:summarize([r for r in rows if r['arm']==a and r['domain']==d]) for a in arms}
              for d in sorted({e['domain'] for e in episodes})}
    # Gate requires a positive full-flow geometry-vs-affine gap plus all four
    # single module ablations worse on safety/utility. It does not pretend
    # that passing is an external preregistration or full real-world proof.
    full=aggregates['full'];base=aggregates['affine_weighted']
    effects={a:{'extra_unsafe_executions':aggregates[a]['unsafe_executions']-full['unsafe_executions'],
                'lost_successful_executions':full['successful_executions']-aggregates[a]['successful_executions'],
                'extra_initial_errors':aggregates[a]['false_allow']+aggregates[a]['false_block']-full['false_allow']-full['false_block']}
             for a in ('off_1','off_2','off_3','off_4')}
    dominates_all_linear=all(full['successful_executions']>aggregates[a]['successful_executions']
                             and full['unsafe_executions']<=aggregates[a]['unsafe_executions'] for a in models)
    gate=(full['unsafe_executions']==0 and full['decision_accuracy']-base['decision_accuracy']>=.03
          and dominates_all_linear
          and all(v['extra_unsafe_executions']>0 or v['lost_successful_executions']>0 for v in effects.values()))
    report={'scope':freeze['scope'],'test':aggregates,'by_domain':bydomain,'module_effects':effects,
            'gate_passed':gate,'dataset_retained':gate,
            'dominates_all_tested_linear_configs_on_safe_execution_and_violations':dominates_all_linear,
            'limitations':['This is controlled-model evidence for upgraded typed pipeline, not full original DAFR or empirical natural-language generalization.',
                'Four synthetic graph/effect families; graph extraction consumes explicit trace records.',
                'No claim of optimal affine/polyhedral learner or superiority to arbitrary nonlinear rules.',
                'Verification order is shared and can be suboptimal relative to oracle permitted-set upper bound.']}
    dump(OUT/'summary.json',report)
    (OUT/'test_rows.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
    if gate:
        DATA.mkdir(parents=True,exist_ok=True)
        for s,subset in splits.items():
            (DATA/f'{s}_inputs.jsonl').write_text(''.join(json.dumps(e['input'])+'\n' for e in subset),encoding='utf-8')
            (DATA/f'{s}_evaluator.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in subset),encoding='utf-8')
            (DATA/f'{s}_labels.jsonl').write_text(''.join(json.dumps({'id':e['input']['id'],'safe':safe(e['hidden_world']),
                'expected_loss':expected_loss(e['hidden_world']),'recoverable':oracle_recoverable(e)})+'\n' for e in subset),encoding='utf-8')
        dump(DATA/'manifest.json',{'freeze':freeze,'gate':report['module_effects'],
             'data_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.glob('*.jsonl')}})
    print('Gate',gate,'Module effects',json.dumps(effects),flush=True)
    for a,s in aggregates.items():print(a,json.dumps(s),flush=True)


if __name__=='__main__':main()
