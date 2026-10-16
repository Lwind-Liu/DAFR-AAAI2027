"""Resumable complete 104-pair comparison, with live pilot rows reused."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import run_catalog_other_methods as baseline
from flash_catalog_client import CatalogClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--budget-cny', type=float, default=25.)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--report-only', action='store_true')
    parser.add_argument('--methods', nargs='+', choices=baseline.METHODS, default=["progent", "drift"])
    args = parser.parse_args()
    catalog = baseline.catalog
    pairs, model = catalog.prepare()
    pairs += baseline.added_pairs(pairs)
    cases = {c['id']: c for p in pairs for c in p}
    output = baseline.ROOT / 'results/summaries/catalog_policy_baseline_matrix_104'
    output.mkdir(parents=True, exist_ok=True)
    paths = [Path(__file__), Path(baseline.__file__), Path(baseline.reference.__file__),
        *baseline.reference.VENDOR.glob('progent_defense/secagent/*.py'),
        *baseline.reference.VENDOR.glob('drift_defense/*.py'),
        *baseline.reference.VENDOR.glob('filter_defenses/*defense.py')]
    protocol = {'pairs':104, 'episodes':1248, 'methods':['no_defense',*baseline.METHODS,'full'],
        'model':'deepseek-v4-flash-0731', 'planner_tokens':650, 'defense_tokens':2048,
        'max_turns':12, 'max_tool_calls':32,
        'data_sha256':hashlib.sha256((baseline.ROOT/'data/workflow_catalog_104/cases.jsonl').read_bytes()).hexdigest(),
        'detectors':baseline.reference.DETECTORS,
        'adapter_scope':'Original main-table implementations; workflow tool schemas, external-note filtering, concrete draft argument policy checks. No DAFR risk admission in baselines.',
        'source_sha256':{str(p.relative_to(baseline.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    protocol = json.loads(json.dumps(protocol))
    frozen = output/'protocol.json'
    if frozen.exists(): assert json.loads(frozen.read_text()) == protocol
    catalog.dump(frozen,protocol)
    if args.prepare_only:
        print(json.dumps({'pairs':104,'total_episodes':1248,'new_baseline_episodes':832})); return
    path = output/'rows.jsonl'
    rows = [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
    done = {(r['id'],r['arm']) for r in rows}
    originals = catalog.read_rows() + [json.loads(s) for p in (baseline.ROOT/'results/summaries/workflow_catalog_104').glob('CAT-*.jsonl') for s in p.read_text().splitlines()]
    pilot = baseline.ROOT/'results/summaries/catalog_other_methods_pilot/rows.jsonl'
    if pilot.exists(): originals += [json.loads(s) for s in pilot.read_text().splitlines()]
    with path.open('a',encoding='utf-8') as stream:
        for row in originals:
            if row['id'] not in cases or row['arm'] not in ('full','no_geometry',*baseline.METHODS): continue
            if row['termination'] in ('infrastructure_error','api_error','budget_exhausted'): continue
            row = deepcopy(row)
            if row['arm'] in ('full','no_geometry'):
                baseline.dafr_replay(cases[row['id']],row,model)
                row['reused_from']='workflow_catalog_104'
                if row['arm']=='no_geometry': row['arm']='no_defense'
            else:
                baseline.audit(cases[row['id']],row)
                row['reused_from']='catalog_other_methods_pilot'
            if (row['id'],row['arm']) in done: continue
            rows.append(row); done.add((row['id'],row['arm'])); stream.write(json.dumps(row)+'\n')
    if not args.report_only:
        key = sys.stdin.readline().strip(); assert key
        client = CatalogClient(key,output,args.budget_cny)
        filters = {m:baseline.reference.FilterAdapter(m) for m in args.methods if m in ('piguard','protectai')}
        jobs = [(c,m) for m in args.methods for c in cases.values() if (c['id'],m) not in done]
        print(json.dumps({'remaining_episodes':len(jobs)}),flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as pool, path.open('a',encoding='utf-8') as stream:
            futures = [pool.submit(baseline.episode,c,m,client,filters) for c,m in jobs]
            for future in as_completed(futures):
                row=future.result(); baseline.audit(cases[row['id']],row)
                if row['termination'] in ('infrastructure_error','api_error','budget_exhausted'):
                    with (output/'attempts.log').open('a',encoding='utf-8') as failed:
                        failed.write(json.dumps(row)+'\n')
                else:
                    rows.append(row); stream.write(json.dumps(row)+'\n'); stream.flush()
                if len(rows)%10==0:
                    print(json.dumps({'episodes':len(rows),'last_method':row['arm']}),flush=True)
                    baseline.summarize(rows,list(cases.values()),output,baseline.METHODS)
    for row in rows:
        if row['arm'] in baseline.METHODS: baseline.audit(cases[row['id']],row)
        else:
            copied=deepcopy(row)
            if copied['arm']=='no_defense': copied['arm']='no_geometry'
            baseline.dafr_replay(cases[row['id']],copied,model)
    assert len({(r['id'],r['arm']) for r in rows})==len(rows)
    catalog.dump(output/'audit.json',{'replayed_episodes':len(rows),'errors':0,'complete':len(rows)==1248})
    print(json.dumps(baseline.summarize(rows,list(cases.values()),output,baseline.METHODS)),flush=True)


if __name__=='__main__': main()

