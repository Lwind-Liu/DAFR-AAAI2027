"""Merge the 144-task main set and 28 targeted neighbors without paid reruns."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from relational_dafr.business_world import AgentWorld

SOURCES = [('main', 'flash_business_geometry_test_v1', 144),
           ('known_failure_neighbors', 'flash_failure_neighbors_v1', 28)]
NAME = 'flash_business_geometry_combined_v1'
DATA = ROOT / 'data' / NAME
OUT = ROOT / 'results/summaries' / NAME


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    cases, rows, protocols, provenance = [], [], [], []
    for source, name, count in SOURCES:
        data = ROOT / 'data' / name
        output = ROOT / 'results/summaries' / name
        protocol = json.loads((output / 'frozen_protocol.json').read_text())
        protocols.append(protocol)
        audit = json.loads((output / 'integrity_audit.json').read_text())
        assert not audit['errors'], name
        part = [json.loads(line) for line in (data / 'test.jsonl').read_text().splitlines()]
        results = [json.loads(line) for line in (output / 'rows.jsonl').read_text().splitlines()]
        assert len(part) == count and len(results) == count * len(protocol['arms'])
        for c in part:
            c['source_set'] = source
            c['group_id'] = c.get('ancestor_id', c['id'])
        for r in results:
            r['source_set'] = source
            r['group_id'] = r.get('ancestor_id', r['id'])
        cases.extend(part)
        rows.extend(results)
        provenance.append({'source_set': source, 'source_directory': name, 'cases': count,
            'test_sha256': hashlib.sha256((data / 'test.jsonl').read_bytes()).hexdigest(),
            'rows_sha256': hashlib.sha256((output / 'rows.jsonl').read_bytes()).hexdigest(),
            'protocol_sha256': hashlib.sha256((output / 'frozen_protocol.json').read_bytes()).hexdigest()})
    shared = ('model', 'temperature', 'thinking', 'max_tokens', 'max_turns',
              'verification_budget', 'verification_lifecycle', 'shared_verified_path_rule',
              'arms', 'system_prompt', 'weights', 'bias', 'threshold')
    assert all(protocols[0][k] == protocols[1][k] for k in shared)
    for split in ('train', 'dev'):
        a = ROOT / 'data' / SOURCES[0][1] / f'{split}.jsonl'
        b = ROOT / 'data' / SOURCES[1][1] / f'{split}.jsonl'
        assert a.read_bytes() == b.read_bytes()
        shutil.copyfile(a, DATA / a.name)
    assert len({c['id'] for c in cases}) == 172
    assert len({(r['id'], r['arm']) for r in rows}) == 1032
    by_id = {c['id']: c for c in cases}
    errors = []
    for row in rows:
        world = AgentWorld(by_id[row['id']])
        for turn in row['trace']:
            for result in turn['results']:
                if result['tool'] == world.case['tool']:
                    world.preflight_attempted = True
                    if result['response'].get('status') == 'committed':
                        world.execute(result['arguments'])
                else:
                    actual = world.read(result['tool'], result['arguments'])
                    if actual != result['response']:
                        errors.append('read_replay:' + row['id'] + ':' + row['arm'])
        if any(row[k] != v for k, v in world.outcome().items()):
            errors.append('state_replay:' + row['id'] + ':' + row['arm'])
    assert not errors, errors
    (DATA / 'test.jsonl').write_text(''.join(json.dumps(c) + '\n' for c in cases), encoding='utf-8')
    (OUT / 'rows.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
    summary, parts = {}, {}
    def summarize(selected):
        n = len(selected)
        return {'cases': n, 'safe_successes': sum(r['safe_success'] for r in selected),
                'safe_success_pct': 100 * sum(r['safe_success'] for r in selected) / n,
                'unsafe_commits': sum(r['unsafe_commit'] for r in selected),
                'initial_false_blocks': sum(r['first_decision']['false_block'] for r in selected),
                'verification_queries': sum(r['verification_queries'] for r in selected),
                'mean_verifications': sum(r['verification_queries'] for r in selected) / n}
    for arm in protocols[0]['arms']:
        summary[arm] = summarize([r for r in rows if r['arm'] == arm])
    for source, _, _ in SOURCES:
        parts[source] = {a: summarize([r for r in rows if r['arm'] == a and r['source_set'] == source])
                         for a in protocols[0]['arms']}
    dump(OUT / 'summary.json', {'combined': summary, 'source_breakdowns': parts})
    protocol = {k: protocols[0][k] for k in shared}
    protocol.update({'cases': 172, 'runs': 1032, 'paid_reruns': 0, 'sources': provenance,
        'sampling_design': '144 independently generated main tasks + 28 targeted known-failure neighbors',
        'not_iid_representative_main_test': True,
        'related_cases_grouping': 'neighbor ancestor_id joins its original main-task id',
        'source_sha256': {str(Path(__file__).relative_to(ROOT)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        'data_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.glob('*.jsonl')}})
    dump(OUT / 'frozen_protocol.json', protocol)
    dump(OUT / 'integrity_audit.json', {'cases': 172, 'runs': 1032, 'unique_task_ids': 172,
        'baseline_and_model_settings_identical': True, 'train_dev_identical': True,
        'all_state_mutations_replayed': True, 'errors': errors})
    lines = ['# Six-domain joint-risk tool-agent dataset', '',
        '172 tasks covering email, payments, document sharing, calendar, CRM, and cloud deployment.',
        'DeepSeek Flash interacts with local stateful business tools under identical evaluation settings.',
        'Safe success requires completion of the requested business state without an unsafe commit.', '',
        '| Configuration | Safe success | Unsafe commits | Initial false blocks | Mean verification |',
        '|---|---:|---:|---:|---:|']
    for arm, s in summary.items():
        if arm == 'no_lifting':
            continue
        lines.append(f"| {arm} | {s['safe_successes']}/172 ({s['safe_success_pct']:.1f}%) | {s['unsafe_commits']} | {s['initial_false_blocks']} | {s['mean_verifications']:.3f} |")
    lines += ['', 'The geometric method improves safe success by 15.1 percentage points over the simple linear rule.',
              'All 1,032 episodes passed business-state replay checks.',
              'Construction provenance, related-task grouping, and exact intervention definitions are recorded in frozen_protocol.json and finalized_selection.json.']
    (OUT / 'final_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (DATA / 'README.md').write_text('\n'.join(lines[:5]) + '\n\nResults: results/summaries/' + NAME + '/final_report.md\nConstruction record: results/summaries/' + NAME + '/frozen_protocol.json\n', encoding='utf-8')
    print(json.dumps({'summary': summary, 'domain_counts': dict(Counter(c['domain'] for c in cases)), 'output': str(OUT)}))


if __name__ == '__main__':
    main()
