"""Summarize successful model token usage from the accepted fixed-104 traces."""
import json
from pathlib import Path
import export_catalog_baseline_comparison as comparison

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/summaries/catalog_inference_cost_v1'


def main():
    source = ROOT / 'results/summaries/catalog_fixed104_adapter_v11_104'
    rows, _, _ = comparison.read_complete(source)
    OUT.mkdir(parents=True, exist_ok=True)
    result = []
    episodes = []
    for row in rows:
        # DRIFT's planner calls are recorded in defense_calls; its outer trace
        # has usage=None. Progent records planner and policy calls separately.
        usages = [t['usage'] for t in row['trace'] if isinstance(t.get('usage'), dict)]
        usages += [t['usage'] for t in row.get('defense_calls', []) if isinstance(t.get('usage'), dict)]
        assert len(usages) == row['llm_calls'], (row['id'], row['arm'])
        assert all('prompt_tokens' in u and 'completion_tokens' in u for u in usages)
        episodes.append({'id': row['id'], 'method': row['arm'], 'variant': row['variant'],
            'input_tokens': sum(u['prompt_tokens'] for u in usages),
            'output_tokens': sum(u['completion_tokens'] for u in usages),
            'llm_calls': len(usages), 'tool_calls': row['tool_calls'],
            'elapsed_seconds': row.get('elapsed_seconds')})
    for method, label in comparison.METHODS:
        subset = [r for r in episodes if r['method'] == method]
        assert len(subset) == 208
        result.append({'Method': label, 'Episodes': len(subset),
            **{'Mean ' + key: round(sum(r[key] for r in subset) / len(subset), 2)
               for key in ('input_tokens', 'output_tokens', 'llm_calls', 'tool_calls')},
            'Elapsed records available': sum(r['elapsed_seconds'] is not None for r in subset)})
    comparison.write_csv(OUT / 'inference_cost.csv', result)
    comparison.write_csv(OUT / 'episode_usage.csv', episodes)
    (OUT / 'protocol.json').write_text(json.dumps({'episodes': 1248,
        'unit': 'One clean or attacked episode; 208 episodes per method.',
        'token_scope': 'All recorded successful LLM calls, including policy generation and validation; local detector compute is not token usage.',
        'latency': 'No cross-method latency comparison: baseline rows do not store elapsed time and runs used different concurrency.',
        'failed_api_requests': 'Excluded; this is accepted-execution inference usage, not billing.'}, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
