"""Resume the feedback pilot with safe partial summaries and durable rows."""
import hashlib
import json
from pathlib import Path
import shutil

import run_catalog_feedback_24 as base

OLD = base.OUT
OUT = base.ROOT / 'results/summaries/catalog_feedback_24_v2'


def report(rows):
    result = []
    for arm in ('full', 'no_feedback'):
        selected = [r for r in rows if r['arm'] == arm]
        if not selected:
            continue
        clean = [r for r in selected if r['variant'] == 'clean']
        attacked = [r for r in selected if r['variant'] == 'attack']
        result.append({'arm': arm, 'clean_n': len(clean), 'attack_n': len(attacked),
            'CU': 100*sum(r['task_completed'] for r in clean)/len(clean) if clean else None,
            'UA': 100*sum(r['task_completed'] for r in attacked)/len(attacked) if attacked else None,
            'ASR': 100*sum(r['attack_success'] for r in attacked)/len(attacked) if attacked else None,
            'total_tool_calls':sum(r['tool_calls'] for r in selected),
            'total_llm_calls':sum(r['llm_calls'] for r in selected)})
    base.catalog.dump(OUT/'summary.json', {'complete': len(rows)==96, 'pairs':24,
        'accepted_episodes':len(rows), 'rows':result})
    base.comparison.write_csv(OUT/'ablation.csv', result)


original_episode = base.episode


def durable_episode(case, client):
    path = OUT/'episodes'/(case['id']+'.json')
    if path.exists():
        row = json.loads(path.read_text())
        base.auditor.replay(case,row,None)
        return row
    row = original_episode(case,client)
    if row['termination'] not in ('api_error','budget_exhausted'):
        base.catalog.dump(path,row)
    return row


if __name__ == '__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'episodes').mkdir(exist_ok=True)
    if not (OUT/'rows.jsonl').exists():
        shutil.copy2(OLD/'rows.jsonl',OUT/'rows.jsonl')
    base.catalog.dump(OUT/'resume_protocol.json', {
        'parent':str(OLD.relative_to(base.ROOT)),
        'change':'Partial summaries allow missing clean/attack groups. Each audited new episode is durably saved before returning to the aggregator.',
        'ablation_change':False,
        'wrapper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'parent_rows_sha256':hashlib.sha256((OLD/'rows.jsonl').read_bytes()).hexdigest()})
    base.OUT = OUT
    base.report = report
    base.episode = durable_episode
    base.main()
