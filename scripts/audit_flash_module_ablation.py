"""Replay all controller decisions and business effects without API calls."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from relational_dafr.business_world import AgentWorld
from relational_dafr.module_ablation import ARMS, guard


def main():
    out = ROOT / 'results/summaries/flash_module_ablation_v2'
    data = ROOT / 'data/flash_business_geometry_combined_v1'
    protocol = json.loads((out / 'frozen_protocol.json').read_text(encoding='utf-8'))
    errors = []
    for name, expected in protocol['source_sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            errors.append('source_hash:' + name)
    for name, expected in protocol['data_sha256'].items():
        if hashlib.sha256((data / name).read_bytes()).hexdigest() != expected:
            errors.append('data_hash:' + name)
    cases = {c['id']: c for c in map(json.loads, (data / 'test.jsonl').read_text(encoding='utf-8').splitlines())}
    rows = list(map(json.loads, (out / 'rows.jsonl').read_text(encoding='utf-8').splitlines()))
    model = dict(protocol['baseline'])
    model['weights'] = np.array(model['weights'])
    seen = set()
    for row in rows:
        key = (row['id'], row['arm'])
        if key in seen:
            errors.append('duplicate:' + str(key))
        seen.add(key)
        world = AgentWorld(cases[row['id']])
        for turn in row['trace']:
            for result in turn['results']:
                name, args, response = result['tool'], result['arguments'], result['response']
                if response == {'error': 'invalid_arguments'}:
                    continue
                if name == world.case['tool']:
                    allowed, detail = guard(world, args, row['arm'], model)
                    actual = world.execute(args) if allowed else {'status': 'blocked', **detail}
                else:
                    actual = world.read(name, args)
                if actual != response:
                    errors.append('tool_replay:' + str(key) + ':' + name)
        for name, actual in world.outcome().items():
            if row[name] != actual:
                errors.append('state_replay:' + str(key) + ':' + name)
    expected = {(task, arm) for task in cases for arm in ARMS}
    summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))['arms']
    for arm in ARMS:
        selected = [r for r in rows if r['arm'] == arm]
        for name, actual in [('cases', len(selected)),
            ('safe_successes', sum(r['safe_success'] for r in selected)),
            ('unsafe_commits', sum(r['unsafe_commit'] for r in selected)),
            ('verification_queries', sum(r['verification_queries'] for r in selected))]:
            if summary[arm][name] != actual:
                errors.append('aggregate:' + arm + ':' + name)
    audit = {'cases': len(cases), 'runs': len(rows), 'complete': seen == expected,
        'missing_episodes': len(expected - seen),
        'source_and_data_hashes_checked': True,
        'controller_decisions_and_business_effects_replayed': True,
        'budget_exhausted_episodes': sum(r['termination'] == 'budget_exhausted' for r in rows),
        'errors': errors}
    (out / 'integrity_audit.json').write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(audit))
    assert not errors, errors
    assert audit['complete'] and not audit['budget_exhausted_episodes'], 'Incomplete evaluation'


if __name__ == '__main__':
    main()
