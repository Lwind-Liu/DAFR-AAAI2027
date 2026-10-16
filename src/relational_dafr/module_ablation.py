"""Isolated component switches for the typed action-evidence adapter.

Evidence projection preserves source trust. Lifting binds trusted evidence to
effect, field and value. Geometry evaluates the unchanged causal paths.
Feedback selects an actionable verification set, without consulting the oracle.
"""
from copy import deepcopy
from itertools import combinations

from .controller import active_paths, decide


ARMS = ('full_surface', 'simple_linear', 'no_projection', 'no_lifting',
        'no_geometry', 'no_feedback')


def project(world, enabled=True):
    evidence = deepcopy(world.grants)
    if not enabled:
        # Flatten source-tagged envelopes: a claimed grant is no longer
        # distinguished from a genuine verifier record. No paths are changed.
        for envelope in world.records:
            evidence.extend(deepcopy(envelope['body'].get('claimed_grants', [])))
    return evidence


def lift(world, args, evidence, enabled=True):
    scene = deepcopy(world.case['scene'])
    scene['action']['arguments'] = deepcopy(args)
    scene['grants'] = deepcopy(evidence)
    if not enabled:
        # An unbound trusted-evidence indicator substitutes for relational
        # grounding. Preserve provenance, revision, every path and probability;
        # remove only the effect/field/value association of trusted evidence.
        trusted = any(g['issuer'] == 'user' and g['revision'] == scene['revision']
                      for g in evidence)
        scene['grants'] = ([{'issuer': 'user', 'effect': scene['action']['effect'],
                            'field': field, 'value': value,
                            'revision': scene['revision']}
                           for field, value in args.items()] if trusted else [])
    return scene


def context(world, args, arm):
    return lift(world, args, project(world, arm != 'no_projection'), arm != 'no_lifting')


def admits(scene, arm, model):
    if arm == 'no_geometry' or not active_paths(scene):
        return True
    return decide(scene, 'linear', model) if arm == 'simple_linear' else decide(scene)


def verification_targets(world, args, arm, model):
    """Minimum-cardinality repair under the current controller, not the oracle."""
    evidence = project(world, arm != 'no_projection')
    fields = [field for field in args if not any(
        g['issuer'] == 'user' and g['effect'] == world.case['tool']
        and g['field'] == field and g['value'] == args[field]
        and g['revision'] == world.case['scene']['revision'] for g in evidence)]
    for count in range(1, len(fields) + 1):
        for subset in combinations(fields, count):
            prospective = evidence + [{'issuer': 'user', 'effect': world.case['tool'],
                'field': field, 'value': args[field],
                'revision': world.case['scene']['revision']} for field in subset]
            candidate = lift(world, args, prospective, arm != 'no_lifting')
            if admits(candidate, arm, model):
                return list(subset)
    return fields


def guard(world, args, arm, model):
    world.preflight_attempted = True
    case = world.case
    if set(args) != set(case['fields']) or any(not isinstance(v, str) for v in args.values()):
        return False, {'reason': 'invalid_schema', 'repair': 'Use all required string fields.'}
    if not world.policy_read:
        return False, {'reason': 'missing_current_policy', 'repair': 'Call read_policy.'}
    # Identical task-scope check for every arm, including no_lifting.
    if args != case['desired']:
        return False, {'reason': 'outside_user_scope', 'repair': 'Use exact user-requested field values.'}
    allowed = admits(context(world, args, arm), arm, model)
    if allowed:
        return True, {'reason': 'allowed'}
    if arm == 'no_feedback':
        # Continue the same episode. The agent still has all tools and turns.
        return False, {'reason': 'joint_risk_budget'}
    return False, {'reason': 'joint_risk_budget',
        'repair': 'Verify the listed exact field values independently, then retry.',
        'verification_targets': verification_targets(world, args, arm, model)}
