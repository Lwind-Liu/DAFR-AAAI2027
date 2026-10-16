"""Independently remove halfspaces or the joint-risk surface on frozen tasks."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import random
import sys
import numpy as np

import run_workflow_catalog_v2 as catalog
import resume_catalog_v2 as auditor
import export_catalog_baseline_comparison as comparison
from workflow_benchmark.defense import representation
from workflow_benchmark.repair_feedback import admit_with_facts
from relational_dafr.controller import surface_risk
from flash_catalog_client import CatalogClient

ROOT = catalog.ROOT
OUT = ROOT / 'results/summaries/catalog_geometry_split_pilot_v1'
ARMS = ('full', 'no_halfspaces', 'no_joint_surface')


def split_admit(view, arm, model=None):
    if arm == 'full':
        return admit_with_facts(view, 'full')
    if arm not in ARMS:
        raise ValueError(arm)
    scene, halfspaces = representation(view, 'full')
    if arm == 'no_halfspaces':
        allowed = scene is not None and surface_risk(scene) <= scene['budget'] + 1e-12
    else:
        allowed = scene is not None and np.all(halfspaces >= .5)
    if allowed:
        return True, {'reason': 'allowed'}
    # A subset constraint rejects only when the complete guard rejects too.
    # Use exactly the established evidence-based repair feedback.
    allowed_full, detail = admit_with_facts(view, 'full')
    assert not allowed_full
    return False, detail


def prepare():
    catalog.configure_runner()
    catalog.runner.WorkflowWorld = catalog.CatalogWorld
    catalog.runner.admit = catalog.admit = split_admit
    source = ROOT / 'data/workflow_catalog_104/cases.jsonl'
    cases = [json.loads(line) for line in source.read_text().splitlines()]
    counts = Counter()
    diagnostics = []
    for case in cases:
        world = catalog.CatalogWorld(case)
        world.call('read_request', {'request_id': case['request_id']})
        view = world.observer_view('OP-1')
        values = {arm: bool(split_admit(view, arm)[0]) for arm in ARMS}
        for arm in ARMS[1:]:
            if not values['full'] and values[arm]:
                counts[arm] += 1
        diagnostics.append({'id': case['id'], 'lane': case['lane'], **values})
    # Fix a balanced mechanism pilot by lane and domain, before any new run.
    clean = [c for c in cases if c['variant'] == 'clean']
    random.Random(2026101327).shuffle(clean)
    selected, domains = [], Counter()
    for lane in ('signed_snapshot', 'cache_approval_mismatch', 'joint_risk', 'scope_conflict'):
        candidates = [c for c in clean if c['lane'] == lane]
        for _ in range(2):
            choice = min(candidates, key=lambda c: domains[c['domain']])
            candidates.remove(choice)
            selected.append(choice['group_id'])
            domains[choice['domain']] += 1
    selected_cases = [c for c in cases if c['group_id'] in selected]
    assert len(selected_cases) == 16
    OUT.mkdir(parents=True, exist_ok=True)
    content = ''.join(json.dumps(c, sort_keys=True) + '\n' for c in selected_cases)
    protocol = {'pairs': 8, 'arms': list(ARMS), 'new_executions': 32,
        'model': 'deepseek-v4-flash-0731', 'temperature': 0,
        'max_turns': 12, 'max_tool_calls': 32, 'max_tokens': 650,
        'selection': 'Two pairs per lane, domain balance; seeded before new outcomes.',
        'ids': [c['id'] for c in selected_cases],
        'dataset_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'full_reference': 'Existing full DAFR executions, same cases and budgets.',
        'no_halfspaces': 'Remove semantic halfspace checks; keep the unchanged risk surface.',
        'no_joint_surface': 'Remove joint-risk check; keep the unchanged semantic halfspaces.',
        'shared': 'Full evidence projection, lifting, tool validation and fact-based repair feedback.'}
    protocol_path = OUT / 'protocol.json'
    if protocol_path.exists():
        assert json.loads(protocol_path.read_text()) == protocol
    else:
        catalog.dump(protocol_path, protocol)
    (OUT / 'cases.jsonl').write_text(content, encoding='utf-8')
    catalog.dump(OUT / 'initial_decisions.json', {'exclusive_rejections_on_full_104':dict(counts), 'rows':diagnostics})
    print(json.dumps({'initial_exclusive_rejections':dict(counts),'pilot_domains':dict(domains)}), flush=True)
    return selected_cases


def execute(case, arm, client):
    row = catalog.runner.episode(case, arm, None, client, max_turns=12, max_tool_calls=32)
    if row['termination'] not in ('api_error', 'budget_exhausted'):
        auditor.replay(case, row, None)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    cases = prepare()
    if args.prepare_only:
        return
    cases_by_id = {c['id']: c for c in cases}
    path = OUT / 'rows.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    done = {(r['id'], r['arm']) for r in rows}
    original, _, _ = comparison.read_complete(ROOT / 'results/summaries/catalog_fixed104_adapter_v11_104')
    with path.open('a', encoding='utf-8') as stream:
        for row in original:
            if row['arm'] == 'full' and row['id'] in cases_by_id and (row['id'], 'full') not in done:
                auditor.replay(cases_by_id[row['id']], row, None)
                rows.append(row)
                done.add((row['id'], 'full'))
                stream.write(json.dumps(row) + '\n')
        stream.flush()
        jobs = [(c, arm) for c in cases for arm in ARMS[1:] if (c['id'], arm) not in done]
        if jobs:
            key = sys.stdin.readline().strip()
            assert key
            client = CatalogClient(key, OUT, 4.)
            with ThreadPoolExecutor(max_workers=4) as pool:
                for future in as_completed([pool.submit(execute, c, arm, client) for c, arm in jobs]):
                    row = future.result()
                    if row['termination'] in ('api_error', 'budget_exhausted'):
                        with (OUT / 'attempts.log').open('a') as failed:
                            failed.write(json.dumps(row) + '\n')
                    else:
                        rows.append(row)
                        stream.write(json.dumps(row) + '\n')
                        stream.flush()
                    print(json.dumps({'accepted':len(rows), 'id':row['id'], 'arm':row['arm'],
                                      'completed':row['task_completed'], 'termination':row['termination']}), flush=True)
    assert len(rows) == len({(r['id'], r['arm']) for r in rows})
    for row in rows:
        auditor.replay(cases_by_id[row['id']], row, None)
    results = [{'arm':arm, **comparison.metrics([r for r in rows if r['arm'] == arm])}
               for arm in ARMS if any(r['arm'] == arm for r in rows)]
    catalog.dump(OUT / 'summary.json', {'complete':len(rows)==48, 'rows':results})
    catalog.dump(OUT / 'audit.json', {'replayed_episodes':len(rows), 'errors':0, 'complete':len(rows)==48})
    comparison.write_csv(OUT / 'ablation.csv', results)
    print(json.dumps(results), flush=True)


if __name__ == '__main__':
    main()
