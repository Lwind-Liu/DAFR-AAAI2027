"""Generic provenance paths, scoped grants and nonconvex risk surfaces.

Inputs are typed facts, not unrestricted natural language. An event denotes
compromise or propagation; a path activates only if every event occurs.
Independent primitive event probabilities are declared by the environment.
Different paths can share events, so their failures are correlated.
This prototype does not estimate real-world probabilities or replace CLAFR.
"""
from copy import deepcopy
from itertools import combinations
import math
import numpy as np

MAX_EVENTS = 6
MAX_PATHS = 4


def validate_context(scene):
    for event in scene['events'].values():
        p=event['probability']
        if not isinstance(p,(int,float)) or not math.isfinite(p) or not 0<=p<=1:
            raise ValueError('Invalid primitive event probability')
    for name in ('severity','budget'):
        if not math.isfinite(scene[name]) or scene[name]<0:
            raise ValueError('Invalid risk consequence/budget')
    for path in scene['paths']:
        if (not path['events'] or any(e not in scene['events'] for e in path['events'])
                or path['field'] not in scene['action']['arguments']):
            raise ValueError('Invalid provenance path')


def grant_covers(scene, path, mode='full'):
    for grant in scene['grants']:
        if grant['issuer'] != 'user':
            continue
        if mode == 'global_authorization':
            return True
        if (grant['effect'] == scene['action']['effect']
                and grant['field'] == path['field']
                and grant['value'] == scene['action']['arguments'][path['field']]
                and (mode=='ignore_revision' or grant['revision'] == scene['revision'])):
            return True
    return False


def active_paths(scene, mode='full'):
    paths = []
    for path in scene['paths']:
        if not grant_covers(scene,path,mode):
            events = tuple(path['events'])
            if mode == 'no_dependency':
                # Ablate the source-to-action relation, retaining source risk.
                events = (events[0],)
            paths.append(events)
    return paths


def surface_risk(scene, mode='full'):
    """Probability of OR-of-AND causal paths via inclusion-exclusion.

    The graph fixes the polynomial topology; event probabilities are its
    coordinates. No field names, tool names or domain names enter this law.
    """
    validate_context(scene)
    paths = active_paths(scene,mode)
    probability = 0.0
    for size in range(1,len(paths)+1):
        for selected in combinations(paths,size):
            if mode == 'independent_paths':
                # Incorrect control: multiply path probabilities even if the
                # same primitive event appears in several paths.
                probability += (-1)**(size+1) * np.prod([
                    np.prod([scene['events'][e]['probability'] for e in path]) for path in selected])
            else:
                union = set().union(*map(set,selected))
                probability += (-1)**(size+1) * np.prod([scene['events'][e]['probability'] for e in union])
    return scene['severity'] * float(probability)


def risk_interval(scene, radius):
    """Monotone DNF bounds, conditional on declared probability coverage."""
    if radius<0:
        raise ValueError('Probability uncertainty radius must be nonnegative')
    low,high=deepcopy(scene),deepcopy(scene)
    for e in scene['events']:
        p=scene['events'][e]['probability']
        low['events'][e]['probability']=max(0.,p-radius)
        high['events'][e]['probability']=min(1.,p+radius)
    return surface_risk(low),surface_risk(high)


def features(scene):
    """All baselines receive the same probabilities, graph and scope lifting.

    Canonical event and path ordering is declared by the input. No domain
    string, safety label, simulator outcome or final risk score is included.
    """
    validate_context(scene)
    event_ids = list(scene['events'])
    probabilities = [scene['events'][e]['probability'] for e in event_ids]
    paths = active_paths(scene)
    membership = [[float(e in path) for e in event_ids] + [0.]*(MAX_EVENTS-len(event_ids)) for path in paths]
    membership += [[0.]*MAX_EVENTS for _ in range(MAX_PATHS-len(paths))]
    if len(event_ids)>MAX_EVENTS or len(paths)>MAX_PATHS:
        raise ValueError('Benchmark lifting dimensions exceeded; controller itself supports larger graphs')
    return np.array(probabilities + [0.]*(MAX_EVENTS-len(event_ids))
                    + [x for row in membership for x in row]
                    + [scene['severity'],scene['budget']])


def decide(scene, mode='full', model=None):
    if mode == 'linear':
        values=features(scene)
        if model.get('feature_map')=='quadratic':
            values=quadratic_features(values)
        if model.get('feature_map')=='random_tanh':
            z=(values-model['input_mean'])/model['input_std']
            values=np.concatenate((values,np.tanh(z@model['projection']+model['offset'])))
        return float(values @ model['weights']+model['bias']) <= model['threshold']
    # No proxy controller label is passed to this decision.
    return surface_risk(scene,mode) <= scene['budget'] + 1e-12


def quadratic_features(values):
    # Interaction expansion is available to the learned control too; the
    # surface comparison must not depend on withholding nonlinear features.
    indices=np.triu_indices(len(values))
    return np.concatenate((values,(values[:,None]*values[None,:])[indices]))


def repair(scene, mode='full', model=None):
    """Choose the smallest scoped verification set that passes this controller.

    A verification acquires an independent user grant for one exact field;
    it does not invent authority or change the requested action. Real-world
    acquisition would require an actual user/independent verifier round trip.
    """
    candidates = [('none',deepcopy(scene))]
    available = scene['verification_options']
    for count in range(1,len(available)+1):
        for fields in combinations(available,count):
            edited = deepcopy(scene)
            for field in fields:
                edited['grants'].append({'issuer':'user','effect':edited['action']['effect'],
                    'field':field,'value':edited['action']['arguments'][field],'revision':edited['revision']})
            candidates.append(('+'.join(fields),edited))
    for label,candidate in candidates:
        if decide(candidate,mode,model):
            return label,candidate
    return None,None
