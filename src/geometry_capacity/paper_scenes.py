"""Six-channel extension, following the same declared physics and cohorts.

Added after a 3-D diagnostic tied a 64-plane baseline. This is exploratory
dimension stress, not preregistered or calibrated hardware evidence.
"""
from copy import deepcopy
import math
import random


def generate(groups=90,seed=20261017,channels=6):
    result=[]
    for k,profile in enumerate(('edge_controller','rack_controller','charging_controller','lab_controller')):
        for i in range(groups):
            rng=random.Random(seed+k*100000+i)
            split='train' if i<groups//3 else ('dev' if i<2*groups//3 else 'test')
            mixing=[[rng.uniform(.03,.15) if r!=c else rng.uniform(.65,1.3)
                     for c in range(channels)] for r in range(channels)]
            background=[rng.uniform(0,.15) for _ in range(channels)]
            base=rng.uniform(.9,1.3);cooling=rng.uniform(0,.7)
            direction=[rng.uniform(.02,1) for _ in range(channels)]
            cohort=('broad','boundary','axis_stress')[i%3]
            if cohort=='axis_stress':direction[rng.randrange(channels)]*=8
            response=[sum(row[j]*direction[j] for j in range(channels)) for row in mixing]
            a=sum(v*v for v in response);b=2*sum(v*old for v,old in zip(response,background))
            c=sum(v*v for v in background)-(base+cooling)**2
            scale=(-b+math.sqrt(b*b-4*a*c))/(2*a)
            factor=rng.uniform(.94,1.06) if cohort=='boundary' else rng.uniform(.35,1.6)
            proposal=[v*scale*factor for v in direction];weights=[rng.uniform(.7,1.3) for _ in direction]
            scene={'group_id':f'{profile}/{split}/{i:04d}','profile':profile,'split':split,'cohort':cohort,
                   'plant':{'mixing':mixing,'base_capacity':base,'ambient':rng.uniform(18,30),
                            'gain':rng.uniform(3,12),'law':'quadratic'},
                   'state':{'background':background,'cooling_credit':cooling,'version':i+2},
                   'proposal':proposal,'goal':{'throughput_weights':weights,
                       'minimum_throughput':sum(w*q for w,q in zip(weights,proposal))*rng.uniform(.45,.8),
                       'caps':proposal[:],'locked':[False]*channels}}
            for variant in ('natural','no_cooling','extra_cooling','concurrent_load','locked','linear_control'):
                item=deepcopy(scene);item.update(id=scene['group_id']+'/'+variant,variant=variant)
                if variant=='no_cooling':item['state']['cooling_credit']=0
                elif variant=='extra_cooling':item['state']['cooling_credit']+=.35
                elif variant=='concurrent_load':item['state']['background']=[v+rng.uniform(.12,.35) for v in background]
                elif variant=='locked':item['goal']['locked'][rng.randrange(channels)]=True
                elif variant=='linear_control':item['plant']['law']='linear'
                result.append(item)
    return result


def replay(scene,allocation):
    """Independent generic physical evaluator; no geometric imports."""
    p,s,g=scene['plant'],scene['state'],scene['goal'];n=len(s['background'])
    if len(allocation)!=n or any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in allocation):
        raise ValueError('Invalid channel allocation')
    currents=[s['background'][j]+sum(p['mixing'][j][i]*allocation[i] for i in range(n)) for j in range(n)]
    heat=sum(v*v for v in currents) if p['law']=='quadratic' else sum(currents)
    capacity=p['base_capacity']+s['cooling_credit']
    temperature=p['ambient']+p['gain']*heat
    limit=p['ambient']+p['gain']*(capacity**2 if p['law']=='quadratic' else capacity)
    violations=[]
    if temperature>limit+1e-10:violations.append('temperature')
    if any(q>cap+1e-10 for q,cap in zip(allocation,g['caps'])):violations.append('allocation_cap')
    if any(locked and abs(q-old)>1e-10 for q,old,locked in zip(allocation,scene['proposal'],g['locked'])):violations.append('locked_effect')
    progress=sum(w*q for w,q in zip(g['throughput_weights'],allocation))>=g['minimum_throughput']-1e-10
    return {'safe':not violations,'success':not violations and progress,'temperature':temperature,
            'limit':limit,'violations':violations}
