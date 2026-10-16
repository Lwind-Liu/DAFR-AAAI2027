"""Separate matched-budget diagnosis for the two long pilot workflows."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import sys

import run_catalog_dynamic_pilot as pilot
from flash_catalog_client import CatalogClient
import export_catalog_baseline_comparison as comparison

ROOT = pilot.ROOT
OUT = ROOT / 'results/summaries/catalog_long_budget_probe_v1'


def episode(case, mode, client):
    guard = pilot.JointRiskGuard(mode)
    token = pilot.CURRENT.set(guard)
    try:
        row = pilot.catalog.runner.episode(case, mode, None, client, max_turns=24, max_tool_calls=32)
        row['risk_decisions'] = guard.decisions
        pilot.audit(case, row)
        return row
    finally:
        pilot.CURRENT.reset(token)


def main():
    protocol = json.loads((pilot.OUT / 'protocol.json').read_text())
    all_cases = json.loads((pilot.OUT / 'selected_cases.json').read_text())
    cases = [c for c in all_cases if protocol['reference_lengths'][c['group_id']] == 16]
    assert len(cases) == 4
    pilot.catalog.configure_runner()
    pilot.catalog.runner.WorkflowWorld = pilot.catalog.CatalogWorld
    pilot.catalog.runner.admit = pilot.admission
    OUT.mkdir(exist_ok=True)
    frozen = {'episodes': 8, 'pairs': 2, 'ids': [c['id'] for c in cases],
        'reason': 'Matched 24-turn diagnosis because the 16-step clean reference procedure exceeds the original 12-turn allowance.',
        'max_turns': 24, 'max_tool_calls': 32, 'planner_tokens': 650,
        'model': 'deepseek-v4-flash-0731', 'temperature': 0,
        'source_sha256': hashlib.sha256(Path(pilot.__file__).read_bytes()).hexdigest(),
        'data_sha256': protocol['data_sha256']}
    path = OUT / 'protocol.json'
    if path.exists():
        assert json.loads(path.read_text()) == frozen
    else:
        pilot.catalog.dump(path, frozen)
    row_path = OUT / 'rows.jsonl'
    rows = [json.loads(line) for line in row_path.read_text().splitlines()] if row_path.exists() else []
    done = {(r['id'], r['arm']) for r in rows}
    jobs = [(c, mode) for c in cases for mode in ('dynamic', 'static') if (c['id'], mode) not in done]
    if jobs:
        key = sys.stdin.readline().strip()
        assert key
        client = CatalogClient(key, OUT, 2.)
        with ThreadPoolExecutor(max_workers=4) as pool, row_path.open('a') as stream:
            for future in as_completed([pool.submit(episode, c, mode, client) for c, mode in jobs]):
                row = future.result()
                if row['termination'] in ('api_error', 'budget_exhausted'):
                    with (OUT / 'attempts.log').open('a') as failed:
                        failed.write(json.dumps(row) + '\n')
                else:
                    rows.append(row)
                    stream.write(json.dumps(row) + '\n')
                    stream.flush()
                print(json.dumps({'accepted': len(rows), 'arm': row['arm'], 'termination': row['termination']}), flush=True)
    by_id = {c['id']: c for c in cases}
    for row in rows:
        pilot.audit(by_id[row['id']], row)
    assert len(rows) == len({(r['id'], r['arm']) for r in rows})
    result = [{'Configuration': mode, **comparison.metrics([r for r in rows if r['arm'] == mode])}
              for mode in ('dynamic', 'static') if any(r['arm'] == mode for r in rows)]
    pilot.catalog.dump(OUT / 'summary.json', {'complete': len(rows) == 8, 'rows': result})
    pilot.catalog.dump(OUT / 'audit.json', {'replayed_episodes': len(rows), 'errors': 0, 'complete': len(rows) == 8})
    comparison.write_csv(OUT / 'comparison.csv', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
