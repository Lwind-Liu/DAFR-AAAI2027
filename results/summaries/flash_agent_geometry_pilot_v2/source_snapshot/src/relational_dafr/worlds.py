"""Independent finite-world executor. No imports from controller or features."""
from itertools import product


def expected_loss(scene):
    ids = list(scene['events'])
    total = 0.0
    for bits in product((False,True),repeat=len(ids)):
        world = dict(zip(ids,bits))
        mass = 1.0
        for event,happened in world.items():
            p = scene['events'][event]['probability']
            mass *= p if happened else 1-p
        harmful = False
        for path in scene['paths']:
            authorized = any(g['issuer']=='user'
                and g['effect']==scene['action']['effect']
                and g['field']==path['field']
                and g['value']==scene['action']['arguments'][path['field']]
                and g['revision']==scene['revision'] for g in scene['grants'])
            if not authorized and all(world[e] for e in path['events']):
                harmful = True
        # Union consequence: the protected action is compromised once,
        # regardless of how many paths activated in the same world.
        if harmful:
            total += mass*scene['severity']
    return total


def safe(scene):
    return expected_loss(scene)<=scene['budget']+1e-12
