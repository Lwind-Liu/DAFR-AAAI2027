"""Audit frozen outputs and the entire predeclared repair grammar; no fitting."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from geometry_capacity.backends import coordinates, decide, edit_candidates, repair
from geometry_capacity.simulator import replay

DATA = ROOT / 'data/geometry_capacity_v1'
OUT = ROOT / 'results/summaries/geometry_capacity_v1'


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def main():
    manifest = json.loads((DATA / 'manifest.json').read_text(encoding='utf-8'))
    for path, expected in manifest['source_sha256'].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    for path, expected in manifest['data_sha256'].items():
        assert hashlib.sha256((DATA / path).read_bytes()).hexdigest() == expected, path
    splits = {s: read_rows(DATA / f'{s}.jsonl') for s in ('train', 'dev', 'test')}
    groups = {s: {c['group_id'] for c in rows} for s, rows in splits.items()}
    assert not (groups['train'] & groups['dev'] or groups['train'] & groups['test'] or groups['dev'] & groups['test'])
    arms = manifest['arms']
    for params in arms.values():
        for key in ('normals', 'weights'):
            if key in params.get('model', {}):
                params['model'][key] = np.array(params['model'][key])
    recorded = {(r['id'], r['arm']): r for r in read_rows(OUT / 'test_rows.jsonl')}
    names = ['geometry', 'nonlinear_arithmetic'] + [a for a in arms if a.startswith(('linear_', 'learned_linear_'))]
    stats = {a: {'candidates': 0, 'safe_candidates': 0, 'unsafe_candidates': 0,
                 'false_allow': 0, 'false_block': 0, 'affected_groups': set()} for a in names}
    witnesses = []
    for case in splits['test']:
        options = list(edit_candidates(case))
        truth = [replay(case, q) for q in options]
        expected = next((q for q, t in zip(options, truth) if t['success']), None)
        assert repair(case, 'full') == expected
        assert repair(case, 'arithmetic_control') == expected
        assert case['state']['version'] == replay(case, case['proposal'])['after']['version'] - int(replay(case, case['proposal'])['safe'])
        for name, params in arms.items():
            output = repair(case, params['mode'], params.get('model'))
            record = recorded[case['id'], name]
            assert output == record['output'], (case['id'], name)
            t = replay(case, output) if output is not None else None
            assert record['output_success'] == bool(t and t['success'])
            assert record['output_safe'] == bool(t and t['safe'])
            assert record['oracle_recoverable'] == (expected is not None)
        if case['plant']['law'] != 'quadratic':
            # Positive control: full geometry and linear representations agree.
            for name in names:
                assert recorded[case['id'], name]['output'] == expected
            continue
        loads_credit = [coordinates(case, q) for q in options]
        x = np.array([[*loads, credit] for loads, credit in loads_credit])
        safe = np.array([t['safe'] for t in truth])
        for name in names:
            params = arms[name]
            model = params.get('model')
            if params['mode'] == 'linear_polytope':
                allowed = np.max(x[:, :3] @ model['normals'].T, axis=1) <= model['threshold'] * (1 + x[:, 3])
            elif params['mode'] == 'learned_linear':
                allowed = x @ model['weights'] + model['bias'] <= model['threshold']
            else:
                allowed = np.array([decide(case, q, params['mode']) for q in options])
            fa, fb = allowed & ~safe, ~allowed & safe
            s = stats[name]
            s['candidates'] += len(options)
            s['safe_candidates'] += int(safe.sum())
            s['unsafe_candidates'] += int((~safe).sum())
            s['false_allow'] += int(fa.sum())
            s['false_block'] += int(fb.sum())
            if fa.any() or fb.any():
                s['affected_groups'].add(case['group_id'])
            # Verify every batch decision against the actual backend primitives.
            if model is not None:
                assert allowed.tolist() == [decide(case, q, params['mode'], model) for q in options]
            if name == 'linear_64_planes_safety_1pct' and fa.any() and len(witnesses) < 3:
                j = int(np.flatnonzero(fa)[0])
                witnesses.append({'id': case['id'], 'arm': name, 'original': case['proposal'],
                                  'edited': options[j], 'execution': truth[j],
                                  'linear_margin': float(model['threshold'] * (1 + x[j, 3]) - np.max(x[j, :3] @ model['normals'].T)),
                                  'geometry_allowed': decide(case, options[j])})
    for name, s in stats.items():
        s['affected_groups'] = len(s['affected_groups'])
    assert stats['geometry']['false_allow'] == stats['geometry']['false_block'] == 0
    assert stats['nonlinear_arithmetic'] == stats['geometry']
    report = {'checks': 'Frozen source/data hashes, split separation, replayed outputs, equal search grammar, exact controls, every linear batch decision matched native primitives.',
              'candidate_metrics': stats, 'witnesses': witnesses,
              'caveat': 'Candidates within each base group are correlated; counts are descriptive, not independent sample sizes. Audit does not recalibrate models.'}
    (OUT / 'candidate_audit.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'checks': report['checks'], 'candidate_metrics': stats}, indent=2))


if __name__ == '__main__':
    main()
