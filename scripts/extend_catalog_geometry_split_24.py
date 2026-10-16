"""Expand the eight-pair split pilot to 24 pairs sampled from the fixed 104."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import sys

import run_catalog_geometry_split_pilot as split

ROOT = split.ROOT
OUT = ROOT / 'results/summaries/catalog_geometry_split_24_v1'


def report(rows):
    result = [{'arm':arm, **split.comparison.metrics([r for r in rows if r['arm']==arm])}
              for arm in split.ARMS if any(r['arm']==arm for r in rows)]
    split.catalog.dump(OUT/'summary.json', {'complete':len(rows)==144,
        'pairs':24,'accepted_episodes':len(rows),'rows':result})
    split.comparison.write_csv(OUT/'ablation.csv',result)


def main():
    split.catalog.configure_runner()
    split.catalog.runner.WorkflowWorld = split.catalog.CatalogWorld
    split.catalog.runner.admit = split.catalog.admit = split.split_admit
    data = ROOT/'data/workflow_catalog_104/cases.jsonl'
    all_cases = [json.loads(line) for line in data.read_text().splitlines()]
    pilot = [json.loads(line) for line in (split.OUT/'rows.jsonl').read_text().splitlines()]
    prior_groups = {r['group_id'] for r in pilot}
    assert len(prior_groups)==8 and len(pilot)==48
    candidates = sorted({c['group_id'] for c in all_cases}-prior_groups)
    random.Random(2026101341).shuffle(candidates)
    groups = prior_groups | set(candidates[:16])
    cases = [c for c in all_cases if c['group_id'] in groups]
    assert len(cases)==48
    by_id = {c['id']:c for c in cases}
    OUT.mkdir(parents=True,exist_ok=True)
    protocol = {'pairs':24,'prior_pairs':8,'additional_pairs':16,'new_executions':64,
        'selection':'Keep all eight original pairs; uniformly shuffle remaining group IDs with seed 2026101341 and take 16, without outcome filtering.',
        'arms':list(split.ARMS),'ids':[c['id'] for c in cases],
        'data_sha256':hashlib.sha256(data.read_bytes()).hexdigest(),
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'guard_sha256':hashlib.sha256(Path(split.__file__).read_bytes()).hexdigest(),
        'model':'deepseek-v4-flash-0731','temperature':0,'max_turns':12,
        'max_tool_calls':32,'max_tokens':650,'reuse':'Existing matched full reference and all original pilot episodes; replayed.'}
    path = OUT/'protocol.json'
    if path.exists():
        assert json.loads(path.read_text())==protocol
    else:
        split.catalog.dump(path,protocol)
    (OUT/'cases.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in cases),encoding='utf-8')
    path = OUT/'rows.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    done = {(r['id'],r['arm']) for r in rows}
    original,_,_ = split.comparison.read_complete(ROOT/'results/summaries/catalog_fixed104_adapter_v11_104')
    with path.open('a',encoding='utf-8') as stream:
        for candidate in pilot+[r for r in original if r['arm']=='full' and r['id'] in by_id]:
            if (candidate['id'],candidate['arm']) in done:
                continue
            row = deepcopy(candidate)
            split.auditor.replay(by_id[row['id']],row,None)
            rows.append(row)
            done.add((row['id'],row['arm']))
            stream.write(json.dumps(row)+'\n')
        stream.flush()
        jobs = [(c,arm) for c in cases for arm in split.ARMS[1:] if (c['id'],arm) not in done]
        report(rows)
        print(json.dumps({'pairs':24,'reused':len(rows),'pending':len(jobs)}),flush=True)
        if jobs:
            key = sys.stdin.readline().strip()
            assert key
            client = split.CatalogClient(key,OUT,6.)
            with ThreadPoolExecutor(max_workers=6) as pool:
                for future in as_completed([pool.submit(split.execute,c,arm,client) for c,arm in jobs]):
                    row = future.result()
                    if row['termination'] in ('api_error','budget_exhausted'):
                        with (OUT/'attempts.log').open('a') as failed:
                            failed.write(json.dumps(row)+'\n')
                    else:
                        rows.append(row)
                        stream.write(json.dumps(row)+'\n')
                        stream.flush()
                    report(rows)
                    print(json.dumps({'accepted':len(rows),'id':row['id'],'arm':row['arm'],
                                      'termination':row['termination']}),flush=True)
    assert len(rows)==len({(r['id'],r['arm']) for r in rows})
    for row in rows:
        split.auditor.replay(by_id[row['id']],row,None)
    split.catalog.dump(OUT/'audit.json',{'replayed_episodes':len(rows),'errors':0,'complete':len(rows)==144})
    report(rows)
    print((OUT/'summary.json').read_text(),flush=True)


if __name__=='__main__':
    main()
