"""Declared causal graph families, not empirically calibrated domains."""
from copy import deepcopy
import random

DOMAINS = ('payment','document_release','record_mutation','permission_change')


def generate(per_domain=240, seed=20261010):
    result=[]
    for domain_id,domain in enumerate(DOMAINS):
        for i in range(per_domain):
            rng=random.Random(seed+domain_id*100000+i)
            # Graphs have genuinely different shared-event topology. Domain
            # names and field names are not controller features.
            if domain=='payment':
                edges=[('payee',('e0','e1')),('amount',('e0','e2'))]
            elif domain=='document_release':
                edges=[('recipient',('e0','e1')),('payload',('e2','e3'))]
            elif domain=='record_mutation':
                edges=[('record',('e0','e1','e2')),('value',('e0','e3'))]
            else:
                edges=[('principal',('e0','e1')),('scope',('e2','e1')),
                       ('expiry',('e0','e3','e4'))]
            n=1+max(int(e[1:]) for _,path in edges for e in path)
            events={f'e{j}':{'probability':rng.uniform(.03,.97),
                       'role':'source' if j==0 else 'propagation'} for j in range(n)}
            scene={'group':f'{domain}/{i}', 'domain':domain,
                   'split':'train' if i<per_domain//2 else ('dev' if i<3*per_domain//4 else 'test'),
                   'events':events,'paths':[{'field':field,'events':list(path)} for field,path in edges],
                   'severity':rng.uniform(.2,1),'budget':rng.uniform(.03,.22),'revision':2,
                   'action':{'effect':domain,'arguments':{field:f'{field}_{i+1000}' for field,_ in edges}},
                   'grants':[],'verification_options':[field for field,_ in edges]}
            for variant in ('unverified','one_exact_grant','unrelated_grant','stale_grant','foreign_grant'):
                c=deepcopy(scene)
                field=edges[0][0]
                grant={'issuer':'user','effect':domain,'field':field,
                       'value':c['action']['arguments'][field],'revision':2}
                if variant=='unrelated_grant':
                    grant['effect']='another_effect'
                elif variant=='stale_grant':
                    grant['revision']=1
                elif variant=='foreign_grant':
                    grant['issuer']='untrusted_source'
                if variant!='unverified':
                    c['grants'].append(grant)
                c.update(id=f'{scene["group"]}/{variant}',variant=variant)
                result.append(c)
    return result
