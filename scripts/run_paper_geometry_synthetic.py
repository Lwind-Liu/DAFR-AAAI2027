"""Final paper-aligned synthetic protocol. No benchmark/API calls or filtering."""
from collections import defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'scripts'))
from geometry_capacity.paper_pipeline import build,run,evaluate_world
from geometry_capacity.backends import edit_candidates,fit_linear,calibrate
from geometry_capacity import paper_scenes
from run_geometry_capacity_benchmark import jsonl,dump

DATA=ROOT/'data/paper_geometry_synthetic_v1'
OUT=ROOT/'results/summaries/paper_geometry_synthetic_v1'


def fit_simple_linear(train,dev):
    def matrix(cases):
        result=[]
        for c in cases:
            p,s,q=c['plant'],c['state'],c['proposal'];n=len(q)
            loads=[(s['background'][j]+sum(p['mixing'][j][i]*q[i] for i in range(n)))/p['base_capacity'] for j in range(n)]
            result.append([*loads,s['cooling_credit']/p['base_capacity']])
        return np.array(result)
    train=[c for c in train if c['plant']['law']=='quadratic'];dev=[c for c in dev if c['plant']['law']=='quadratic']
    x,xd=matrix(train),matrix(dev)
    y=np.array([not paper_scenes.replay(c,c['proposal'])['safe'] for c in train])
    yd=np.array([not paper_scenes.replay(c,c['proposal'])['safe'] for c in dev])
    base=fit_linear(x,y)
    return {**base,'threshold':calibrate(xd@base['weights']+base['bias'],yd,'weighted')}


def summary(rows):
    n=len(rows)
    return {'cases':n,'safe_original':sum(r['original_safe'] for r in rows),
            'false_allow':sum(r['initial_allowed'] and not r['original_safe'] for r in rows),
            'false_block':sum(not r['initial_allowed'] and r['original_safe'] for r in rows),
            'successful_tasks':sum(r['success'] for r in rows),
            'unsafe_admissions':sum(r['unsafe_admission'] for r in rows),
            'recoverable':sum(r['recoverable'] for r in rows),
            'revision_checks':sum(r['revision_checks'] for r in rows)}


def intervals(rows):
    arms=sorted({r['arm'] for r in rows});groups=sorted({r['group'] for r in rows})
    per={a:defaultdict(list) for a in arms}
    for r in rows:per[r['arm']][r['group']].append([float(r['success']),float(r['unsafe_admission'])])
    means={a:np.array([np.mean(per[a][g],axis=0) for g in groups]) for a in arms}
    rng=np.random.default_rng(20261017);sampled=rng.integers(0,len(groups),(4000,len(groups)))
    out={}
    for a in arms:
        if a=='full':continue
        delta=means['full']-means[a];bootstrap=delta[sampled].mean(axis=1)
        out[a]={key:{'full_minus_arm':float(delta[:,i].mean()),
                    'paired_group_95pct':np.quantile(bootstrap[:,i],[.025,.975]).tolist()}
                for i,key in enumerate(('success_rate','unsafe_admission_rate'))}
    return out


