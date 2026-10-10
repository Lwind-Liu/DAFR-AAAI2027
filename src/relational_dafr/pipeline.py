"""Experimental complete typed-evidence controller; not production NLP DAFR.

Modules: provenance projection, dependency lifting, state-conditioned surface,
verification feedback and execution. Every representation uses the same inputs,
verification query budget and field ordering. No hidden labels enter the policy.
"""
from copy import deepcopy
import numpy as np
from .controller import features,surface_risk,grant_covers


def extract_context(public,projection=True,dynamic=True):
    action=deepcopy(public['action'])
    grants=[]
    traces=[]
    planning=None
    current=None
    for envelope in public['records']:
        channel,body=envelope['channel'],envelope['body']
        if body['kind']=='grant':
            if channel=='user' or not projection:
                grants.append(deepcopy(body['grant']))
            continue
        # Runtime identity is trusted execution plumbing, not authored text.
        if channel!='runtime':
            continue
        if body['kind']=='planning_snapshot':planning=body
        if body['kind']=='current_measurements':current=body
        if body['kind']=='field_trace':
            traces.append({'field':body['field'],'events':list(body['chain'])})
    source=current if dynamic else planning
    if source is None or not traces:
        raise ValueError('Missing typed measurement/trace evidence')
    return {'action':action,'grants':grants,'paths':traces,'revision':source['revision'],
            'events':{e:{'probability':m['estimate']} for e,m in source['events'].items()},
            'radii':{e:m['radius'] for e,m in source['events'].items()},
            'severity':public['policy']['severity'],'budget':public['policy']['risk_budget']}


def lifted_context(context,lifting=True):
    c=deepcopy(context)
    if not lifting:
        c['paths']=[{'field':p['field'],'events':[p['events'][0]]} for p in c['paths']]
    return c


def upper_context(context):
    c=deepcopy(context)
    for e in c['events']:
        c['events'][e]['probability']=min(1.,c['events'][e]['probability']+c['radii'][e])
    return c


def allows(context,representation='surface',model=None,mode='full',uncertainty=True):
    if representation=='affine':
        return bool(features(context)@model['weights']+model['bias']<=model['threshold'])
    if representation=='linear_rules':
        # Decision-tree predicates are axis-aligned halfspaces; leaves give
        # finite AND/OR rule compositions, stronger than one affine threshold.
        probability=model['tree'].predict_proba(features(context)[None,:])[0]
        classes=list(model['tree'].classes_)
        score=float(probability[classes.index(1)]) if 1 in classes else 0.
        return score<=model['threshold']
    c=upper_context(context) if uncertainty else context
    return surface_risk(c,mode)<=c['budget']+1e-12


def run_episode(public,runtime,representation='surface',model=None,projection=True,
                lifting=True,dynamic=True,repair=True,mode='full',uncertainty=True):
    records=deepcopy(public)
    contexts=[]
    try:
        context=lifted_context(extract_context(records,projection,dynamic),lifting)
    except (ValueError,KeyError,TypeError):
        return {'decision':'invalid_evidence','committed':False,'initial_allowed':False,
                'policy_safe':False,'queries':0,'contexts':[]}
    initial=allows(context,representation,model,mode,uncertainty)
    contexts.append({'allowed':initial,'revision':context['revision'],
                     'grant_count':len(context['grants'])})
    allowed=initial
    # Same repair order across representations, using only observable scope
    # mismatch and no ledger access. Refused checks consume the same budget.
    fields=[]
    for path in context['paths']:
        if path['field'] not in fields and not grant_covers(context,path):fields.append(path['field'])
    if not allowed and repair:
        for field in fields:
            if len(runtime.queries)>=public['policy']['verification_query_budget']:break
            response=runtime.verify(field)
            records['records'].append(response)
            context=lifted_context(extract_context(records,projection,dynamic),lifting)
            allowed=allows(context,representation,model,mode,uncertainty)
            contexts.append({'allowed':allowed,'revision':context['revision'],
                             'grant_count':len(context['grants'])})
            if allowed:break
    result=runtime.execute(public['action']) if allowed else None
    return {'decision':'execute' if result else 'decline','initial_allowed':initial,
            'committed':result is not None,'policy_safe':bool(result and result['policy_safe']),
            'queries':len(runtime.queries),'contexts':contexts,
            'execution':result}
