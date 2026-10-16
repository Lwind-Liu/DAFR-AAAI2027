"""Fixed 24-task operational extension, using the frozen whole-region model."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import random
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
import run_flash_module_ablation as base
from relational_dafr.operational_failures import AgentWorld, build_cases
from relational_dafr.whole_region_ablation import guard

base.AgentWorld = AgentWorld
base.guard = guard
ARMS = ('full_surface', 'no_projection', 'no_lifting', 'linear_region', 'no_geometric_region')


def main():
    out = ROOT / 'results/summaries/flash_operational_extension_v1'
    data = ROOT / 'data/flash_operational_extension_v1'
    out.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    reference = ROOT / 'results/summaries/flash_whole_region_ablation_v3/frozen_protocol.json'
    old = json.loads(reference.read_text())
    model = dict(old['linear_model'])
    model['weights'] = np.array(model['weights'])
    cases = build_cases()
    original_ids = {json.loads(line)['id'] for line in
        (ROOT / 'data/flash_business_geometry_combined_v1/test.jsonl').read_text().splitlines()}
    assert not original_ids.intersection(c['id'] for c in cases)
    (data / 'test.jsonl').write_text(''.join(json.dumps(c) + '\n' for c in cases), encoding='utf-8')
    source = [Path(__file__), ROOT / 'src/relational_dafr/operational_failures.py',
        ROOT / 'src/relational_dafr/whole_region_ablation.py', ROOT / 'src/relational_dafr/module_ablation.py',
        ROOT / 'scripts/run_flash_module_ablation.py', ROOT / 'scripts/run_flash_business_geometry.py',
        ROOT / 'src/relational_dafr/agent_world.py', ROOT / 'src/relational_dafr/business_world.py',
        ROOT / 'src/relational_dafr/controller.py', ROOT / 'src/relational_dafr/worlds.py']
    protocol = {'cases': 24, 'planned_episodes': 120, 'seed': 20261026, 'arms': ARMS,
        'model': 'deepseek-flash', 'temperature': 0, 'thinking': 'disabled',
        'max_turns': 10, 'max_tokens': 650, 'verification_budget': 4,
        'system_prompt': base.SYSTEM, 'linear_model': old['linear_model'],
        'method_and_parameters': 'unchanged from whole-region v3',
        'scenario_assignment': 'four predefined availability scenarios, six tasks each; no risk or outcome filtering',
        'frozen_reference_sha256': hashlib.sha256(reference.read_bytes()).hexdigest(),
        'data_sha256': hashlib.sha256((data / 'test.jsonl').read_bytes()).hexdigest(),
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source}}
    protocol = json.loads(json.dumps(protocol))
    frozen = out / 'frozen_protocol.json'
    if frozen.exists():
        assert json.loads(frozen.read_text()) == protocol
    base.dump(frozen, protocol)
    rows_file = out / 'rows.jsonl'
    rows = list(map(json.loads, rows_file.read_text().splitlines())) if rows_file.exists() else []
    done = {(r['id'], r['arm']) for r in rows}
    client = base.CachedCostClient(2.2, out)
    jobs = [(c, a) for c in cases for a in ARMS if (c['id'], a) not in done]
    random.Random(20261026).shuffle(jobs)
    print(json.dumps({'event': 'started', 'tasks': 24, 'episodes': len(jobs), 'budget_cny': client.budget}), flush=True)
    with ThreadPoolExecutor(max_workers=8) as pool, rows_file.open('a', encoding='utf-8') as stream:
        futures = [pool.submit(base.episode, c, a, model, client, 10) for c, a in jobs]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            stream.write(json.dumps(row) + '\n')
            stream.flush()
            if len(rows) % 12 == 0:
                print(json.dumps({'completed': len(rows), 'conservative_cost_cny': round(client.spent_upper, 4)}), flush=True)
    summary = {}
    for arm in ARMS:
        part = [r for r in rows if r['arm'] == arm]
        summary[arm] = {'cases': len(part), 'safe_successes': sum(r['safe_success'] for r in part),
            'unsafe_commits': sum(r['unsafe_commit'] for r in part),
            'verification_queries': sum(r['verification_queries'] for r in part),
            'termination_counts': {t: sum(r['termination'] == t for r in part) for t in sorted({r['termination'] for r in part})}}
    base.dump(out / 'summary.json', {'arms': summary})
    base.dump(out / 'usage.json', {**client.usage, 'conservative_cost_cny': client.spent_upper,
        'budget_cny': client.budget, 'balance_after': client.balance()})
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
