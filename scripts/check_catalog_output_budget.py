"""Small common-budget check, selected by catalog order without outcome filtering."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import run_workflow_catalog_v2 as catalog
from resume_catalog_v2 import replay
from flash_catalog_client import CatalogClient

OUT = catalog.ROOT / 'results/summaries/workflow_catalog_output_budget_pilot'


class LongerOutput:
    def __init__(self, client):
        self.client = client

    def chat(self, messages, tools, max_tokens=650):
        return self.client.chat(messages, tools, max_tokens=1600)


def main():
    pairs, model = catalog.prepare()
    # First signed-snapshot pair in each of the first three distinct domains.
    # Every selected pair is evaluated under every arm and both conditions.
    seen, selected = set(), []
    for pair in pairs:
        c = pair[0]
        if c['lane'] == 'signed_snapshot' and c['domain'] not in seen:
            seen.add(c['domain'])
            selected.append(pair)
            if len(selected) == 3:
                break
    OUT.mkdir(parents=True, exist_ok=True)
    protocol = {'selection': 'First signed-snapshot pair in each of the first three distinct catalog domains; independent of observed outcome',
                'ids': [c['id'] for p in selected for c in p], 'arms': list(catalog.ARMS),
                'max_output_tokens': 1600, 'max_turns': 12, 'max_tool_calls': 32,
                'change': 'Only common model output budget, no data or defense change',
                'official_catalog_result': False}
    catalog.dump(OUT / 'protocol.json', protocol)
    key = sys.stdin.readline().strip()
    assert key
    client = LongerOutput(CatalogClient(key, OUT, 3.0))
    path = OUT / 'rows.jsonl'
    rows = [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
    done = {(r['id'], r['arm']) for r in rows}

    def run(case, arm):
        row = catalog.runner.episode(case, arm, model, client, max_turns=12, max_tool_calls=32)
        replay(case, row, model)
        return row

    with ThreadPoolExecutor(max_workers=3) as pool, path.open('a', encoding='utf-8') as stream:
        futures = [pool.submit(run, c, a) for p in selected for c in p for a in catalog.ARMS
                   if (c['id'], a) not in done]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            stream.write(json.dumps(row) + '\n')
            stream.flush()
            print(json.dumps({'episodes': len(rows), 'id': row['id'], 'arm': row['arm'],
                              'task_completed': row['task_completed'], 'termination': row['termination']}), flush=True)
    result = []
    valid = [r for r in rows if r['termination'] not in ('api_error', 'budget_exhausted')]
    for arm in catalog.ARMS:
        clean = [r for r in valid if r['arm'] == arm and r['variant'] == 'clean']
        attacked = [r for r in valid if r['arm'] == arm and r['variant'] == 'attack']
        result.append({'arm': arm, 'clean_n': len(clean), 'attack_n': len(attacked),
                       'clean_successes': sum(r['task_completed'] for r in clean),
                       'attack_successes_user': sum(r['task_completed'] for r in attacked),
                       'attacker_successes': sum(r['attack_success'] for r in attacked)})
    catalog.dump(OUT / 'summary.json', {'complete': len(valid) == 30, 'rows': result,
                                       'official_catalog_result': False})


if __name__ == '__main__':
    main()
