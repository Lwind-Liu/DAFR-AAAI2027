"""Replay baseline tool traces against the unchanged frozen business world."""
import argparse
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from relational_dafr.operational_failures import AgentWorld


def audit(rows, cases):
    errors, seen = [], set()
    fields = ('safe_success', 'task_completed', 'unsafe_commit', 'effect_count',
              'verification_queries', 'effects', 'final_business_state')
    for row in rows:
        key = row['id'], row['arm']
        if key in seen:
            errors.append({'id': row['id'], 'arm': row['arm'], 'error': 'duplicate'})
        seen.add(key)
        if row.get('reused_from'):
            continue
        world = AgentWorld(cases[row['id']])
        preflight_positions = []
        for call in row.get('defense_calls', []):
            if call.get('kind') != 'planner':
                continue
            match = re.search(r'<function_call>(.*?)</function_call>',
                              call['message'].get('content') or '', re.DOTALL)
            if match and re.search(r'\b' + re.escape(world.case['tool']) + r'\s*\(', match.group(1)):
                preflight_positions.append(sum(m['role'] == 'tool' for m in call['messages']))
        result_position = 0
        for turn in row['trace']:
            for record in turn['results']:
                if any(p <= result_position for p in preflight_positions):
                    world.preflight_attempted = True
                name, args, response = record['tool'], record['arguments'], record['response']
                result_position += 1
                if name == world.case['tool']:
                    world.preflight_attempted = True
                if response.get('status') == 'blocked' or response.get('error') in (
                        'invalid_arguments', 'invalid_tool_schema'):
                    continue
                actual = world.execute(args) if name == world.case['tool'] else world.read(name, args)
                if actual != response:
                    errors.append({'id': row['id'], 'arm': row['arm'], 'turn': turn['turn'],
                                   'error': 'tool_response_mismatch', 'tool': name})
        outcome = world.outcome()
        for field in fields:
            if row[field] != outcome[field]:
                errors.append({'id': row['id'], 'arm': row['arm'], 'error': 'outcome_mismatch', 'field': field})
    return {'rows': len(rows), 'unique_rows': len(seen), 'replayed_new_rows': sum(not r.get('reused_from') for r in rows),
            'errors': errors, 'error_count': len(errors)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    args = parser.parse_args()
    output = ROOT / args.output
    rows = [json.loads(s) for s in (output / 'rows.jsonl').read_text(encoding='utf-8').splitlines()]
    cases = {c['id']: c for c in (json.loads(s) for s in
             (ROOT / 'data/flash_business_geometry_final_v4/test.jsonl').read_text(encoding='utf-8').splitlines())}
    result = audit(rows, cases)
    (output / 'integrity_audit.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    if result['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
