"""Generic guards taking ONLY the visible observer view, never the world/case."""
from copy import deepcopy
import numpy as np

from relational_dafr.controller import features, surface_risk

ARMS = ('full', 'no_projection', 'no_lifting', 'linear', 'no_geometry')


def representation(view, arm='full'):
    draft, policy = view['draft'], view['policy']
    if not draft or not policy:
        return None, np.array([0., 0., 0., 0.])
    scene = deepcopy(policy['risk_metadata'])
    scene.update(action={'effect': 'commit_operation', 'arguments': {f: draft[f] for f in ('destination', 'payload')}},
                 revision=draft['revision'], grants=[])
    receipts = deepcopy(view['authenticated_receipts'])
    if arm == 'no_projection':
        for observation in view['observations']:
            claim = observation['response'].get('claimed_receipt')
            if claim:
                receipts.append(deepcopy(claim))
    scope = []
    for field in ('destination', 'payload'):
        relevant = [r for r in receipts if r['field'] == field
                    and r['request_id'] == draft['request_id'] and r['revision'] == draft['revision']]
        # Missing evidence is an uncertain risk coordinate, not hidden ground truth.
        scope.append(float(not relevant or any(r['value'] == draft[field] for r in relevant)))
        for receipt in receipts:
            if receipt['field'] != field:
                continue
            covers = (receipt['request_id'] == draft['request_id']
                      and receipt['revision'] == draft['revision']
                      and receipt['effect'] == 'commit_operation' and receipt['value'] == draft[field])
            if arm == 'no_lifting' or covers:
                scene['grants'].append({'issuer': 'user', 'effect': 'commit_operation',
                    'field': field, 'value': draft[field], 'revision': draft['revision']})
        if arm == 'no_lifting':
            scope[-1] = 1.
    halfspaces = np.array([float(policy['request_id'] == draft['request_id']),
                          float(policy['revision'] == draft['revision']), *scope])
    return scene, halfspaces


def coordinates(view, arm='full'):
    scene, semantic = representation(view, arm)
    if scene is None:
        return np.concatenate((np.zeros(32), semantic))
    return np.concatenate((features(scene), semantic))


def admit(view, arm, model=None):
    if arm not in ARMS:
        raise ValueError(arm)
    if arm == 'no_geometry':
        return True, {'reason': 'allowed'}
    scene, semantic = representation(view, arm)
    if arm == 'linear':
        point = coordinates(view)
        allowed = float(point @ np.asarray(model['weights']) + model['bias']) <= model['threshold']
    else:
        allowed = scene is not None and np.all(semantic >= .5) and surface_risk(scene) <= scene['budget'] + 1e-12
    if allowed:
        return True, {'reason': 'allowed'}
    policy = view['policy']
    return False, {'status': 'blocked', 'reason': 'evidence_or_feasibility_constraint',
        'repair': 'Read the current request, independently verify its record references, use the returned current values and revision to stage a fresh operation, and then commit.',
        'record_ids': policy['records'] if policy else []}
