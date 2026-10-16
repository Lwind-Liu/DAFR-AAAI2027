"""Pool the two disjoint random five-task timing batches with equal weights."""
import csv
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/summaries/catalog_latency_random10'
METHODS = [('no_defense','No Defense'),('piguard','PIGuard'),('protectai','ProtectAI'),
           ('progent','Progent'),('drift','DRIFT'),('full','DAFR')]


def main():
    batches, protocols, sources = [], [], []
    for name in ('catalog_latency_random5_v1', 'catalog_latency_random5_v2'):
        folder = ROOT/'results/summaries'/name
        protocol = json.loads((folder/'protocol.json').read_text())
        audit = json.loads((folder/'audit.json').read_text())
        assert audit['complete'] and audit['errors'] == 0 and audit['replayed_episodes'] == 60
        records = [json.loads(line) for line in (folder/'rows.jsonl').read_text().splitlines()]
        assert len(records) == len({(r['id'],r['arm']) for r in records}) == 60
        assert {(r['id'],r['arm']) for r in records} == {(cid,m) for cid in protocol['ids'] for m,_ in METHODS}
        assert not any(r['termination'] in ('infrastructure_error','api_error','budget_exhausted') for r in records)
        assert all(r['wall_seconds'] > 0 for r in records)
        batches.append(records); protocols.append(protocol)
        sources.append({'path':str(folder.relative_to(ROOT)),
                        'rows_sha256':hashlib.sha256((folder/'rows.jsonl').read_bytes()).hexdigest()})
    assert not set(protocols[0]['ids']) & set(protocols[1]['ids'])
    for key in ('data_sha256','adapter_sha256','model','temperature','max_turns',
                'max_tool_calls','planner_tokens','defense_tokens','concurrency','timing'):
        assert protocols[0][key] == protocols[1][key], key
    rows = batches[0] + batches[1]
    result = []
    for method,label in METHODS:
        selected = [r for r in rows if r['arm'] == method]
        clean = [r['wall_seconds'] for r in selected if r['variant'] == 'clean']
        attack = [r['wall_seconds'] for r in selected if r['variant'] == 'attack']
        assert len(clean) == len(attack) == 10
        times = clean+attack
        result.append({'Method':label,'Episodes':len(times),
            'Batch 1 seconds':statistics.mean(r['wall_seconds'] for r in batches[0] if r['arm']==method),
            'Batch 2 seconds':statistics.mean(r['wall_seconds'] for r in batches[1] if r['arm']==method),
            'Clean seconds':statistics.mean(clean),'Attack seconds':statistics.mean(attack),
            'Mean seconds':statistics.mean(times),'Std seconds':statistics.stdev(times),
            'Median seconds':statistics.median(times)})
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'latency.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=list(result[0]));writer.writeheader();writer.writerows(result)
    (OUT/'summary.json').write_text(json.dumps({'complete':True,'task_pairs':10,
        'episodes':120,'timing':protocols[0]['timing'],'sources':sources,'rows':result},indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__': main()
