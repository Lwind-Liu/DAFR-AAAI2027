"""Independent local thermal simulator. No imports from clafr or backends.

This is a declared engineering model, not calibrated physical hardware.
Current channels dissipate quadratic energy; a linear-energy control is also
included to prevent presenting every task as a nonlinear-geometry win.
"""
from copy import deepcopy


def replay(scene, allocation):
    p, state, goal = scene['plant'], scene['state'], scene['goal']
    q = allocation
    before = deepcopy(state)
    violations = []
    if len(q) != 3 or any(not isinstance(v, (int, float)) or v < 0 for v in q):
        return {'safe': False, 'success': False, 'violations': ['schema'], 'after': before}
    currents = []
    for wire in range(3):
        currents.append(state['background'][wire] + sum(p['mixing'][wire][i] * q[i] for i in range(3)))
    # Measured model output computed from raw allocation and physical state,
    # never from a feature vector, margin, or a backend's decision.
    dissipated = sum(v * v for v in currents) if p['law'] == 'quadratic' else sum(currents)
    temperature = p['ambient'] + p['gain'] * dissipated
    capacity = p['base_capacity'] + state['cooling_credit']
    limit = p['ambient'] + p['gain'] * (capacity * capacity if p['law'] == 'quadratic' else capacity)
    if temperature > limit + 1e-10:
        violations.append('temperature')
    if any(v > cap + 1e-10 for v, cap in zip(q, goal['caps'])):
        violations.append('allocation_cap')
    if any(locked and abs(v - wanted) > 1e-10 for v, wanted, locked in zip(q, scene['proposal'], goal['locked'])):
        violations.append('locked_effect')
    achieved = sum(w * v for w, v in zip(goal['throughput_weights'], q))
    goal_met = achieved >= goal['minimum_throughput'] - 1e-10
    after = deepcopy(state)
    if not violations:
        after['committed_allocation'] = list(q)
        after['temperature'] = temperature
        after['version'] += 1
    return {'safe': not violations, 'success': not violations and goal_met,
            'goal_met': goal_met, 'temperature': temperature, 'limit': limit,
            'violations': violations, 'after': after}
