"""Development-gated, grouped holdout study of linear vs nonlinear capacity."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from geometry_capacity.scenes import generate
from geometry_capacity.simulator import replay
from geometry_capacity.backends import coordinates, decide, edit_candidates, fit_linear, supporting_planes, calibrate, repair

DATA = ROOT / 'data/geometry_capacity_v1'
OUT = ROOT / 'results/summaries/geometry_capacity_v1'
KS = (1, 4, 16, 64)
REGIMES = ('weighted', 'safety_1pct')


def json_safe(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=json_safe) + '\n', encoding='utf-8')


def jsonl(path, rows):
    path.write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows), encoding='utf-8')


def matrix(cases):
    return np.array([[*coordinates(c, c['proposal'])[0], coordinates(c, c['proposal'])[1]] for c in cases])


def fit_models(train, dev):
    train = [c for c in train if c['plant']['law'] == 'quadratic']
    dev = [c for c in dev if c['plant']['law'] == 'quadratic']
    x, xd = matrix(train), matrix(dev)
    y = np.array([not replay(c, c['proposal'])['safe'] for c in train])
    yd = np.array([not replay(c, c['proposal'])['safe'] for c in dev])
    base = fit_linear(x, y)
    arms = {
        'geometry': {'mode': 'full'}, 'nonlinear_arithmetic': {'mode': 'arithmetic_control'},
        'no_joint_budget': {'mode': 'no_joint_budget'},
        'no_cross_channel': {'mode': 'no_cross_channel'},
        'no_cooling_credit': {'mode': 'no_cooling_credit'},
        'static_state': {'mode': 'static_state'}, 'no_repair': {'mode': 'no_repair'},
    }
    for regime in REGIMES:
        model = {**base, 'threshold': calibrate(xd @ base['weights'] + base['bias'], yd, regime)}
        arms[f'learned_linear_{regime}'] = {'mode': 'learned_linear', 'model': model}
    for k in KS:
        normals = supporting_planes(x, k)
        scores = np.max(xd[:, :3] @ normals.T, axis=1) / (1 + xd[:, 3])
        for regime in REGIMES:
            arms[f'linear_{k}_planes_{regime}'] = {'mode': 'linear_polytope',
                'model': {'normals': normals, 'threshold': calibrate(scores, yd, regime)}}
    return arms


def original_row(case, name, params):
    truth = replay(case, case['proposal'])
    mode = 'full' if params['mode'] == 'no_repair' else params['mode']
    allowed = decide(case, case['proposal'], mode, params.get('model'))
    return {'id': case['id'], 'group_id': case['group_id'], 'profile': case['profile'], 'cohort': case['cohort'],
            'variant': case['variant'], 'law': case['plant']['law'], 'arm': name,
            'safe_original': truth['safe'], 'allowed': bool(allowed)}


def summary(rows):
    safe = sum(r['safe_original'] for r in rows)
    unsafe = len(rows) - safe
    fa = sum(r['allowed'] and not r['safe_original'] for r in rows)
    fb = sum(not r['allowed'] and r['safe_original'] for r in rows)
    value = {'cases': len(rows), 'safe': safe, 'unsafe': unsafe, 'false_allow': fa, 'false_block': fb,
             'fa_rate': fa / unsafe if unsafe else None, 'fb_rate': fb / safe if safe else None,
             'balanced_accuracy': 1 - .5 * (fa / unsafe + fb / safe) if safe and unsafe else None,
             'accuracy': 1 - (fa + fb) / len(rows)}
    if rows and 'oracle_recoverable' in rows[0]:
        value.update(oracle_recoverable=sum(r['oracle_recoverable'] for r in rows),
                     successful_outputs=sum(r['output_success'] for r in rows),
                     unsafe_outputs=sum(r['output_present'] and not r['output_safe'] for r in rows),
                     recoverable_failed_originals=sum(r['oracle_recoverable'] and not r['safe_original'] for r in rows),
                     recovered_failed_originals=sum(r['output_success'] and not r['safe_original'] for r in rows))
    return value


def paired_ci(rows, other, repeats=2000):
    by_id = defaultdict(dict)
    for r in rows:
        if r['arm'] in ('geometry', other):
            by_id[r['id']][r['arm']] = r
    group_values = defaultdict(list)
    for pair in by_id.values():
        g, b = pair['geometry'], pair[other]
        group_values[g['group_id']].append(int(g['allowed'] == g['safe_original']) - int(b['allowed'] == b['safe_original']))
    values = [sum(v) / len(v) for v in group_values.values()]
    rng = random.Random(20261011)
    resamples = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(repeats))
    return {'metric': 'paired decision accuracy difference', 'groups': len(values),
            'difference': sum(values) / len(values), 'ci95': [resamples[int(.025 * repeats)], resamples[int(.975 * repeats)]]}


def main():
    cases = generate()
    train = [c for c in cases if c['split'] == 'train']
    dev = [c for c in cases if c['split'] == 'dev']
    arms = fit_models(train, dev)
    dev_rows = [original_row(c, name, params) for c in dev for name, params in arms.items()]
    dev_summaries = {name: summary([r for r in dev_rows if r['arm'] == name and r['law'] == 'quadratic']) for name in arms}
    print('Development gate:', flush=True)
    for name in ('geometry', 'learned_linear_weighted', 'linear_4_planes_weighted', 'linear_64_planes_weighted'):
        print(name, json.dumps(dev_summaries[name]), flush=True)
    gate = (dev_summaries['geometry']['false_allow'] == 0 and dev_summaries['geometry']['false_block'] == 0
            and dev_summaries['geometry']['balanced_accuracy'] - dev_summaries['learned_linear_weighted']['balanced_accuracy'] >= .05
            and dev_summaries['geometry']['balanced_accuracy'] - dev_summaries['linear_4_planes_weighted']['balanced_accuracy'] >= .02)
    if not gate:
        print('FAILED development gate. No dataset/results frozen; discard this prototype.', flush=True)
        raise SystemExit(2)
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for split in ('train', 'dev', 'test'):
        subset = [c for c in cases if c['split'] == split]
        jsonl(DATA / f'{split}.jsonl', subset)
        jsonl(DATA / f'{split}_inputs.jsonl', [{'id': hashlib.sha256(c['id'].encode()).hexdigest()[:20],
            **{k: c[k] for k in ('plant', 'state', 'history', 'proposal', 'goal', 'policy_text')}} for c in subset])
        jsonl(DATA / f'{split}_labels.jsonl', [{'id': hashlib.sha256(c['id'].encode()).hexdigest()[:20],
            'evaluator_id': c['id'], 'result': replay(c, c['proposal'])} for c in subset])
    # Freeze settings and models before consulting held-out labels.
    sources = [Path(__file__), *sorted((ROOT / 'src/geometry_capacity').glob('*.py')),
               ROOT / 'src/clafr/geometry.py', ROOT / 'src/clafr/schemas.py']
    manifest = {'seed': 20261011, 'cases': len(cases), 'base_groups': len({c['group_id'] for c in cases}),
        'counts': {s: len([c for c in cases if c['split'] == s]) for s in ('train', 'dev', 'test')},
        'development_gate': {'passed': gate, 'learned_linear_gap_min': .05, 'four_plane_gap_min': .02},
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        'data_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.glob('*.jsonl')},
        'scope': 'Synthetic, uncalibrated physical capacity model; actual clafr geometry primitives with new deterministic lifting, not production semantic encoder/compiler or AgentDojo task runs.',
        'arms': arms, 'selection': 'All generated scenarios retained; train fits weights/normals, dev chooses thresholds; test used only after freezing.'}
    dump(DATA / 'manifest.json', manifest)
    dump(OUT / 'dev_calibration.json', {'models': arms, 'metrics': dev_summaries})
    rows = []
    test = [c for c in cases if c['split'] == 'test']
    for i, c in enumerate(test):
        feasible = [q for q in edit_candidates(c) if replay(c, q)['success']]
        for name, params in arms.items():
            r = original_row(c, name, params)
            output = repair(c, params['mode'], params.get('model'))
            execution = replay(c, output) if output is not None else None
            r.update(oracle_recoverable=bool(feasible), output_present=output is not None,
                     output_safe=bool(execution and execution['safe']), output_success=bool(execution and execution['success']),
                     output=output, output_violations=execution['violations'] if execution else [])
            if name in ('geometry', 'nonlinear_arithmetic') and r['allowed'] != r['safe_original']:
                raise AssertionError(f'Exact implementation disagrees with simulator: {c["id"]} {name}')
            rows.append(r)
        if (i + 1) % 60 == 0:
            print(f'Test: {i + 1}/{len(test)} scenes x {len(arms)} arms', flush=True)
    jsonl(OUT / 'test_rows.jsonl', rows)
    nonlinear = [r for r in rows if r['law'] == 'quadratic']
    aggregates = {'by_arm': {a: summary([r for r in nonlinear if r['arm'] == a]) for a in arms},
        'linear_control': {a: summary([r for r in rows if r['arm'] == a and r['law'] == 'linear']) for a in arms},
        'by_cohort': {co: {a: summary([r for r in nonlinear if r['arm'] == a and r['cohort'] == co]) for a in arms}
                      for co in ('broad', 'boundary', 'axis_stress')},
        'by_variant': {v: {a: summary([r for r in nonlinear if r['arm'] == a and r['variant'] == v]) for a in arms}
                       for v in sorted({r['variant'] for r in nonlinear})},
        'paired_group_ci': {a: paired_ci(nonlinear, a) for a in arms if a != 'geometry'}}
    dump(OUT / 'summary.json', {'manifest': manifest, 'test': aggregates})
    lines = ['# Geometry capacity v1', '', 'Held-out quadratic-model subset; metrics verified by independent local simulator.', '',
             '| Arm | False allow / unsafe | False block / safe | Task-success outputs / recoverable | Unsafe outputs |',
             '|---|---:|---:|---:|---:|']
    for a, s in aggregates['by_arm'].items():
        lines.append(f"| {a} | {s['false_allow']}/{s['unsafe']} | {s['false_block']}/{s['safe']} | {s['successful_outputs']}/{s['oracle_recoverable']} | {s['unsafe_outputs']} |")
    lines += ['', 'The nonlinear arithmetic control expresses the same constraint and should tie geometry.',
              'Linear baselines use the same current/cooling coordinates. Supporting-plane count is an explicit complexity budget.',
              'This is a simulator representation/ablation study, not evidence of production DAFR end-to-end performance.', '']
    (OUT / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines), flush=True)


if __name__ == '__main__':
    main()
