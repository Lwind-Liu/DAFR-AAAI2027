"""Grouped holdout and leave-one-graph-family-out study; no seed search."""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from relational_dafr import decide,features,repair,surface_risk
from relational_dafr.controller import quadratic_features,risk_interval
from relational_dafr.scenarios import generate,DOMAINS
from relational_dafr.worlds import safe,expected_loss
from geometry_capacity.backends import fit_linear,calibrate


def fit(train,dev,feature_map=None):
    x=np.array([features(c) for c in train])
    y=np.array([not safe(c) for c in train])
    xd=np.array([features(c) for c in dev])
    yd=np.array([not safe(c) for c in dev])
    extra={}
    if feature_map=='quadratic':
        x=np.array([quadratic_features(v) for v in x])
        xd=np.array([quadratic_features(v) for v in xd])
        extra={'feature_map':feature_map}
    if feature_map=='random_tanh':
        rng=np.random.default_rng(20261010)
        mean,std=x.mean(axis=0),np.maximum(x.std(axis=0),1e-6)
        projection=rng.normal(0,1/np.sqrt(x.shape[1]),size=(x.shape[1],128))
        offset=rng.normal(0,.5,size=128)
        x=np.column_stack((x,np.tanh(((x-mean)/std)@projection+offset)))
        xd=np.column_stack((xd,np.tanh(((xd-mean)/std)@projection+offset)))
        extra={'feature_map':feature_map,'input_mean':mean,'input_std':std,'projection':projection,'offset':offset}
    model=fit_linear(x,y)
    model.update(extra)
    model['threshold']=calibrate(xd@model['weights']+model['bias'],yd,'weighted')
    return model


def metrics(rows):
    n=len(rows)
    return {'cases':n,'safe':sum(r['safe'] for r in rows),
        'unsafe':sum(not r['safe'] for r in rows),
        'false_allow':sum(r['allowed'] and not r['safe'] for r in rows),
        'false_block':sum(not r['allowed'] and r['safe'] for r in rows),
        'accuracy':sum(r['allowed']==r['safe'] for r in rows)/n,
        'safe_verification_plans':sum(r.get('plan_safe',False) for r in rows),
        'unsafe_verification_plans':sum(r.get('plan_present',False) and not r.get('plan_safe',False) for r in rows),
        'unnecessary_verifications':sum(r['safe'] and r.get('verification_steps',0)>0 for r in rows)}


def evaluate(cases,mode,model=None,do_repair=True):
    rows=[]
    for c in cases:
        allowed=decide(c,mode,model)
        label=safe(c)
        name,plan=repair(c,mode,model) if do_repair else ('none',c if allowed else None)
        steps=0 if not name or name=='none' else len(name.split('+'))
        rows.append({'id':c['id'],'group':c['group'],'domain':c['domain'],'variant':c['variant'],
                     'safe':label,'allowed':bool(allowed),'plan_present':plan is not None,
                     'plan_safe':bool(plan is not None and safe(plan)), 'verification_steps':steps})
    return rows


def group_ci(a,b):
    values=defaultdict(list)
    for ra,rb in zip(a,b):
        assert ra['id']==rb['id']
        values[ra['group']].append(int(ra['allowed']==ra['safe'])-int(rb['allowed']==rb['safe']))
    means=np.array([np.mean(v) for v in values.values()])
    rng=np.random.default_rng(20261010)
    draws=means[rng.integers(0,len(means),size=(2000,len(means)))].mean(axis=1)
    return {'groups':len(means),'accuracy_difference':float(means.mean()),
            'ci95':np.quantile(draws,[.025,.975]).tolist()}


