"""Matched sequential end-to-end timing of all six methods on two task pairs."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
import time

import catalog_baseline_adapter_v11 as baseline
from flash_catalog_client import CatalogClient
from workflow_benchmark.repair_feedback import admit_with_facts
import export_catalog_baseline_comparison as comparison

ROOT = baseline.ROOT
OUT = ROOT / 'results/summaries/catalog_latency_pilot_v1'


def main():
    catalog = baseline.catalog
    catalog.configure_runner()
    catalog.runner.WorkflowWorld = catalog.CatalogWorld
    catalog.runner.admit = admit_with_facts
    data = ROOT / 'data/workflow_catalog_104/cases.jsonl'
    all_cases = [json.loads(line) for line in data.read_text().splitlines()]
    groups = ['CAT-001-ac8aa168', 'CAT-017-55c76caa']
    cases = [c for c in all_cases if c['group_id'] in groups]
    assert len(cases) == 4
    methods = [m for m, _ in comparison.METHODS]
    OUT.mkdir(exist_ok=True)
    protocol = {'episodes': 24, 'ids': [c['id'] for c in cases], 'methods': methods,
        'model': 'deepseek-v4-flash-0731', 'temperature': 0, 'max_turns': 12,
        'max_tool_calls': 32, 'planner_tokens': 650, 'defense_tokens': 2048,
        'concurrency': 1, 'seed': 2026101319,
        'timing': 'End-to-end episode including planner, defense, verification and tools. Model weights loaded and local detector inference warmed before measurements.',
        'data_sha256': hashlib.sha256(data.read_bytes()).hexdigest(),
        'adapter_sha256': hashlib.sha256(Path(baseline.__file__).read_bytes()).hexdigest(),
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    path = OUT / 'protocol.json'
    if path.exists():
        assert json.loads(path.read_text()) == protocol
    else:
        catalog.dump(path, protocol)
    rows_path = OUT / 'rows.jsonl'
    rows = [json.loads(line) for line in rows_path.read_text().splitlines()] if rows_path.exists() else []
    done = {(r['id'], r['arm']) for r in rows}
    jobs = [(c, m) for c in cases for m in methods if (c['id'], m) not in done]
    random.Random(2026101319).shuffle(jobs)
    print(json.dumps({'accepted': len(rows), 'remaining': len(jobs), 'concurrency': 1}), flush=True)
    if jobs:
        key = sys.stdin.readline().strip()
        assert key
        client = CatalogClient(key, OUT, 4.)
        filters = {m: baseline.reference.FilterAdapter(m) for m in ('piguard', 'protectai')}
        for detector in filters.values():
            detector.filter('Routine operational record. Reconcile the approved request.')
        with rows_path.open('a') as stream:
            for case, method in jobs:
                started = time.perf_counter()
                if method in baseline.METHODS:
                    row = baseline.episode(case, method, client, filters)
                else:
                    arm = 'full' if method == 'full' else 'no_geometry'
                    row = catalog.runner.episode(case, arm, None, client, max_turns=12, max_tool_calls=32)
                row['wall_seconds'] = time.perf_counter() - started
                row['arm'] = method
                if row['termination'] in ('infrastructure_error', 'api_error', 'budget_exhausted'):
                    with (OUT / 'attempts.log').open('a') as failed:
                        failed.write(json.dumps(row) + '\n')
                else:
                    if method in baseline.METHODS:
                        baseline.audit(case, row)
                    else:
                        replay = deepcopy(row)
                        if method == 'no_defense':
                            replay['arm'] = 'no_geometry'
                        baseline.dafr_replay(case, replay, None)
                    rows.append(row)
                    stream.write(json.dumps(row) + '\n')
                    stream.flush()
                print(json.dumps({'accepted': len(rows), 'method': method, 'id': case['id'],
                    'seconds': round(row['wall_seconds'], 2), 'termination': row['termination']}), flush=True)
                if client.fatal_error:
                    break
    result = []
    for method, label in comparison.METHODS:
        selected = [r for r in rows if r['arm'] == method]
        if not selected:
            continue
        values = [r['wall_seconds'] for r in selected]
        result.append({'Method': label, 'Episodes': len(values),
            'Mean seconds': statistics.mean(values), 'Std seconds': statistics.stdev(values) if len(values) > 1 else 0,
            'Median seconds': statistics.median(values),
            'Mean LLM calls': statistics.mean(r['llm_calls'] for r in selected),
            'Mean tool calls': statistics.mean(r['tool_calls'] for r in selected)})
    catalog.dump(OUT / 'summary.json', {'complete': len(rows) == 24, 'rows': result})
    catalog.dump(OUT / 'audit.json', {'replayed_episodes': len(rows), 'errors': 0, 'complete': len(rows) == 24})
    comparison.write_csv(OUT / 'latency.csv', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
