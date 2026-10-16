"""Uniform 48-turn chain study, continuing every censored 32-turn prefix."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time
import jsonschema

import run_catalog_action_chains as chain
from flash_catalog_client import CatalogClient
import export_catalog_baseline_comparison as comparison

ROOT = chain.ROOT
OUT = ROOT / 'results/summaries/catalog_action_chains_v2'


def continue_episode(case, prefix, client):
    row = deepcopy(prefix)
    world, guard = chain.ChainWorld(case), chain.ChainGuard(prefix['arm'])
    messages = [{'role': 'system', 'content': chain.pilot.catalog.runner.SYSTEM}, {'role': 'user', 'content': case['task']}]
    tools = chain.pilot.catalog.runner.schemas()
    validators = {t['function']['name']: t['function']['parameters'] for t in tools}
    submitted, blocked = prefix['tool_calls'], prefix['blocked_calls']
    # Rebuild actual state, the frozen per-request constraints, and exact model
    # context. The original 32 turns are retained as observed executions.
    for turn in prefix['trace']:
        assistant = turn['assistant']
        messages.append(assistant)
        for call, result in zip(assistant.get('tool_calls') or [], turn.get('results', [])):
            name, args = result['tool'], result['arguments']
            try:
                jsonschema.validate(args, validators[name])
                if name == 'commit_operation':
                    allowed, detail = guard(world.observer_view(args['operation_id']))
                    if allowed:
                        actual = world.call(name, args)
                    else:
                        world.on_admission_blocked(args['operation_id'])
                        actual = detail
                else:
                    actual = world.call(name, args)
            except (KeyError, ValueError, TypeError, jsonschema.ValidationError):
                actual = {'error': 'invalid_tool_arguments'}
            assert actual == result['response']
            messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(actual)})
    assert guard.decisions == prefix['risk_decisions']
    attempts, termination = prefix['llm_calls'], 'turn_limit'
    started = time.monotonic()
    for turn in range(len(prefix['trace']), 48):
        try:
            assistant, usage = client.chat(messages, tools, max_tokens=650)
            attempts += 1
        except Exception as error:
            row['termination'] = 'api_error'
            row['continuation_error_type'] = type(error).__name__
            return row
        messages.append(assistant)
        entry = {'turn': turn, 'assistant': assistant, 'usage': usage, 'results': []}
        row['trace'].append(entry)
        calls = assistant.get('tool_calls') or []
        if not calls:
            termination = 'model_finished'
            break
        for call in calls:
            name, decision = call['function']['name'], None
            try:
                args = json.loads(call['function']['arguments'])
                if name not in validators:
                    raise ValueError()
                jsonschema.validate(args, validators[name])
                if submitted >= 48:
                    response = {'error': 'tool_budget_exhausted'}
                else:
                    submitted += 1
                    if name == 'commit_operation':
                        allowed, decision = guard(world.observer_view(args['operation_id']))
                        if allowed:
                            response = world.call(name, args)
                        else:
                            blocked += 1
                            world.on_admission_blocked(args['operation_id'])
                            response = decision
                    else:
                        response = world.call(name, args)
            except (ValueError, TypeError, jsonschema.ValidationError):
                args, response = {}, {'error': 'invalid_tool_arguments'}
            entry['results'].append({'tool': name, 'arguments': args, 'response': response, 'decision': decision})
            messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(response)})
        if submitted >= 48:
            termination = 'tool_limit'
            break
    row.update(world.outcome())
    row.update(termination=termination, tool_calls=submitted, executed_tool_calls=world.calls,
               blocked_calls=blocked, llm_calls=attempts, successful_llm_calls=sum('usage' in t for t in row['trace']),
               elapsed_seconds=prefix['elapsed_seconds'] + time.monotonic() - started,
               risk_decisions=guard.decisions, reused_prefix_turns=len(prefix['trace']))
    chain.audit(case, row)
    return row


def main():
    chain.pilot.catalog.configure_runner()
    source = chain.OUT
    original = json.loads((source / 'summary.json').read_text())
    assert original['complete']
    prefix_rows = [json.loads(line) for line in (source / 'rows.jsonl').read_text().splitlines()]
    cases = {c['id']: c for c in chain.make_cases()}
    OUT.mkdir(exist_ok=True)
    protocol = {'episodes': 72, 'max_turns': 48, 'max_tool_calls': 48,
        'parent': 'catalog_action_chains_v1', 'prefix_sha256': hashlib.sha256((source / 'rows.jsonl').read_bytes()).hexdigest(),
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'policy': 'All naturally terminated model_finished episodes are budget-invariant prefixes; all turn/tool-limited episodes are extended, regardless of outcome. All lengths and modes receive the same 48-turn / 48-call allowance.',
        'model': 'deepseek-v4-flash-0731', 'temperature': 0, 'planner_tokens': 650}
    path = OUT / 'protocol.json'
    if path.exists():
        assert json.loads(path.read_text()) == protocol
    else:
        chain.pilot.catalog.dump(path, protocol)
    rows_path = OUT / 'rows.jsonl'
    rows = [json.loads(line) for line in rows_path.read_text().splitlines()] if rows_path.exists() else []
    done = {(r['id'], r['arm']) for r in rows}
    jobs = []
    with rows_path.open('a') as stream:
        for prefix in prefix_rows:
            if (prefix['id'], prefix['arm']) in done:
                continue
            if prefix['termination'] == 'model_finished':
                row = deepcopy(prefix)
                row['reused_from'] = str(source.relative_to(ROOT))
                chain.audit(cases[row['id']], row)
                rows.append(row)
                stream.write(json.dumps(row) + '\n')
            else:
                assert prefix['termination'] in ('turn_limit', 'tool_limit')
                jobs.append(prefix)
        stream.flush()
        print(json.dumps({'reused_naturally_terminated': len(rows), 'prefixes_to_extend': len(jobs)}), flush=True)
        if jobs:
            key = sys.stdin.readline().strip()
            assert key
            client = CatalogClient(key, OUT, 3.)
            with ThreadPoolExecutor(max_workers=4) as pool:
                for future in as_completed([pool.submit(continue_episode, cases[r['id']], r, client) for r in jobs]):
                    row = future.result()
                    if row['termination'] == 'api_error':
                        with (OUT / 'attempts.log').open('a') as failed:
                            failed.write(json.dumps(row) + '\n')
                    else:
                        rows.append(row)
                        stream.write(json.dumps(row) + '\n')
                        stream.flush()
                    print(json.dumps({'accepted': len(rows), 'length': row['length'], 'arm': row['arm'], 'completed': row['task_completed']}), flush=True)
    assert len(rows) == len({(r['id'], r['arm']) for r in rows})
    for row in rows:
        chain.audit(cases[row['id']], row)
    result = [{'length': length, 'configuration': mode,
               **comparison.metrics([r for r in rows if r['length'] == length and r['arm'] == mode])}
              for length in (1, 2, 4) for mode in ('dynamic', 'static')]
    chain.pilot.catalog.dump(OUT / 'summary.json', {'complete': len(rows) == 72, 'rows': result})
    chain.pilot.catalog.dump(OUT / 'audit.json', {'replayed_episodes': len(rows), 'errors': 0, 'complete': len(rows) == 72})
    comparison.write_csv(OUT / 'trajectory_scaling.csv', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
