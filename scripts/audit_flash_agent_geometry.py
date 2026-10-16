"""Replay every retained tool trace and independently verify evaluation totals."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from relational_dafr.agent_world import AgentWorld


def audit(output):
    protocol = json.loads((output / 'frozen_protocol.json').read_text())
    world_type = AgentWorld
    if any(name.endswith('business_world.py') for name in protocol['source_sha256']):
        from relational_dafr.business_world import AgentWorld as BusinessWorld
        world_type = BusinessWorld
    data = ROOT / 'data' / output.name
    cases = {c['id']: c for c in map(json.loads, (data / 'test.jsonl').read_text().splitlines())}
    errors = []
    if any(c.get('targeted_regression') for c in cases.values()):
        reference = json.loads((ROOT / 'results/summaries/flash_business_geometry_test_v1/frozen_protocol.json').read_text())
        for key in ('weights', 'bias', 'threshold'):
            if protocol[key] != reference[key]:
                errors.append('changed_reference_model:' + key)
        anchors = {c['id']: c for c in map(json.loads,
            (ROOT / 'data/flash_business_geometry_test_v1/test.jsonl').read_text().splitlines())}
        for case in cases.values():
            anchor = anchors[case['ancestor_id']]
            if case['scene']['paths'] != anchor['scene']['paths']:
                errors.append('changed_neighbor_graph:' + case['id'])
            if abs(case['scene']['budget'] - anchor['scene']['budget']) > .03 * anchor['scene']['budget'] + 1e-6:
                errors.append('neighbor_budget_jitter:' + case['id'])
            for event, record in case['scene']['events'].items():
                if abs(record['probability'] - anchor['scene']['events'][event]['probability']) > .015001:
                    errors.append('neighbor_probability_jitter:' + case['id'])
    if any(c.get('stress_stratum') == 'boundary' for c in cases.values()):
        from relational_dafr.worlds import expected_loss
        for case in cases.values():
            ratio = expected_loss(case['scene']) / case['scene']['budget']
            if abs(ratio - case['oracle_risk_to_budget']) > 1e-12:
                errors.append('oracle_ratio:' + case['id'])
            if case['stress_stratum'] == 'boundary' and not .9 <= ratio <= 1.1:
                errors.append('outside_boundary:' + case['id'])
    for name, expected in protocol['source_sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            errors.append('source_hash:' + name)
    for name, expected in protocol['data_sha256'].items():
        if hashlib.sha256((data / name).read_bytes()).hexdigest() != expected:
            errors.append('data_hash:' + name)
    ids = {}
    for split in ('train', 'dev', 'test'):
        rows = [json.loads(line) for line in (data / f'{split}.jsonl').read_text().splitlines()]
        ids[split] = {c['id'] for c in rows}
    if any(ids[a] & ids[b] for a, b in [('train', 'dev'), ('train', 'test'), ('dev', 'test')]):
        errors.append('split_overlap')
    rows = [json.loads(line) for line in (output / 'rows.jsonl').read_text().splitlines()]
    unique = {(r['id'], r['arm']) for r in rows}
    if len(unique) != len(rows):
        errors.append('duplicate_runs')
    if len(rows) != len(cases) * len(protocol['arms']):
        errors.append('missing_runs')
    for row in rows:
        world = world_type(cases[row['id']])
        for turn in row['trace']:
            for result in turn['results']:
                tool, args, response = result['tool'], result['arguments'], result['response']
                if tool == world.case['tool']:
                    world.preflight_attempted = True
                    if response.get('status') == 'committed':
                        actual = world.execute(args)
                    else:
                        continue
                else:
                    actual = world.read(tool, args)
                if actual != response:
                    errors.append('tool_replay:' + row['id'] + ':' + row['arm'] + ':' + tool)
        if any(row[k] != v for k, v in world.outcome().items()):
            errors.append('outcome_replay:' + row['id'] + ':' + row['arm'])
    result = {'episodes': len(cases), 'runs': len(rows), 'unique_runs': len(unique),
              'split_overlap': False if not any('split_overlap' in e for e in errors) else True,
              'source_and_data_hashes_checked': True, 'all_state_mutations_replayed': True,
              'errors': errors}
    (output / 'integrity_audit.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', nargs='?', default='results/summaries/flash_agent_geometry_test_v1')
    audit(ROOT / parser.parse_args().output)
