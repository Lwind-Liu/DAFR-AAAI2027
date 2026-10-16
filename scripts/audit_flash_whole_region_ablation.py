"""Audit whole-region replacement and reused unchanged module episodes."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from relational_dafr.business_world import AgentWorld
from relational_dafr.whole_region_ablation import guard


def main():
    out = ROOT / 'results/summaries/flash_whole_region_ablation_v3'
    data = ROOT / 'data/flash_business_geometry_combined_v1'
    protocol = json.loads((out / 'frozen_protocol.json').read_text())
    errors = []
    for name, sha in protocol['source_sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != sha:
            errors.append('source_hash:' + name)
    for name, sha in protocol['data_sha256'].items():
        if hashlib.sha256((data / name).read_bytes()).hexdigest() != sha:
            errors.append('data_hash:' + name)
    cases = {c['id']: c for c in map(json.loads, (data / 'test.jsonl').read_text().splitlines())}
    rows = list(map(json.loads, (out / 'rows.jsonl').read_text().splitlines()))
    model = dict(protocol['linear_model'])
    model['weights'] = np.array(model['weights'])
    seen = set()
    old = {(r['id'], r['arm']): r for r in map(json.loads,
        (ROOT / 'results/summaries/flash_module_ablation_v2/rows.jsonl').read_text().splitlines())}
    for row in rows:
        key = (row['id'], row['arm'])
        if key in seen:
            errors.append('duplicate:' + str(key))
        seen.add(key)
        if row['arm'] in protocol['reused_arms'] and row != old[key]:
            errors.append('reuse_changed:' + str(key))
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
                    errors.append('tool_replay:' + str(key))
        if any(row[k] != v for k, v in world.outcome().items()):
            errors.append('state_replay:' + str(key))
    expected = {(task, arm) for task in cases for arm in protocol['display_arms']}
    summary = json.loads((out / 'summary.json').read_text())['arms']
    for arm in protocol['display_arms']:
        part = [r for r in rows if r['arm'] == arm]
        for name, actual in [('cases', len(part)),
            ('safe_successes', sum(r['safe_success'] for r in part)),
            ('unsafe_commits', sum(r['unsafe_commit'] for r in part)),
            ('verification_queries', sum(r['verification_queries'] for r in part))]:
            if summary[arm][name] != actual:
                errors.append('aggregate:' + arm + ':' + name)
    audit = {'tasks': len(cases), 'episodes': len(rows), 'complete': seen == expected,
        'new_episodes': sum(r['arm'] in protocol['paid_arms'] for r in rows),
        'reused_episodes': sum(r['arm'] in protocol['reused_arms'] for r in rows),
        'budget_exhausted_episodes': sum(r['termination'] == 'budget_exhausted' for r in rows),
        'hashes_and_reused_rows_checked': True,
        'controller_decisions_and_business_states_replayed': True, 'errors': errors}
    (out / 'integrity_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    print(json.dumps(audit))
    assert audit['complete'] and not errors and not audit['budget_exhausted_episodes'], audit


if __name__ == '__main__':
    main()
