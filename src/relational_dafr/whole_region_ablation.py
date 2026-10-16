"""Replace the entire typed feasible region with one affine decision.

The reference region intersects current-policy and argument-scope halfspaces
with the joint-risk surface. Runtime tool-schema validation is outside that
region and shared by every arm. No separate semantic or clear-path rule is
retained by the single-affine comparator.
"""
from copy import deepcopy
from itertools import combinations

import numpy as np

from .controller import features, decide
from .module_ablation import context, guard as reference_guard


def halfspace_coordinates(world, args):
    return np.array([float(world.policy_read),
        *[float(args.get(field) == world.case['desired'][field])
          for field in world.case['fields']]])


def coordinates(world, args, scene=None):
    if scene is None:
        scene = context(world, args, 'full_surface')
    return np.concatenate((features(scene), halfspace_coordinates(world, args)))


def region_admits(world, args, scene=None):
    if scene is None:
        scene = context(world, args, 'full_surface')
    return bool(np.all(halfspace_coordinates(world, args) >= .5) and decide(scene))


def linear_admits(world, args, model, scene=None):
    point = coordinates(world, args, scene)
    return bool(point @ model['weights'] + model['bias'] <= model['threshold'])


def targets(world, args, model):
    scene = context(world, args, 'full_surface')
    for count in range(1, len(world.case['fields']) + 1):
        for subset in combinations(world.case['fields'], count):
            candidate = deepcopy(scene)
            candidate['grants'].extend({'issuer': 'user', 'effect': world.case['tool'],
                'field': field, 'value': args[field], 'revision': scene['revision']}
                for field in subset)
            if linear_admits(world, args, model, candidate):
                return list(subset)
    return list(world.case['fields'])


def guard(world, args, arm, model):
    if arm not in ('linear_region', 'no_geometric_region'):
        # Exact existing component switches; reference-arm behavior unchanged.
        return reference_guard(world, args, arm, model)
    world.preflight_attempted = True
    if set(args) != set(world.case['fields']) or any(not isinstance(v, str) for v in args.values()):
        return False, {'reason': 'invalid_schema', 'repair': 'Use all required string fields.'}
    if arm == 'no_geometric_region':
        return True, {'reason': 'allowed'}
    allowed = linear_admits(world, args, model)
    if allowed:
        return True, {'reason': 'allowed'}
    # These branches generate feedback only AFTER the single affine decision.
    # They never override an admission or act as extra execution constraints.
    if not world.policy_read:
        return False, {'reason': 'feasibility_constraint', 'repair': 'Call read_policy.'}
    if args != world.case['desired']:
        return False, {'reason': 'feasibility_constraint',
                       'repair': 'Use exact user-requested field values.'}
    return False, {'reason': 'feasibility_constraint',
        'repair': 'Verify the listed exact field values independently, then retry.',
        'verification_targets': targets(world, args, model)}
