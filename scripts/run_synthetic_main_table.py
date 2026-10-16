"""Portable multi-model runner over the unchanged fixed 104 paired tasks."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'external/official_baselines/AutoDojo/agentdojo/src'))
import catalog_baseline_adapter_v11 as baseline
from portable_catalog_client import PortableClient

METHODS = ('no_defense', 'piguard', 'protectai', 'progent', 'drift', 'full')
DATA_HASH = '5c35f1124a476d8bf0c129b9a083959cfba7cfd6c35aa10daecfb4c4a6fef698'
FAILED = ('api_error', 'infrastructure_error', 'budget_exhausted')


def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def report(rows, cases, methods, out):
    table = []
    for method in methods:
        selected = [r for r in rows if r['arm'] == method]
        clean = [r for r in selected if r['variant'] == 'clean']
        attack = [r for r in selected if r['variant'] == 'attack']
        table.append(dict(method=method, clean_n=len(clean), attack_n=len(attack),
            CU=100*sum(r['task_completed'] for r in clean)/len(clean) if clean else None,
            UA=100*sum(r['task_completed'] for r in attack)/len(attack) if attack else None,
            ASR=100*sum(r['attack_success'] for r in attack)/len(attack) if attack else None,
            total_tool_calls=sum(r['tool_calls'] for r in selected),
            total_llm_calls=sum(r['llm_calls'] for r in selected)))
    complete = len(rows) == len(cases)*len(methods)
    save(out/'summary.json', dict(complete=complete, task_pairs=len(cases)//2,
                                 completed_episodes=len(rows), rows=table))
    import csv
    with (out/'comparison.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(table[0]))
        writer.writeheader(); writer.writerows(table)
    return complete


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', default='config.json')
    p.add_argument('--output', required=True)
    p.add_argument('--methods', nargs='+', choices=METHODS, default=list(METHODS))
    p.add_argument('--pairs', type=int, default=104)
    p.add_argument('--seed', type=int, default=20261013)
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--check', action='store_true', help='Offline data/environment checks only.')
    p.add_argument('--report-only', action='store_true')
    args = p.parse_args()
    assert 1 <= args.pairs <= 104 and args.workers > 0
    config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    assert config['model'] and config['base_url']
    data = ROOT/'data/workflow_catalog_104/cases.jsonl'
    assert hashlib.sha256(data.read_bytes()).hexdigest() == DATA_HASH, 'Dataset changed'
    flat = [json.loads(line) for line in data.read_text(encoding='utf-8').splitlines()]
    groups = {}
    for case in flat: groups.setdefault(case['group_id'], []).append(case)
    assert len(groups) == 104 and all(sorted(c['variant'] for c in pair) == ['attack', 'clean'] for pair in groups.values())
    ids = sorted(groups)
    if args.pairs < 104:
        ids = sorted(random.Random(args.seed).sample(ids, args.pairs))
    cases = {c['id']: c for gid in ids for c in groups[gid]}
    baseline.catalog.configure_runner()
    baseline.catalog.runner.WorkflowWorld = baseline.catalog.CatalogWorld
    baseline.catalog.runner.admit = baseline.catalog.admit
    model = baseline.catalog.simple_linear()
    out = Path(args.output).resolve(); out.mkdir(parents=True, exist_ok=True)
    code = {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest()
            for folder in ('scripts', 'src', 'external/official_baselines/AutoDojo/agentdojo/src')
            for f in sorted((ROOT/folder).rglob('*.py'))}
    protocol = dict(model=config['model'], base_url=config['base_url'],
        extra_body=config.get('extra_body', {}), omit_fields=config.get('omit_fields', []),
        max_tokens_field=config.get('max_tokens_field', 'max_tokens'),
        methods=args.methods, case_ids=list(cases), data_sha256=DATA_HASH,
        code_sha256=code, max_turns=12, max_tool_calls=32, planner_tokens=650,
        defense_tokens=2048, system=baseline.catalog.runner.SYSTEM,
        tools=baseline.catalog.runner.schemas(), seed=args.seed)
    protocol_path = out/'protocol.json'
    if protocol_path.exists():
        assert json.loads(protocol_path.read_text(encoding='utf-8')) == protocol, 'Configuration/code changed: choose a new output directory'
    else: save(protocol_path, protocol)
    # Construct every selected world and evaluate initial admission without an API.
    for case in cases.values():
        world = baseline.catalog.CatalogWorld(case)
        assert 'OP-1' in world.drafts
        baseline.catalog.admit(world.observer_view('OP-1'), 'full', model)
    if args.check:
        print(json.dumps(dict(offline_check='passed', task_pairs=args.pairs,
             episodes=len(cases)*len(args.methods), model=config['model'], api_calls=0)))
        return
    episode_dir = out/'episodes'; episode_dir.mkdir(exist_ok=True)
    rows = [json.loads(f.read_text(encoding='utf-8')) for f in sorted(episode_dir.glob('*.json'))]
    done = set()
    def audit(row):
        case = cases[row['id']]
        if row['arm'] in baseline.METHODS: baseline.audit(case, row)
        else:
            copied = deepcopy(row)
            if copied['arm'] == 'no_defense': copied['arm'] = 'no_geometry'
            baseline.dafr_replay(case, copied, model)
    for row in rows:
        assert row['arm'] in args.methods and row['termination'] not in FAILED
        assert (row['id'], row['arm']) not in done
        audit(row); done.add((row['id'], row['arm']))
    report(rows, cases, args.methods, out)
    jobs = [(case, method) for method in args.methods for case in cases.values() if (case['id'], method) not in done]
    print(json.dumps(dict(completed=len(rows), remaining=len(jobs))), flush=True)
    if args.report_only or not jobs: return
    key = os.environ.get('SYNTH_API_KEY', '')
    if not key: raise SystemExit('Set SYNTH_API_KEY in your environment; never put it in config.json.')
    client = PortableClient(key, config, out)
    # Confirm access before downloading detector models or scheduling all jobs.
    client.chat([{'role': 'user', 'content': 'Reply OK.'}], max_tokens=16)
    filters = {m: baseline.reference.FilterAdapter(m) for m in ('piguard', 'protectai')
               if any(method == m for _, method in jobs)}
    def run(case, method):
        if method in baseline.METHODS:
            row = baseline.episode(case, method, client, filters)
        else:
            row = baseline.catalog.runner.episode(case, 'full' if method == 'full' else 'no_geometry',
                                                  model, client, max_turns=12, max_tool_calls=32)
            row['arm'] = method
        if row['termination'] not in FAILED:
            audit(row)
            save(episode_dir/(case['id']+'__'+method+'.json'), row)
        return row
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run, *job) for job in jobs]
        for future in as_completed(futures):
            row = future.result()
            if row['termination'] in FAILED:
                with (out/'attempts.jsonl').open('a', encoding='utf-8') as f: f.write(json.dumps(row)+'\n')
            else: rows.append(row)
            report(rows, cases, args.methods, out)
            print(json.dumps(dict(completed=len(rows), expected=len(cases)*len(args.methods),
                                 method=row['arm'], termination=row['termination'])), flush=True)
    complete = report(rows, cases, args.methods, out)
    save(out/'audit.json', dict(replayed_episodes=len(rows), errors=0, complete=complete))
    if not complete: raise SystemExit(2)


if __name__ == '__main__': main()
