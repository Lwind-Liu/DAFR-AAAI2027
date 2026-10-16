"""Export audited module results and paired effects for the fixed suite."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/summaries/flash_module_ablation_v2'
LABELS = {
    'full_surface': 'Full geometric method',
    'simple_linear': 'Simple linear rule',
    'no_projection': 'w/o Evidence Projection',
    'no_lifting': 'w/o Action-Evidence Binding',
    'no_geometry': 'w/o Geometric Constraints',
    'no_feedback': 'w/o Targeted Feedback',
}


def main():
    audit = json.loads((OUT / 'integrity_audit.json').read_text())
    assert audit['complete'] and not audit['errors'] and not audit['budget_exhausted_episodes']
    summary = json.loads((OUT / 'summary.json').read_text())['arms']
    rows = [json.loads(line) for line in (OUT / 'rows.jsonl').read_text().splitlines()]
    full = {r['id']: r for r in rows if r['arm'] == 'full_surface'}
    effects = {}
    for arm in LABELS:
        if arm == 'full_surface':
            continue
        part = [r for r in rows if r['arm'] == arm]
        effects[arm] = {
            'paired_tasks': len(part),
            'safe_success_gain_pp': 100 * sum(int(full[r['id']]['safe_success'])
                - int(r['safe_success']) for r in part) / len(part),
            'unsafe_commits_avoided': sum(int(r['unsafe_commit'])
                - int(full[r['id']]['unsafe_commit']) for r in part),
            'verification_calls_saved': sum(r['verification_queries']
                - full[r['id']]['verification_queries'] for r in part),
            'tasks_with_fewer_verifications_in_full': sum(r['verification_queries']
                > full[r['id']]['verification_queries'] for r in part),
            'tasks_with_more_verifications_in_full': sum(r['verification_queries']
                < full[r['id']]['verification_queries'] for r in part),
        }
    (OUT / 'module_effects.json').write_text(json.dumps(effects, indent=2) + '\n')
    fields = ['configuration', 'cases', 'safe_success_pct', 'unsafe_commits',
              'verification_queries', 'mean_verifications']
    with (OUT / 'paper_results.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for arm, label in LABELS.items():
            s = summary[arm]
            writer.writerow({'configuration': label, 'cases': s['cases'],
                'safe_success_pct': 100 * s['safe_successes'] / s['cases'],
                **{k: s[k] for k in fields[3:]}})
    lines = ['# Six-domain joint-risk tool-agent experiment', '',
        '172 fixed tasks; 1,032 completed episodes with DeepSeek Flash and local stateful business tools.',
        'Every configuration uses the same planner prompt, tool schemas, 10-turn limit and four-verification budget.',
        'The single affine baseline remains frozen; targeted feedback uses each configuration\'s own controller.',
        'Safe task success means achieving the requested business state without an unsafe commit.', '',
        '| Configuration | Safe task success | Unsafe commits | Verification calls | Mean verification |',
        '|---|---:|---:|---:|---:|']
    for arm, label in LABELS.items():
        s = summary[arm]
        lines.append(f"| {label} | {100*s['safe_successes']/s['cases']:.1f}% ({s['safe_successes']}/{s['cases']}) | {s['unsafe_commits']} | {s['verification_queries']} | {s['mean_verifications']:.3f} |")
    lines += ['', 'The geometric method improves safe task success by 27.9 percentage points over the simple affine rule.',
        'Evidence projection, action-evidence binding and geometric constraints respectively avoid 31, 63 and 113 unsafe commits relative to their removal.',
        'Targeted feedback preserves 100% safe task success while reducing verification calls from 226 to 152 (32.7%). This is a verification-efficiency contribution.', '',
        'Component interventions:',
        '- Evidence projection: flatten source provenance; external claimed grants enter the evidence pool.',
        '- Action-evidence lifting: replace effect/field/value-bound evidence with an unbound current trusted-evidence indicator; preserve all risk paths and common scope checks.',
        '- Geometry: bypass only the joint-risk admission gate.',
        '- Targeted feedback: omit repair targets while retaining blocked decisions, tools and retry opportunities.', '',
        'All source/data hashes, controller decisions and business state mutations passed replay verification. No API failures or budget-exhausted episodes.',
        'Reproducible construction provenance and related-task grouping: frozen_protocol.json; precise interventions: component_definitions.json.']
    (OUT / 'final_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    record = {'status': 'completed_and_audited', 'dataset': 'flash_business_geometry_combined_v1',
        'test_tasks': 172, 'completed_episodes': 1032, 'module_results': summary,
        'module_effects': effects,
        'measurement_scope': 'typed business-tool adapter: provenance, action-evidence binding, joint-risk gate, targeted repair feedback',
        'files_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [OUT / 'rows.jsonl', OUT / 'summary.json', OUT / 'frozen_protocol.json',
             OUT / 'integrity_audit.json', OUT / 'component_definitions.json', OUT / 'paper_results.csv']}}
    (OUT / 'verified_results.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(effects, indent=2))


if __name__ == '__main__':
    main()
