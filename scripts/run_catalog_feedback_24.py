"""Ablate the decision/revision feedback branch on the fixed 24-pair pilot."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import run_workflow_catalog_v2 as catalog
import resume_catalog_v2 as auditor
import export_catalog_baseline_comparison as comparison
from workflow_benchmark.repair_feedback import admit_with_facts
from flash_catalog_client import CatalogClient

ROOT = catalog.ROOT
OUT = ROOT / 'results/summaries/catalog_feedback_24_v1'


def admission(view, arm, model=None):
    if arm not in ('full', 'no_feedback'):
        raise ValueError(arm)
    allowed, detail = admit_with_facts(view, 'full')
    if arm == 'full' or allowed:
        return allowed, detail
    # Retain the exact feasible-region decision and the possibility of retry.
    # Remove the branch's revision targets, record IDs and authenticated facts.
    return False, {'status': 'blocked', 'reason': 'infeasible_operation'}


def report(rows):
    result = [{'arm':arm, **comparison.metrics([r for r in rows if r['arm']==arm])}
              for arm in ('full','no_feedback') if any(r['arm']==arm for r in rows)]
    catalog.dump(OUT/'summary.json', {'complete':len(rows)==96, 'pairs':24,
        'accepted_episodes':len(rows), 'rows':result})
    comparison.write_csv(OUT/'ablation.csv',result)


def episode(case, client):
    row = catalog.runner.episode(case,'no_feedback',None,client,max_turns=12,max_tool_calls=32)
    if row['termination'] not in ('api_error','budget_exhausted'):
        auditor.replay(case,row,None)
    return row


def main():
    catalog.configure_runner()
    catalog.runner.WorkflowWorld = catalog.CatalogWorld
    catalog.runner.admit = catalog.admit = admission
    parent = ROOT/'results/summaries/catalog_geometry_split_24_v1'
    cases = [json.loads(line) for line in (parent/'cases.jsonl').read_text().splitlines()]
    assert len(cases)==48 and len({c['group_id'] for c in cases})==24
    by_id = {c['id']:c for c in cases}
    OUT.mkdir(parents=True,exist_ok=True)
    protocol = {'pairs':24,'arms':['full','no_feedback'],'new_executions':48,
        'case_source':str(parent.relative_to(ROOT)), 'ids':[c['id'] for c in cases],
        'selection':'Identical 24 pairs used in the preceding split experiment; no outcome filtering.',
        'model':'deepseek-v4-flash-0731','temperature':0,'max_turns':12,
        'max_tool_calls':32,'max_tokens':650,
        'case_sha256':hashlib.sha256((parent/'cases.jsonl').read_bytes()).hexdigest(),
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'paper_definition':'Feasibility Decision and Targeted Feedback, paper/main/DAFR_AAAI2027_Main_Current.tex.',
        'ablation':'Keep the feasible-region membership decision; convert revision feedback into generic rejection without repair targets, suggested records or supplied facts.',
        'preserved':'Full projection, lifting, halfspaces, joint risk, tool schemas, verification service, retry ability and all non-defense tool responses.',
        'reference':'Existing full DAFR traces on identical tasks and budgets, replay audited.'}
    path = OUT/'protocol.json'
    if path.exists():
        assert json.loads(path.read_text())==protocol
    else:
        catalog.dump(path,protocol)
    # Audit independence of the new branch on all initial task views.
    for case in cases:
        world = catalog.CatalogWorld(case)
        world.call('read_request',{'request_id':case['request_id']})
        view = world.observer_view('OP-1')
        assert admission(view,'full')[0] == admission(view,'no_feedback')[0]
    path = OUT/'rows.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    done = {(r['id'],r['arm']) for r in rows}
    originals = [json.loads(line) for line in (parent/'rows.jsonl').read_text().splitlines()]
    with path.open('a',encoding='utf-8') as stream:
        for original in originals:
            if original['arm']!='full' or (original['id'],'full') in done:
                continue
            row = deepcopy(original)
            auditor.replay(by_id[row['id']],row,None)
            rows.append(row)
            done.add((row['id'],'full'))
            stream.write(json.dumps(row)+'\n')
        stream.flush()
        report(rows)
        jobs = [c for c in cases if (c['id'],'no_feedback') not in done]
        print(json.dumps({'pairs':24,'reused':len(rows),'pending':len(jobs)}),flush=True)
        if jobs:
            key = sys.stdin.readline().strip()
            assert key
            client = CatalogClient(key,OUT,4.)
            with ThreadPoolExecutor(max_workers=6) as pool:
                for future in as_completed([pool.submit(episode,c,client) for c in jobs]):
                    row = future.result()
                    if row['termination'] in ('api_error','budget_exhausted'):
                        with (OUT/'attempts.log').open('a') as failed:
                            failed.write(json.dumps(row)+'\n')
                    else:
                        rows.append(row)
                        stream.write(json.dumps(row)+'\n')
                        stream.flush()
                    report(rows)
                    print(json.dumps({'accepted':len(rows),'id':row['id'],
                        'completed':row['task_completed'],'termination':row['termination']}),flush=True)
    assert len(rows)==len({(r['id'],r['arm']) for r in rows})
    for row in rows:
        auditor.replay(by_id[row['id']],row,None)
    catalog.dump(OUT/'audit.json',{'replayed_episodes':len(rows),'errors':0,
        'initial_decisions_equal':True,'complete':len(rows)==96})
    report(rows)
    print((OUT/'summary.json').read_text(),flush=True)


if __name__=='__main__':
    main()
