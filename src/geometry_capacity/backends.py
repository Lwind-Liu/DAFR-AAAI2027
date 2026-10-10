"""Same observable coordinates, explicit linear-class complexity controls."""
import math
import numpy as np

from clafr.geometry import FeasibleRegion, LinearFacet, RiskBudgetCone
from clafr.schemas import FeatureVector


def coordinates(scene, q, mode='full'):
    p, s = scene['plant'], scene['state']
    background = scene['history']['background_at_planning'] if mode == 'static_state' else s['background']
    mixing = p['mixing']
    if mode == 'no_cross_channel':
        mixing = [[mixing[i][j] if i == j else 0 for j in range(3)] for i in range(3)]
    loads = [(background[j] + sum(mixing[j][i] * q[i] for i in range(3))) / p['base_capacity'] for j in range(3)]
    credit = 0 if mode == 'no_cooling_credit' else s['cooling_credit'] / p['base_capacity']
    return loads, credit


def region(scene, mode='full', normals=None, threshold=1):
    if scene['plant']['law'] == 'linear':
        return FeasibleRegion((LinearFacet('linear_heat', {**{f'load{i}': 1 for i in range(3)}, 'credit': -1},
                                         1, 'linear control', 'reduce allocation'),))
    if mode == 'linear_polytope':
        return FeasibleRegion(tuple(LinearFacet(f'plane_{j}',
            {**{f'load{i}': float(w[i]) for i in range(3)}, 'credit': -threshold}, threshold,
            'calibrated supporting halfspace', 'reduce allocation') for j, w in enumerate(normals)))
    if mode == 'no_joint_budget':
        return FeasibleRegion(tuple(LinearFacet(f'axis_{i}', {f'load{i}': 1, 'credit': -1}, 1,
                                               'independent budget', 'reduce allocation') for i in range(3)))
    return FeasibleRegion((RiskBudgetCone('thermal_capacity', {f'load{i}': 1 for i in range(3)}, {'credit': 1},
                                        1, 'joint simulated heat capacity', 'reduce coupled loads'),))


def task_contract(scene, q):
    goal = scene['goal']
    return (all(0 <= x <= cap + 1e-10 for x, cap in zip(q, goal['caps']))
            and all(not locked or abs(x - wanted) <= 1e-10 for x, wanted, locked in zip(q, scene['proposal'], goal['locked']))
            and sum(w * x for w, x in zip(goal['throughput_weights'], q)) >= goal['minimum_throughput'] - 1e-10)


def decide(scene, q, mode='full', model=None):
    if not task_contract(scene, q):
        return False
    loads, credit = coordinates(scene, q, mode)
    if mode == 'arithmetic_control':
        total = sum(x * x for x in loads) if scene['plant']['law'] == 'quadratic' else sum(loads)
        return total <= ((1 + credit) ** 2 if scene['plant']['law'] == 'quadratic' else 1 + credit) + 1e-10
    if mode == 'learned_linear' and scene['plant']['law'] == 'quadratic':
        values = np.array([*loads, credit])
        return float(values @ model['weights'] + model['bias']) <= model['threshold']
    normals = model.get('normals') if model else None
    threshold = model.get('threshold', 1) if model else 1
    vector = FeatureVector.from_mapping({**{f'load{i}': x for i, x in enumerate(loads)}, 'credit': credit})
    return region(scene, mode, normals, threshold).feasible(vector)


def edit_candidates(scene):
    # Identical finite grammar and ordering for every representation; locked
    # effects cannot be changed. This tests feasibility-guided utility, not
    # intrinsic superiority of a geometry-specific search algorithm.
    seen = set()
    q = scene['proposal']
    for step in range(100, -1, -1):
        scale = step / 100
        candidate = [x if locked else x * scale for x, locked in zip(q, scene['goal']['locked'])]
        key = tuple(candidate)
        if key not in seen and task_contract(scene, candidate):
            seen.add(key)
            yield candidate


def repair(scene, mode, model=None):
    if mode == 'no_repair':
        return scene['proposal'] if decide(scene, scene['proposal']) else None
    options = list(edit_candidates(scene))
    if not options:
        return None
    if mode in ('linear_polytope', 'learned_linear') and scene['plant']['law'] == 'quadratic':
        values = [coordinates(scene, q) for q in options]
        loads = np.array([v[0] for v in values])
        credits = np.array([v[1] for v in values])
        if mode == 'linear_polytope':
            permitted = np.max(loads @ model['normals'].T, axis=1) <= model['threshold'] * (1 + credits)
        else:
            permitted = np.column_stack((loads, credits)) @ model['weights'] + model['bias'] <= model['threshold']
        indices = np.flatnonzero(permitted)
        chosen = options[indices[0]] if len(indices) else None
        if chosen is not None and not decide(scene, chosen, mode, model):
            raise AssertionError('Batch search and native representation disagree')
        return chosen
    return next((q for q in options if decide(scene, q, mode, model)), None)


def fit_linear(x, unsafe):
    # Class-balanced logistic regression with an unrestricted affine score.
    # No nonlinear feature expansion; the same primitive loads/credit are
    # observed by the geometric and linear representations.
    mean, std = x.mean(axis=0), np.maximum(x.std(axis=0), 1e-6)
    z = (x - mean) / std
    y = unsafe.astype(float)
    balancing = np.where(y == 1, .5 / max(y.mean(), 1e-6), .5 / max(1 - y.mean(), 1e-6))
    weights, bias = np.zeros(x.shape[1]), 0.0
    for _ in range(600):
        score = np.clip(z @ weights + bias, -30, 30)
        residual = (1 / (1 + np.exp(-score)) - y) * balancing
        weights -= .08 * (z.T @ residual / len(y) + .001 * weights)
        bias -= .08 * residual.mean()
    raw = weights / std
    return {'weights': raw, 'bias': float(bias - mean @ raw)}


def supporting_planes(x, k):
    # Spherical farthest-point coverage followed by spherical k-means. The
    # normals are fit on training directions, without consulting test labels.
    directions = x[:, :3] / np.maximum(np.linalg.norm(x[:, :3], axis=1, keepdims=True), 1e-12)
    normals = [directions.mean(axis=0)]
    normals[0] /= np.linalg.norm(normals[0])
    for _ in range(k - 1):
        distances = directions @ np.array(normals).T
        normals.append(directions[np.argmin(distances.max(axis=1))].copy())
    normals = np.array(normals)
    for _ in range(15):
        assigned = np.argmax(directions @ normals.T, axis=1)
        for j in range(k):
            selected = directions[assigned == j]
            if len(selected):
                center = selected.mean(axis=0)
                normals[j] = center / np.linalg.norm(center)
    return normals


def calibrate(scores, unsafe, regime):
    order = np.argsort(scores, kind='stable')
    sorted_scores, y = scores[order], unsafe[order].astype(int)
    false_allow = np.cumsum(y)
    safe_allow = np.cumsum(1 - y)
    unsafe_n, safe_n = max(int(y.sum()), 1), max(int((1 - y).sum()), 1)
    # Evaluate thresholds only after a complete tie block.
    ends = np.r_[np.flatnonzero(np.diff(sorted_scores)), len(y) - 1]
    fa, fb = false_allow[ends] / unsafe_n, 1 - safe_allow[ends] / safe_n
    if regime == 'safety_1pct':
        eligible = ends[fa <= .01]
        idx = eligible[-1] if len(eligible) else None
    else:
        idx = ends[np.argmin(5 * fa + fb)]
    return float(sorted_scores[idx]) if idx is not None else float(sorted_scores[0] - 1e-8)