def main():
    global DATA,OUT
    parser=argparse.ArgumentParser();parser.add_argument('--channels',type=int,choices=(3,6),default=6)
    args=parser.parse_args()
    if args.channels==6:
        DATA=ROOT/'data/paper_geometry_synthetic_v2';OUT=ROOT/'results/summaries/paper_geometry_synthetic_v2'
    episodes=build(channels=args.channels);splits={s:[e for e in episodes if e['split']==s] for s in ('train','dev','test')}
    physical={s:list({e['world']['scene']['id']:e['world']['scene'] for e in es}.values()) for s,es in splits.items()}
    linear=fit_simple_linear(physical['train'],physical['dev'])
    arms={'full':{},'no_projection':{'projection':False},'no_lifting':{'lifting':False},
          'no_geometry':{'geometry':False},'no_feedback':{'feedback':False}}
    arms['simple_linear_rule']={'representation':'affine','model':linear}
    DATA.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    for s,es in splits.items():
        jsonl(DATA/f'{s}_inputs.jsonl',[e['input'] for e in es])
        jsonl(DATA/f'{s}_evaluator.jsonl',es)
        jsonl(DATA/f'{s}_labels.jsonl',[{'id':e['input']['id'],**evaluate_world(e,e['input']['action']['arguments'])} for e in es])
    sources=[Path(__file__),ROOT/'scripts/run_geometry_capacity_benchmark.py',
             *sorted((ROOT/'src/geometry_capacity').glob('*.py')),
             ROOT/'src/clafr/geometry.py',ROOT/'src/clafr/schemas.py']
    protocol={'seed':20261017,'risk_dimensions':args.channels,'counts':{s:len(es) for s,es in splits.items()},'arms':arms,
        'scope':'Paper-aligned four-module synthetic adapter using unchanged native FeasibleRegion/LinearFacet/RiskBudgetCone. Not production NLP/LLM DAFR.',
        'rules':['All generated samples retained, including ties and failures; no result-dependent export gate.',
           'Group all physical and evidence counterfactuals before splitting.',
           'Linear baselines receive identical lifting, trusted evidence, support facets and feedback candidate grammar.',
           'Linear weights/normals trained on training; thresholds calibrated on development only.',
           'Removing geometry removes all geometric constraints; removing feedback preserves initial decisions.',
           'Raw-observation fallback under no projection has confidence .65 versus required .8; this is an explicit adapter assumption.',
           'Current verified-state observations precede the proposed write; feedback revises load without changing target, locks or throughput floor.',
           'Quadratic thermal model is declared and uncalibrated; linear-law controls are separately reported.',
           'Unsafe admission means forwarding an unsafe action. Atomic simulator rejection prevents unsafe physical commits.',
           'Exact nonlinear arithmetic is equivalent to the cone; no claim against equally expressive nonlinear rules.'],
        'development_history':'Exploratory six-channel extension of the retained 3-D diagnostic. Final user-requested comparison is one affine rule plus the four paper-module ablations. No seed search or sample filtering.',
        'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        'data_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.glob('*.jsonl')}}
    dump(DATA/'manifest.json',protocol);dump(OUT/'frozen_protocol.json',protocol)
    rows=[]
    for i,e in enumerate(splits['test']):
        grammar={'proposal':e['input']['action']['arguments']['allocation'],'goal':e['input']['task']['goal']}
        recoverable=any(evaluate_world(e,{**e['input']['action']['arguments'],'allocation':q})['success'] for q in edit_candidates(grammar))
        for arm,params in arms.items():
            r=run(e,**params);r.update(arm=arm,recoverable=recoverable)
            rows.append(r)
        if (i+1)%360==0:print(f'{i+1}/{len(splits["test"])} x {len(arms)} configurations',flush=True)
    jsonl(OUT/'test_rows.jsonl',rows)
    report={'scope':protocol['scope'],
            'quadratic':{a:summary([r for r in rows if r['arm']==a and r['law']=='quadratic']) for a in arms},
            'linear_control':{a:summary([r for r in rows if r['arm']==a and r['law']=='linear']) for a in arms},
            'all':{a:summary([r for r in rows if r['arm']==a]) for a in arms},
            'evidence_slices':{v:{a:summary([r for r in rows if r['arm']==a and r['evidence_variant']==v]) for a in arms}
                               for v in ('known_target','lookup_target','injected_target')},
            'paired_intervals':intervals([r for r in rows if r['law']=='quadratic'])}
    dump(OUT/'summary.json',report)
    for a,s in report['quadratic'].items():print(a,json.dumps(s),flush=True)
    # Validate manifest, split groups, exact geometric/simulator agreement,
    # and genuine module identities without changing the generated sample set.
    group_sets={s:{e['group'] for e in es} for s,es in splits.items()}
    assert not(group_sets['train']&group_sets['dev'] or group_sets['train']&group_sets['test'] or group_sets['dev']&group_sets['test'])
    assert len(rows)==len(splits['test'])*len(arms)
    full=report['all']['full'];assert full['false_allow']==full['false_block']==full['unsafe_admissions']==0
    assert full['successful_tasks']==full['recoverable']
    indexed={(r['id'],r['arm']):r for r in rows}
    assert all(r['initial_allowed']==indexed[r['id'],'full']['initial_allowed'] for r in rows if r['arm']=='no_feedback')
    dump(OUT/'integrity.json',{'group_splits_disjoint':True,'full_exact_against_independent_simulator':True,
         'full_maximal_within_shared_revision_grammar':True,'no_feedback_preserves_initial_decision':True,
         'sample_count':len(episodes),'base_groups':len({e['group'] for e in episodes}),
         'all_cases_retained':True,'rows':len(rows)})


if __name__=='__main__':main()
