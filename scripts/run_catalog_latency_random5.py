"""Random five paired tasks, matched sequential timing of all six methods."""
from copy import deepcopy
import getpass
import hashlib
import json
from pathlib import Path
import random
import statistics
import time

import catalog_baseline_adapter_v11 as baseline
from flash_catalog_client import CatalogClient
import export_catalog_baseline_comparison as comparison

ROOT = baseline.ROOT
OUT = ROOT/'results/summaries/catalog_latency_random5_v1'
SEED = 20261014


def summarize(rows):
    result = []
    for method, label in comparison.METHODS:
        selected = [r for r in rows if r['arm'] == method]
        if not selected: continue
        values = [r['wall_seconds'] for r in selected]
        result.append({'Method': label, 'Episodes': len(selected),
            'Mean seconds': statistics.mean(values),
            'Std seconds': statistics.stdev(values) if len(values)>1 else 0,
            'Median seconds': statistics.median(values),
            'Mean LLM calls': statistics.mean(r['llm_calls'] for r in selected),
            'Mean tool calls': statistics.mean(r['tool_calls'] for r in selected)})
    baseline.catalog.dump(OUT/'summary.json', {'complete': len(rows)==60, 'rows': result})
    if result: comparison.write_csv(OUT/'latency.csv', result)
    return result


def main():
    catalog = baseline.catalog
    catalog.configure_runner()
    catalog.runner.WorkflowWorld = catalog.CatalogWorld
    catalog.runner.admit = catalog.admit
    data = ROOT/'data/workflow_catalog_104/cases.jsonl'
    all_cases = [json.loads(line) for line in data.read_text().splitlines()]
    groups = sorted(random.Random(SEED).sample(sorted({c['group_id'] for c in all_cases}), 5))
    cases = [c for c in all_cases if c['group_id'] in groups]
    assert len(cases)==10
    methods = [m for m, _ in comparison.METHODS]
    OUT.mkdir(exist_ok=True)
    protocol = {'episodes': 60, 'ids': [c['id'] for c in cases], 'methods': methods,
        'model': 'deepseek-v4-flash-0731', 'temperature': 0, 'max_turns': 12,
        'max_tool_calls': 32, 'planner_tokens': 650, 'defense_tokens': 2048,
        'concurrency': 1, 'seed': SEED, 'sampling': 'Uniform random sample of five task pairs from frozen 104 before outcomes; no outcome filtering',
        'timing': 'End-to-end episode including planner, defense, verification and tools. Detectors loaded and warmed before timing; audit and result-file writes excluded.',
        'data_sha256': hashlib.sha256(data.read_bytes()).hexdigest(),
        'adapter_sha256': hashlib.sha256(Path(baseline.__file__).read_bytes()).hexdigest(),
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if (OUT/'protocol.json').exists(): assert json.loads((OUT/'protocol.json').read_text())==protocol
    else: catalog.dump(OUT/'protocol.json', protocol)
    path = OUT/'rows.jsonl'
    rows = [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
    done = {(r['id'], r['arm']) for r in rows}
    assert len(done)==len(rows)
    jobs = [(c,m) for c in cases for m in methods if (c['id'],m) not in done]
    random.Random(SEED).shuffle(jobs)
    print(json.dumps({'groups':groups,'accepted':len(rows),'remaining':len(jobs),'concurrency':1}), flush=True)
    if jobs:
        key = getpass.getpass('API key: ').strip()
        assert key
        client = CatalogClient(key, OUT, 8.)
        client.chat([{'role':'user','content':'Reply OK.'}], max_tokens=16)
        filters = {m:baseline.reference.FilterAdapter(m) for m in ('piguard','protectai')}
        for detector in filters.values(): detector.filter('Routine operational record. Reconcile the approved request.')
        print('Detectors ready; sequential timing started.', flush=True)
        with path.open('a', encoding='utf-8') as stream:
            for case, method in jobs:
                start = time.perf_counter()
                if method in baseline.METHODS: row = baseline.episode(case,method,client,filters)
                else: row = catalog.runner.episode(case,'full' if method=='full' else 'no_geometry',None,client,max_turns=12,max_tool_calls=32)
                row['wall_seconds'] = time.perf_counter()-start
                row['arm'] = method
                if row['termination'] in ('infrastructure_error','api_error','budget_exhausted'):
                    with (OUT/'attempts.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(row)+'\n')
                else:
                    if method in baseline.METHODS: baseline.audit(case,row)
                    else:
                        copied = deepcopy(row)
                        if method=='no_defense': copied['arm']='no_geometry'
                        baseline.dafr_replay(case,copied,None)
                    rows.append(row); stream.write(json.dumps(row)+'\n'); stream.flush()
                summarize(rows)
                print(json.dumps({'accepted':len(rows),'method':method,'id':case['id'],
                    'seconds':round(row['wall_seconds'],2),'termination':row['termination']}), flush=True)
                if client.fatal_error or row['termination']=='budget_exhausted': break
    catalog.dump(OUT/'audit.json',{'replayed_episodes':len(rows),'errors':0,'complete':len(rows)==60})
    print(json.dumps(summarize(rows)), flush=True)


if __name__=='__main__': main()
