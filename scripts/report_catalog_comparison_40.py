"""Pool two disjoint, fixed-protocol 20-pair comparisons from raw traces."""
import hashlib
import json
from collections import Counter
import run_catalog_other_methods as baseline
from run_catalog_20_comparison import read_valid, audit

ROOT = baseline.ROOT
OUT = ROOT / 'results/summaries/catalog_method_comparison_40'


def main():
    folders = [ROOT / 'results/summaries' / name for name in
               ('catalog_method_comparison_20', 'catalog_method_comparison_20_batch2')]
    protocols = [json.loads((p/'protocol.json').read_text()) for p in folders]
    for field in ('methods', 'data_sha256', 'adapter_sha256', 'model', 'max_turns',
                  'max_tool_calls', 'planner_tokens', 'defense_tokens'):
        assert protocols[0][field] == protocols[1][field], field
    assert not set(protocols[0]['ids']) & set(protocols[1]['ids'])
    ids = set(protocols[0]['ids']) | set(protocols[1]['ids'])
    assert len(ids) == 80
    pairs, model = baseline.catalog.prepare()
    pairs += baseline.added_pairs(pairs)
    cases = {c['id']: c for p in pairs for c in p if c['id'] in ids}
    rows = [r for p in folders for r in read_valid(p/'rows.jsonl')]
    assert len(rows) == 480
    assert len({(r['id'], r['arm']) for r in rows}) == 480
    assert Counter((r['arm'], r['variant']) for r in rows) == Counter(
        {(m, v): 40 for m in protocols[0]['methods'] for v in ('clean', 'attack')})
    for row in rows:
        assert row['termination'] not in ('infrastructure_error', 'api_error', 'budget_exhausted')
        audit(cases[row['id']], row, model)
    OUT.mkdir(parents=True, exist_ok=True)
    baseline.catalog.dump(OUT/'protocol.json', {
        'pairs': 40, 'episodes': 480, 'ids': sorted(ids),
        'batch_protocols': [{'path': str((p/'protocol.json').relative_to(ROOT)),
                             'sha256': hashlib.sha256((p/'protocol.json').read_bytes()).hexdigest()}
                            for p in folders],
        'aggregation': 'Pool raw completed-task and attacker-goal counts; no outcome-based selection'})
    (OUT/'rows.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows), encoding='utf-8')
    baseline.catalog.dump(OUT/'audit.json', {'replayed_episodes': 480, 'errors': 0, 'complete': True})
    print(json.dumps(baseline.summarize(rows, list(cases.values()), OUT, baseline.METHODS)))


if __name__ == '__main__':
    main()
