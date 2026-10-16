"""Outcome-independent stratified 20-pair check of all main-table methods."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import sys
import catalog_baseline_adapter_v8 as baseline
from flash_catalog_client import CatalogClient

ROOT = baseline.ROOT
OUT = ROOT / 'results/summaries/catalog_fixed104_adapter_v8_20'
MIX = {'signed_snapshot':12, 'cache_approval_mismatch':2, 'joint_risk':2,
       'scope_conflict':1, 'low_exposure':1, 'retry_recovery':2}


def select_pairs(pairs):
    rng = random.Random(2026101320)
    selected = []
    for lane, count in MIX.items():
        candidates = [p for p in pairs if p[0]['lane']==lane]
        selected += rng.sample(candidates,count)
    rng.shuffle(selected)
    assert len(selected)==20
    assert len({p[0]['domain'] for p in selected})==6
    return selected


def read_valid(path):
    if not path.exists(): return []
    lines = path.read_text(encoding='utf-8').splitlines()
    result=[]
    for i,line in enumerate(lines):
        try: result.append(json.loads(line))
        except json.JSONDecodeError:
            # A forcibly stopped old batch can leave its final write partial.
            # Preserve that source; do not treat an incomplete trace as a run.
            if i != len(lines)-1: raise
    return result


def audit(case,row,model):
    if row['arm'] in baseline.METHODS: baseline.audit(case,row)
    else:
        copied=deepcopy(row)
        if copied['arm']=='no_defense':copied['arm']='no_geometry'
        baseline.dafr_replay(case,copied,model)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--report-only',action='store_true')
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--budget-cny',type=float,default=8.)
    args=parser.parse_args()
    pairs,model=baseline.catalog.prepare()
    pairs+=baseline.added_pairs(pairs)
    pairs=select_pairs(pairs)
    cases={c['id']:c for p in pairs for c in p}
    OUT.mkdir(parents=True,exist_ok=True)
    protocol={'pairs':20,'episodes':240,'seed':2026101320,'selection':'Stratified random sampling of fixed 104 pairs without reading execution outcomes',
        'mix':MIX,'domains':dict(Counter(p[0]['domain'] for p in pairs)),
        'ids':list(cases),'methods':['no_defense',*baseline.METHODS,'full'],
        'data_sha256':hashlib.sha256((ROOT/'data/workflow_catalog_104/cases.jsonl').read_bytes()).hexdigest(),
        'adapter_sha256':hashlib.sha256(Path(baseline.__file__).read_bytes()).hexdigest(),
        'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'model':'deepseek-v4-flash-0731','max_turns':12,'max_tool_calls':32,
        'planner_tokens':650,'defense_tokens':2048}
    frozen=OUT/'protocol.json'
    if frozen.exists(): assert json.loads(frozen.read_text())==protocol
    baseline.catalog.dump(frozen,protocol)
    if args.prepare_only:
        print(json.dumps(protocol));return
    path=OUT/'rows.jsonl'
    rows=read_valid(path)
    done={(r['id'],r['arm']) for r in rows}
    sources=[ROOT/'results/summaries'/name/'rows.jsonl' for name in (
        'catalog_fixed104_adapter_v5_20','catalog_fixed104_adapter_v4_pilot','catalog_other_methods_pilot','catalog_baseline_matrix_104','catalog_policy_baseline_matrix_104')]
    original=baseline.catalog.read_rows()+[r for p in (ROOT/'results/summaries/workflow_catalog_104').glob('CAT-*.jsonl') for r in read_valid(p)]
    entries=[(None,r) for r in original]+[(p,r) for p in sources for r in read_valid(p)]
    with path.open('a',encoding='utf-8') as stream:
        for source,row in entries:
            if row['arm'] in ('piguard','protectai'): continue
            if row['arm']=='drift': continue
            if row['arm']=='progent' and (source is None or source.parent.name not in ('catalog_fixed104_adapter_v5_20','catalog_fixed104_adapter_v4_pilot')): continue
            if row['id'] not in cases or row['arm'] not in ('full','no_geometry','no_defense',*baseline.METHODS):continue
            if row['termination'] in ('infrastructure_error','api_error','budget_exhausted'):continue
            row=deepcopy(row)
            if row['arm']=='no_geometry':row['arm']='no_defense'
            key=(row['id'],row['arm'])
            if key in done:continue
            audit(cases[row['id']],row,model)
            row['reused_from']=str(source.relative_to(ROOT)) if source else 'workflow_catalog_104'
            rows.append(row);done.add(key);stream.write(json.dumps(row)+'\n')
    jobs=[(c,m) for m in baseline.METHODS for c in cases.values() if (c['id'],m) not in done]
    print(json.dumps({'selected_pairs':20,'reused_episodes':len(rows),'remaining_episodes':len(jobs)}),flush=True)
    if not args.report_only and jobs:
        key=sys.stdin.readline().strip();assert key
        client=CatalogClient(key,OUT,args.budget_cny)
        filters={m:baseline.reference.FilterAdapter(m) for m in ('piguard','protectai') if any(j[1]==m for j in jobs)}
        with ThreadPoolExecutor(max_workers=args.workers) as pool,path.open('a',encoding='utf-8') as stream:
            futures=[pool.submit(baseline.episode,c,m,client,filters) for c,m in jobs]
            for future in as_completed(futures):
                row=future.result();audit(cases[row['id']],row,model)
                if row['termination'] in ('infrastructure_error','api_error','budget_exhausted'):
                    with (OUT/'attempts.log').open('a',encoding='utf-8') as failed:failed.write(json.dumps(row)+'\n')
                else:
                    rows.append(row);stream.write(json.dumps(row)+'\n');stream.flush()
                if len(rows)%5==0:
                    print(json.dumps({'episodes':len(rows),'method':row['arm'],'termination':row['termination']}),flush=True)
                    baseline.summarize(rows,list(cases.values()),OUT,baseline.METHODS)
    for row in rows:audit(cases[row['id']],row,model)
    assert len({(r['id'],r['arm']) for r in rows})==len(rows)
    baseline.catalog.dump(OUT/'audit.json',{'replayed_episodes':len(rows),'errors':0,'complete':len(rows)==240})
    print(json.dumps(baseline.summarize(rows,list(cases.values()),OUT,baseline.METHODS)),flush=True)


if __name__=='__main__':main()