def main():
    scenes=generate()
    train=[c for c in scenes if c['split']=='train']
    dev=[c for c in scenes if c['split']=='dev']
    test=[c for c in scenes if c['split']=='test']
    model=fit(train,dev)
    quadratic=fit(train,dev,'quadratic')
    nonlinear=fit(train,dev,'random_tanh')
    # Models fixed before reporting any held-out outcomes. No test tuning.
    leaveout={d:fit([c for c in train if c['domain']!=d],
                   [c for c in dev if c['domain']!=d]) for d in DOMAINS}
    leaveout_quad={d:fit([c for c in train if c['domain']!=d],
                   [c for c in dev if c['domain']!=d],'quadratic') for d in DOMAINS}
    arms={'relational_surface':('full',None,True),
          'same_lifting_linear':('linear',model,True),
          'same_lifting_quadratic':('linear',quadratic,True),
          'same_lifting_random_tanh_128':('linear',nonlinear,True),
          'no_dependency_relation':('no_dependency',None,True),
          'global_authorization':('global_authorization',None,True),
          'ignore_current_revision':('ignore_revision',None,True),
          'ignore_shared_events':('independent_paths',None,True),
          'no_verification_repair':('full',None,False)}
    rows={a:evaluate(test,*params) for a,params in arms.items()}
    # Exact nonlinear arithmetic is a mandatory equivalence control. It uses
    # the independent world executor here, and is explicitly marked oracle
    # arithmetic conformance, not a competing learned algorithm.
    arithmetic=[dict(r,allowed=safe(c)) for r,c in zip(rows['relational_surface'],test)]
    assert all(r['allowed']==r['safe'] for r in rows['relational_surface'])
    assert arithmetic==rows['relational_surface']
    full=metrics(rows['relational_surface'])
    assert full['unsafe_verification_plans']==0
    stats={a:metrics(r) for a,r in rows.items()}
    bydomain={d:{a:metrics([r for r in rs if r['domain']==d]) for a,rs in rows.items()} for d in DOMAINS}
    ood={d:{'surface':metrics(evaluate([c for c in test if c['domain']==d],'full')),
            'linear_trained_on_other_graphs':metrics(evaluate([c for c in test if c['domain']==d],'linear',leaveout[d])),
            'quadratic_trained_on_other_graphs':metrics(evaluate([c for c in test if c['domain']==d],'linear',leaveout_quad[d]))} for d in DOMAINS}
    errors={}
    for amplitude in (.02,.05,.1):
        rng=np.random.default_rng(20261010)
        noisy=[]
        bounded=[]
        for c in test:
            observed=deepcopy(c)
            for event in observed['events'].values():
                event['probability']=float(np.clip(event['probability']+rng.uniform(-amplitude,amplitude),0,1))
            noisy.append({'id':c['id'],'group':c['group'],'domain':c['domain'],
                          'safe':safe(c),'allowed':decide(observed)})
            low,high=risk_interval(observed,amplitude)
            truth=expected_loss(c)
            assert low-1e-12<=truth<=high+1e-12
            bounded.append({'safe':safe(c),'allowed':high<=c['budget']+1e-12,
                            'uncertain':low<=c['budget']<high})
        errors[str(amplitude)]={'point_estimate':metrics(noisy),
            'interval_conservative':metrics(bounded),
            'requires_verification':sum(r['uncertain'] for r in bounded),
            'condition':'Known uniform perturbation is within the declared interval. Unknown miscalibration may violate this assumption.'}
        assert errors[str(amplitude)]['interval_conservative']['false_allow']==0
    out=ROOT/'results/summaries/relational_dafr_prototype_v1'
    out.mkdir(parents=True,exist_ok=True)
    sources=[Path(__file__),*sorted((ROOT/'src/relational_dafr').glob('*.py'))]
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    report={'scope':'Experimental generic typed causal controller. Synthetic uncalibrated event probabilities; no production NLP graph extraction, LLM replanning, or real verification round trip.',
            'source_sha256':hashes,'seed':20261010,
            'counts':{'train':len(train),'dev':len(dev),'test':len(test),'base_groups':960},
            'metrics':stats,'by_domain':bydomain,'leave_one_graph_family_out':ood,
            'probability_misspecification':errors,
            'paired_group_ci':group_ci(rows['relational_surface'],rows['same_lifting_linear']),
            'paired_group_ci_stronger_controls':{a:group_ci(rows['relational_surface'],rows[a])
                for a in ('same_lifting_quadratic','same_lifting_random_tanh_128')},
            'equivalent_nonlinear_arithmetic':'Exact tie. Expanding every path-union monomial and giving it to a linear model also reproduces the same surface; no superiority to unrestricted rules is claimed.',
            'models':{'in_domain':model,'quadratic':quadratic,'random_tanh':nonlinear,'leaveout':leaveout,'leaveout_quadratic':leaveout_quad},
            'method_changes':['Shared-event causal paths replace independent risk-coordinate budgets.',
                'Grants must match issuer/effect/field/value/current revision; repeated grants cannot create extra credit.',
                'Nonconvex polynomial feasible surfaces replace the single convex-cone restriction.',
                'Repair proposes exact scoped verification sets; grants require a real trusted acquisition step.'],
            'limits':['Known finite-world process makes exact safety expected by construction; results are mechanism evidence, not empirical deployment performance.',
                'Four graph topologies are synthetic analogues, not independent calibrated real domains.',
                'Primitive events assumed independent. Uniform probability perturbations are tested; empirical calibration and graph-extraction errors are not.',
                'Same-lifting linear baseline is a fitted affine model, not all possible piecewise linear rules.',
                'Acquiring more grants is not scored as already completing a task; repair numbers are safe verification plans only.',
                'Production DAFR source is not replaced by this prototype.']}
    def convert(x):
        if isinstance(x,np.ndarray):return x.tolist()
        if isinstance(x,np.generic):return x.item()
        raise TypeError(type(x).__name__)
    (out/'evaluation.json').write_text(json.dumps(report,indent=2,default=convert)+'\n',encoding='utf-8')
    for a,s in stats.items():print(a,json.dumps(s))
    print('Paired group CI',json.dumps(report['paired_group_ci']))
    print('Unseen graph families',json.dumps(ood))
    print('Probability perturbations',json.dumps(errors))


if __name__=='__main__':main()
