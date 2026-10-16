"""Audit and merge every fixed operational-extension episode into the suite."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from relational_dafr.operational_failures import AgentWorld
from relational_dafr.whole_region_ablation import guard

ARMS = {'full_surface': 'DAFR', 'no_projection': 'w/o Evidence Projection',
    'no_lifting': 'w/o Action-Evidence Lifting', 'linear_region': 'w/o Geometric Modeling',
    'no_geometric_region': 'w/o Feasibility Constraints'}


def main():
    old = ROOT / 'results/summaries/flash_whole_region_ablation_v3'
    new = ROOT / 'results/summaries/flash_operational_extension_v1'
    out = ROOT / 'results/summaries/flash_business_geometry_final_v4'
    data = ROOT / 'data/flash_business_geometry_final_v4'
    out.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    old_data = ROOT / 'data/flash_business_geometry_combined_v1'
    new_data = ROOT / 'data/flash_operational_extension_v1'
    protocol = json.loads((new / 'frozen_protocol.json').read_text())
    errors = []
    for name, expected in protocol['source_sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            errors.append('source_hash:' + name)
    if hashlib.sha256((new_data / 'test.jsonl').read_bytes()).hexdigest() != protocol['data_sha256']:
        errors.append('new_data_hash')
    old_protocol = json.loads((old / 'frozen_protocol.json').read_text())
    assert protocol['linear_model'] == old_protocol['linear_model']
    for key in ('model', 'temperature', 'thinking', 'max_tokens', 'max_turns', 'verification_budget', 'system_prompt'):
        assert protocol[key] == old_protocol[key], key
    for name, expected in old_protocol['data_sha256'].items():
        assert hashlib.sha256((old_data / name).read_bytes()).hexdigest() == expected
    read = lambda p: list(map(json.loads, p.read_text().splitlines()))
    cases = read(old_data / 'test.jsonl') + read(new_data / 'test.jsonl')
    rows = read(old / 'rows.jsonl') + read(new / 'rows.jsonl')
    assert len(cases) == 196 and len({c['id'] for c in cases}) == 196
    assert len(rows) == 980 and len({(r['id'], r['arm']) for r in rows}) == 980
    by_id = {c['id']: c for c in cases}
    model = dict(protocol['linear_model'])
    model['weights'] = np.array(model['weights'])
    for row in rows:
        world = AgentWorld(by_id[row['id']])
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
                    errors.append('tool_replay:' + row['id'] + ':' + row['arm'])
        if any(row[k] != v for k, v in world.outcome().items()):
            errors.append('state_replay:' + row['id'] + ':' + row['arm'])
    assert not errors, errors
    assert not any(r['termination'] == 'budget_exhausted' or ':' in r['termination'] for r in rows)
    for split in ('train', 'dev'):
        shutil.copyfile(old_data / (split + '.jsonl'), data / (split + '.jsonl'))
    (data / 'test.jsonl').write_text(''.join(json.dumps(c) + '\n' for c in cases), encoding='utf-8')
    (out / 'rows.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
    summary = {}
    for arm in ARMS:
        part = [r for r in rows if r['arm'] == arm]
        summary[arm] = {'cases': len(part), 'safe_successes': sum(r['safe_success'] for r in part),
            'safe_success_pct': 100 * sum(r['safe_success'] for r in part) / len(part),
            'unsafe_commits': sum(r['unsafe_commit'] for r in part),
            'verification_queries': sum(r['verification_queries'] for r in part),
            'incomplete_tasks': sum(not r['task_completed'] for r in part)}
    failures = []
    for row in rows:
        if row['arm'] == 'full_surface' and not row['safe_success']:
            failures.append({'id': row['id'], 'domain': row['domain'],
                'scenario': by_id[row['id']].get('operational_scenario'),
                'termination': row['termination'], 'unsafe_commit': row['unsafe_commit'],
                'service_failures': sum(x['response'].get('error') == 'service_unavailable'
                    for t in row['trace'] for x in t['results']),
                'verification_calls': row['verification_queries']})
    dump = lambda p, value: p.write_text(json.dumps(value, indent=2) + '\n')
    dump(out / 'summary.json', {'arms': summary})
    dump(out / 'full_method_failure_cases.json', failures)
    dump(out / 'integrity_audit.json', {'tasks': 196, 'episodes': 980,
        'every_configuration_has_all_tasks': all(s['cases'] == 196 for s in summary.values()),
        'method_and_model_parameters_unchanged': True,
        'controller_decisions_and_business_states_replayed': True, 'errors': errors})
    dump(out / 'frozen_protocol.json', {'dataset': 'flash_business_geometry_final_v4',
        'tasks': 196, 'episodes': 980, 'arms': list(ARMS),
        'base_tasks': 172, 'operational_extension_tasks': 24,
        'construction_record': str((old_data.parent / 'flash_business_geometry_combined_v1').relative_to(ROOT)),
        'operational_extension_protocol': str((new / 'frozen_protocol.json').relative_to(ROOT)),
        'all_cases_retained': True, 'method_and_model_parameters_unchanged': True,
        'data_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in data.glob('*.jsonl')},
        'source_records_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (old / 'rows.jsonl', new / 'rows.jsonl', old / 'frozen_protocol.json', new / 'frozen_protocol.json')}})
    with (out / 'paper_results.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Configuration', 'Safe task success (%)', 'Unsafe executions', 'Verification calls'])
        for arm, label in ARMS.items():
            s = summary[arm]
            w.writerow([label, f"{s['safe_success_pct']:.1f}", s['unsafe_commits'], s['verification_queries']])
    print(json.dumps({'results': summary, 'full_method_failure_cases': failures}, indent=2))


if __name__ == '__main__':
    main()
