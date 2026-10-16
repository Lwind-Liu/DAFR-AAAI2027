"""Join the four independently completed baseline arms on the same 196 tasks."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from run_flash_other_methods import summarize, dump
from audit_flash_other_methods import audit


def main():
    sources = [('flash_other_methods_v2', ('no_defense', 'full', 'progent', 'drift')),
               ('flash_other_methods_v3', ('piguard', 'protectai'))]
    output = ROOT / 'results/summaries/flash_other_methods_final_v1'
    output.mkdir(parents=True, exist_ok=True)
    rows, protocols, usage = [], {}, []
    shared = ('cases', 'dataset_sha256', 'model', 'temperature', 'thinking',
              'max_planner_tokens', 'max_defense_tokens', 'max_turns', 'verification_budget', 'system_prompt')
    reference = None
    for name, methods in sources:
        folder = ROOT / 'results/summaries' / name
        protocol = json.loads((folder / 'frozen_protocol.json').read_text(encoding='utf-8'))
        settings = {k: protocol[k] for k in shared}
        if reference is None:
            reference = settings
        assert settings == reference, 'Common environment or model differs'
        runner_hash = next(v for k, v in protocol['source_sha256'].items()
                           if k.replace('\\', '/') == 'scripts/run_flash_other_methods.py')
        assert hashlib.sha256((folder / 'runner_snapshot.py').read_bytes()).hexdigest() == runner_hash
        protocols[name] = protocol
        usage.append(json.loads((folder / 'usage.json').read_text(encoding='utf-8')))
        for line in (folder / 'rows.jsonl').read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            if row['arm'] in methods:
                row['evaluation_source'] = name
                rows.append(row)
    data = ROOT / 'data/flash_business_geometry_final_v4/test.jsonl'
    assert hashlib.sha256(data.read_bytes()).hexdigest() == reference['dataset_sha256']
    cases = {c['id']: c for c in (json.loads(s) for s in data.read_text(encoding='utf-8').splitlines())}
    reference_audit = json.loads((ROOT / 'results/summaries/flash_business_geometry_final_v4/integrity_audit.json').read_text(encoding='utf-8'))
    assert not reference_audit['errors'], 'Reused reference results failed their original replay audit'
    reference_rows = {(r['id'], r['arm']): r for r in (json.loads(s) for s in
        (ROOT / 'results/summaries/flash_business_geometry_final_v4/rows.jsonl').read_text(encoding='utf-8').splitlines())}
    for row in rows:
        if row['arm'] in ('full', 'no_defense'):
            origin = 'full_surface' if row['arm'] == 'full' else 'no_geometric_region'
            expected = reference_rows[(row['id'], origin)]
            assert {k: row[k] for k in expected if k != 'arm'} == {k: v for k, v in expected.items() if k != 'arm'}
    for arm in ('no_defense', 'piguard', 'protectai', 'progent', 'drift', 'full'):
        assert {r['id'] for r in rows if r['arm'] == arm} == set(cases), f'Incomplete {arm}'
    assert len(rows) == 1176
    audit_result = audit(rows, cases)
    assert audit_result['error_count'] == 0, audit_result
    dump(output / 'integrity_audit.json', audit_result)
    dump(output / 'frozen_protocol.json', {'shared': reference, 'source_protocols': protocols,
        'assembly': sources, 'all_tasks_retained': True, 'new_baseline_episodes': 784,
        'reused_reference_episodes': 392})
    (output / 'rows.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
    results = summarize(rows, output)
    dump(output / 'usage.json', {'new_baselines_conservative_cost_cny': sum(u['conservative_cost_cny'] for u in usage),
                               'source_usage': usage})
    names = {'no_defense': 'No Defense', 'piguard': 'PIGuard', 'protectai': 'ProtectAI',
             'progent': 'Progent', 'drift': 'DRIFT', 'full': 'DAFR'}
    text = ['196 fixed tasks; six domains; DeepSeek Flash.',
            'Method | Safe task success | Unsafe executions']
    for method, s in results.items():
        text.append(f"{names[method]} | {s['safe_success_pct']:.1f}% | {s['unsafe_executions']}")
    (output / 'results.txt').write_text('\n'.join(text) + '\n', encoding='utf-8')
    print(json.dumps(results), flush=True)


if __name__ == '__main__':
    main()
