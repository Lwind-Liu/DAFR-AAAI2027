"""Full fixed-104 halfspace and joint-surface ablations with checkpointing."""
from concurrent.futures import ThreadPoolExecutor, as_completed, CancelledError
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import sys

import run_catalog_geometry_split_pilot as split

ROOT = split.ROOT
OUT = ROOT / 'results/summaries/catalog_geometry_split_104_v1'


def report(rows):
    result = [{'arm': arm, **split.comparison.metrics([r for r in rows if r['arm'] == arm])}
              for arm in split.ARMS if any(r['arm'] == arm for r in rows)]
    split.catalog.dump(OUT / 'summary.json', {'complete': len(rows) == 624,
        'accepted_episodes':len(rows), 'new_arms_accepted':sum(r['arm'] != 'full' for r in rows),
        'new_arms_expected':416, 'rows': result})
    split.comparison.write_csv(OUT / 'ablation.csv', result)


def main():
    split.catalog.configure_runner()
    split.catalog.runner.WorkflowWorld = split.catalog.CatalogWorld
    split.catalog.runner.admit = split.catalog.admit = split.split_admit
    source = ROOT / 'data/workflow_catalog_104/cases.jsonl'
    cases = [json.loads(line) for line in source.read_text().splitlines()]
    by_id = {c['id']:c for c in cases}
    assert len(cases) == 208 and len({c['group_id'] for c in cases}) == 104
    OUT.mkdir(parents=True, exist_ok=True)
    protocol = {'pairs':104, 'arms':list(split.ARMS), 'new_arm_episodes':416,
        'full_reference':'catalog_fixed104_adapter_v11_104',
        'model':'deepseek-v4-flash-0731','temperature':0,'max_turns':12,
        'max_tool_calls':32,'max_tokens':650,'workers':6,
        'data_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'guard_sha256':hashlib.sha256(Path(split.__file__).read_bytes()).hexdigest(),
        'no_halfspaces':'Remove semantic halfspaces; retain the unchanged joint-risk surface.',
        'no_joint_surface':'Remove joint-risk surface; retain the unchanged semantic halfspaces.',
        'shared':'Same full projection, lifting, tools, validation and repair feedback.',
        'reuse':'Full reference and completed identical-budget pilot episodes are replay-audited before reuse.'}
    path = OUT / 'protocol.json'
    if path.exists():
        assert json.loads(path.read_text()) == protocol
    else:
        split.catalog.dump(path, protocol)
    path = OUT / 'rows.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    done = {(r['id'],r['arm']) for r in rows}
    original,_,_ = split.comparison.read_complete(ROOT/'results/summaries/catalog_fixed104_adapter_v11_104')
    pilot_path = split.OUT / 'rows.jsonl'
    pilot = [json.loads(line) for line in pilot_path.read_text().splitlines()] if pilot_path.exists() else []
    with path.open('a',encoding='utf-8') as stream:
        for candidate in [r for r in original if r['arm']=='full'] + [r for r in pilot if r['arm']!='full']:
            key = (candidate['id'],candidate['arm'])
            if key in done:
                continue
            row = deepcopy(candidate)
            split.auditor.replay(by_id[row['id']],row,None)
            row['reused_from'] = 'catalog_fixed104_adapter_v11_104' if row['arm']=='full' else 'catalog_geometry_split_pilot_v1'
            rows.append(row)
            done.add(key)
            stream.write(json.dumps(row)+'\n')
        stream.flush()
        jobs = [(c,arm) for c in cases for arm in split.ARMS[1:] if (c['id'],arm) not in done]
        random.Random(2026101340).shuffle(jobs)
        report(rows)
        print(json.dumps({'accepted':len(rows),'new_arms_accepted':sum(r['arm']!='full' for r in rows),
                          'pending':len(jobs)}),flush=True)
        if jobs:
            key = sys.stdin.readline().strip()
            assert key
            client = split.CatalogClient(key,OUT,25.)
            with ThreadPoolExecutor(max_workers=6) as pool:
                futures = [pool.submit(split.execute,c,arm,client) for c,arm in jobs]
                for future in as_completed(futures):
                    try:
                        row = future.result()
                    except CancelledError:
                        continue
                    if row['termination'] in ('api_error','budget_exhausted'):
                        with (OUT/'attempts.log').open('a') as failed:
                            failed.write(json.dumps(row)+'\n')
                        if client.fatal_error or row['termination']=='budget_exhausted':
                            for pending in futures:
                                pending.cancel()
                    else:
                        rows.append(row)
                        stream.write(json.dumps(row)+'\n')
                        stream.flush()
                    report(rows)
                    print(json.dumps({'new_arms_accepted':sum(r['arm']!='full' for r in rows),
                                      'id':row['id'],'arm':row['arm'],
                                      'termination':row['termination']}),flush=True)
    assert len(rows)==len({(r['id'],r['arm']) for r in rows})
    for row in rows:
        split.auditor.replay(by_id[row['id']],row,None)
    split.catalog.dump(OUT/'audit.json',{'replayed_episodes':len(rows),'errors':0,'complete':len(rows)==624})
    report(rows)
    print((OUT/'summary.json').read_text(),flush=True)


if __name__=='__main__':
    main()
