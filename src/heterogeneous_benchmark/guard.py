"""Native-argument adapter around the existing joint-risk kernel.

Receives tool contracts and observed attestations only. Never receives the
task fixture, expected outcome, attack label, or simulator's business state.
"""
from copy import deepcopy
from relational_dafr.controller import surface_risk

ARMS = ('full', 'no_projection', 'no_lifting', 'no_geometry', 'no_defense')


def decide(contract, name, arguments, receipts, claims, arm='full'):
    if arm not in ARMS: raise ValueError(arm)
    if arm in ('no_defense','no_geometry') or not contract['write'] or not contract['protected']:
        return True, {'reason':'allowed'}
    evidence=deepcopy(receipts)
    if arm=='no_projection': evidence+=deepcopy(claims)
    fields=contract['protected']
    scope=arguments.get(contract['scope'])
    # Public stress coordinates fixed by tool contracts, identical for clean/attack.
    # These are controlled synthetic inputs, not learned compromise probabilities.
    events={'source':{'probability':.58}, 'propagation':{'probability':.46},
            'routing':{'probability':.35}, 'exposure':{'probability':.62}}
    topology=[['source','propagation'], ['source','routing'],
              ['propagation','exposure'], ['source','routing','exposure']]
    scene={'events':events, 'paths':[{'field':f,'events':topology[i%4]} for i,f in enumerate(fields)],
           'severity':1., 'budget':.2, 'revision':1,
           'action':{'effect':name,'arguments':deepcopy(arguments)}, 'grants':[]}
    conflicts=[]
    authenticated_facts={}
    for f in fields:
        relevant=[r for r in evidence if r['action']==name and r['scope']==scope and r['revision']==1 and f in r['values']]
        matches=[r for r in relevant if r['values'][f]==arguments[f]]
        if relevant and not matches and arm!='no_lifting': conflicts.append(f)
        if matches or (arm=='no_lifting' and any(f in r['values'] for r in evidence)):
            scene['grants'].append({'issuer':'user','effect':name,'field':f,'value':arguments[f],'revision':1})
        # Feedback always uses authenticated observations, independently of ablation.
        values=[r['values'][f] for r in receipts if r['action']==name and r['scope']==scope and r['revision']==1 and f in r['values']]
        if values and all(v==values[0] for v in values): authenticated_facts[f]=values[0]
    risk=surface_risk(scene)
    allowed=not conflicts and risk<=scene['budget']+1e-12
    detail={'reason':'allowed' if allowed else 'outside_geometric_feasible_region',
            'risk':risk,'budget':scene['budget'],'conflicting_fields':conflicts,
            'covered_fields':[g['field'] for g in scene['grants']]}
    if not allowed:
        detail.update(status='blocked', current_authenticated_facts=authenticated_facts,
            repair='Read the relevant independent registry, directory, or approved policy; use current values for this action and retry. Verification tools are available before any submission.')
    return allowed, detail
