"""Light environment adapters for the main-table baselines on frozen tasks.

The detector weights, Progent policy generation/enforcement, and DRIFT constraint
building/isolation/validation are reused from the vendored implementations.
No DAFR admission function or hidden safety label is supplied to these methods.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import importlib.util
import json
import logging
from pathlib import Path
import random
import re
import sys
import threading
from types import SimpleNamespace
import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from run_flash_business_geometry import Client, BudgetExceeded, SYSTEM, dump
from relational_dafr.business_world import schemas
from relational_dafr.operational_failures import AgentWorld

VENDOR = ROOT / 'external/official_baselines/AutoDojo/agentdojo/src/agentdojo/agent_pipeline'
METHODS = ('piguard', 'protectai', 'progent', 'drift')
DETECTORS = {
    'piguard': ('leolee99/PIGuard', 'dd78b24e330193a22d2293ac66922dd4f982f563'),
    'protectai': ('protectai/deberta-v3-base-prompt-injection-v2', '90c9989b1a342275dd0d1a95aad283c04e075671'),
}


class BudgetClient(Client):
    def chat(self, messages, tools=None, max_tokens=650):
        payload = {'model': 'deepseek-flash', 'messages': messages,
                   'temperature': 0, 'max_tokens': max_tokens,
                   'thinking': {'type': 'disabled'}}
        if tools:
            payload.update(tools=tools, parallel_tool_calls=False)
        reservation = (len(json.dumps(payload).encode()) * 3 + max_tokens * 12) / 1e6
        with self.lock:
            if self.spent_upper + self.reserved + reservation > self.budget:
                raise BudgetExceeded('conservative_budget_limit')
            self.reserved += reservation
        charged = reservation
        try:
            response = self.request('/chat/completions', payload)
            usage = response.get('usage', {})
            prompt, hits = usage.get('prompt_tokens', 0), usage.get('prompt_cache_hit_tokens', 0)
            assert 0 <= hits <= prompt
            charged = ((prompt - hits) * 3 + hits * .06 + usage.get('completion_tokens', 0) * 12) / 1e6
            with self.lock:
                self.usage['requests'] += 1
                for key in ('prompt_tokens', 'completion_tokens'):
                    self.usage[key] += usage.get(key, 0)
            message = response['choices'][0]['message']
            return {k: message[k] for k in ('role', 'content', 'tool_calls') if k in message}, usage
        except Exception:
            with self.lock:
                self.usage['failed_requests'] += 1
            raise
        finally:
            with self.lock:
                self.reserved -= reservation
                self.spent_upper += charged


class ProgentAdapter:
    def __init__(self, case, client):
        # The reference stores policies in module globals. An isolated module per
        # episode preserves its code and prevents cross-task/thread contamination.
        name = 'agentdojo.agent_pipeline.progent_defense.secagent.task_' + case['id']
        spec = importlib.util.spec_from_file_location(name, VENDOR / 'progent_defense/secagent/tool.py')
        self.core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.core)
        self.calls = []
        self.core.print = lambda *args, **kwargs: None
        self.core.policy_model = 'deepseek-flash'

        def api_request(system, user, temperature=0):
            message, usage = client.chat([{'role': 'system', 'content': system},
                                          {'role': 'user', 'content': user}], max_tokens=2048)
            self.calls.append({'system': system, 'user': user, 'message': message, 'usage': usage})
            return message.get('content') or ''

        self.core.api_request = api_request
        self.core.update_available_tools([{'name': t['function']['name'],
            'description': t['function']['description'],
            'args': t['function']['parameters']['properties']} for t in schemas(case)])
        self.core.reset_security_policy(include_human_policy=True)
        self.core.update_always_allowed_tools(['read_record', 'read_policy', 'verify_field'])
        self.core.generate_security_policy(case['task'], manual_check=False)

    def admit(self, name, args):
        try:
            self.core.check_tool_call(name, args)
            return True, None
        except self.core.ValidationError as error:
            return False, {'status': 'blocked', 'reason': str(error)}

    def update(self, executed):
        if executed:
            self.core.generate_update_security_policy(
                [{'name': r['tool'], 'args': r['arguments']} for r in executed],
                str([json.dumps(r['response']) for r in executed]), manual_check=False)


class FilterAdapter:
    def __init__(self, name):
        import torch
        from huggingface_hub import snapshot_download
        torch.set_num_threads(2)
        model_id, revision = DETECTORS[name]
        snapshot = snapshot_download(model_id, revision=revision, allow_patterns=[
            'config.json', 'model.safetensors', 'tokenizer*', 'spm.model',
            'added_tokens.json', 'special_tokens_map.json', 'modeling_piguard.py', '__init__.py'])
        params = {'device': 'cpu', 'threshold': .5, 'model_id': snapshot}
        if name == 'piguard':
            from agentdojo.agent_pipeline.filter_defenses.piguard_defense import PIGuardDefense
            self.core = PIGuardDefense({'params': params})
        else:
            from agentdojo.agent_pipeline.filter_defenses.protectai_defense import ProtectAIDefense
            self.core = ProtectAIDefense({'params': params})
        self.lock = threading.Lock()
        self.cache = {}

    def filter(self, text):
        # Same sentence filtering and placeholder as DefenseFilterElement.
        with self.lock:
            if text not in self.cache:
                filtered, meta = self.core.filter_sentences(text)
                if meta.get('blocked'):
                    filtered = '[Content removed by defense]'
                self.cache[text] = (filtered, meta)
            return self.cache[text]


class DriftClient:
    def __init__(self, case, world, client):
        self.case, self.world, self.client = case, world, client
        self.calls = []
        self.logger = logging.getLogger('synthetic-drift')
        self.logger.addHandler(logging.NullHandler())

    def llm_run(self, system, user, name='default'):
        message, usage = self.client.chat([{'role': 'system', 'content': system},
                                           {'role': 'user', 'content': user}], max_tokens=2048)
        self.calls.append({'kind': 'defense', 'system': system, 'user': user,
                           'message': message, 'usage': usage})
        return message.get('content') or ''

    def agent_run(self, messages, tools=(), query=None, initial_trajectory=None,
                  achieved_trajectory=None, node_checklist=None, name='default'):
        from agentdojo.agent_pipeline.drift_defense.drift_client import _inject_agent_system_message
        messages = _inject_agent_system_message(deepcopy(messages), tools, query,
            initial_trajectory, achieved_trajectory, node_checklist)
        message, usage = self.client.chat(messages, max_tokens=650 if query else 2048)
        self.calls.append({'kind': 'planner' if query else 'constraint_build',
                           'messages': messages, 'message': message, 'usage': usage})
        content = message.get('content') or ''
        # A rejected write is still an operation preflight in the common runtime.
        if query:
            match = re.search(r'<function_call>(.*?)</function_call>', content, re.DOTALL)
            if match and re.search(r'\b' + re.escape(self.case['tool']) + r'\s*\(', match.group(1)):
                self.world.preflight_attempted = True
        return [content]


def drift_setup(case, world, client):
    from agentdojo.agent_pipeline.drift_defense.drift_llm import DRIFTLLM
    from agentdojo.agent_pipeline.drift_defense import drift_client
    # Only replace the original benchmark's company/user context with this world.
    drift_client.ENVIRONMENT_GUIDELINES = SYSTEM
    bridge = DriftClient(case, world, client)
    core = DRIFTLLM(bridge, config=SimpleNamespace(build_constraints=True,
                     injection_isolation=True, dynamic_validation=True))
    functions = {}
    for t in schemas(case):
        f = t['function']
        params = SimpleNamespace(model_json_schema=lambda s=f['parameters']: deepcopy(s))
        functions[f['name']] = SimpleNamespace(name=f['name'], description=f['description'], parameters=params)
    return core, bridge, SimpleNamespace(functions=functions)


def episode(case, method, client, filters, max_turns=10):
    world = AgentWorld(case)
    messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': case['task']}]
    trace, defense = [], None
    termination = 'turn_limit'
    try:
        if method == 'progent':
            defense = ProgentAdapter(case, client)
        if method == 'drift':
            core, defense, runtime = drift_setup(case, world, client)
            messages = [{'role': 'user', 'content': case['task']}]
        for turn in range(max_turns):
            rejected_retry = False
            if method == 'drift':
                _, _, _, updated, _ = core.query(case['task'], runtime, messages=messages)
                messages = list(updated)
                rejected_retry = messages[-1]['role'] == 'user'
                assistant = messages[-2] if rejected_retry else messages[-1]
                calls = assistant.get('tool_calls') or []
                calls = [{'id': c.id, 'function': {'name': c.function, 'arguments': json.dumps(c.args)}} for c in calls]
                serialized = json.loads(json.dumps(assistant, default=lambda c: c.model_dump()))
                usage = None
            else:
                assistant, usage = client.chat(messages, schemas(case))
                messages.append(assistant)
                serialized, calls = assistant, assistant.get('tool_calls') or []
            trace.append({'turn': turn, 'assistant': serialized, 'usage': usage,
                          'blocked_retry': rejected_retry, 'results': []})
            if not calls:
                if rejected_retry:
                    trace[-1]['block_message'] = messages[-1]['content']
                    continue
                termination = 'model_finished'
                break
            stop, executed = False, []
            for call in calls:
                name = call['function']['name']
                try:
                    args = json.loads(call['function']['arguments'])
                    if not isinstance(args, dict):
                        raise ValueError('object required')
                except (ValueError, TypeError):
                    args, result = {}, {'error': 'invalid_arguments'}
                else:
                    if name == case['tool']:
                        world.preflight_attempted = True
                    valid = next((t['function']['parameters'] for t in schemas(case)
                                  if t['function']['name'] == name), None)
                    try:
                        if valid is None:
                            raise ValueError('unknown_tool')
                        jsonschema.validate(args, valid)
                    except (ValueError, jsonschema.ValidationError) as error:
                        allowed, result = False, {'error': 'invalid_tool_schema', 'reason': str(error)}
                    else:
                        allowed, result = defense.admit(name, args) if method == 'progent' else (True, None)
                    if allowed:
                        result = world.execute(args) if name == case['tool'] else world.read(name, args)
                        executed.append({'tool': name, 'arguments': args, 'response': result})
                        if name == case['tool']:
                            termination, stop = 'committed', True
                record = {'tool': name, 'arguments': args, 'response': result}
                visible = json.dumps(result)
                if method in filters:
                    visible, record['filter_metadata'] = filters[method].filter(visible)
                record['visible_response'] = visible
                trace[-1]['results'].append(record)
                msg = {'role': 'tool', 'tool_call_id': call['id'], 'content': visible}
                if method == 'drift':
                    from agentdojo.functions_runtime import FunctionCall
                    msg.update(tool_call=FunctionCall(function=name, args=args, id=call['id']), error=None)
                messages.append(msg)
            if stop:
                break
            if method == 'progent':
                defense.update(executed)
    except BudgetExceeded:
        termination = 'budget_exhausted'
    except Exception as error:
        termination = type(error).__name__ + ':' + str(error)
    return {'id': case['id'], 'domain': case['domain'], 'arm': method,
            'termination': termination, **world.outcome(), 'trace': trace,
            'defense_calls': defense.calls if defense else []}


def summarize(rows, output):
    arms = {}
    for method in ('no_defense', *METHODS, 'full'):
        selected = [r for r in rows if r['arm'] == method]
        arms[method] = {'cases': len(selected),
            'safe_successes': sum(r['safe_success'] for r in selected),
            'safe_success_pct': 100 * sum(r['safe_success'] for r in selected) / len(selected) if selected else None,
            'unsafe_executions': sum(not e['safe'] for r in selected for e in r['effects']),
            'unsafe_tasks': sum(r['unsafe_commit'] for r in selected),
            'registry_verifications': sum(r['verification_queries'] for r in selected),
            'verification_calls': sum(t['tool'] == 'verify_field' for r in selected
                                      for turn in r['trace'] for t in turn['results']),
            'termination_counts': {t: sum(r['termination'] == t for r in selected)
                                   for t in sorted({r['termination'] for r in selected})}}
    dump(output / 'summary.json', {'arms': arms})
    import csv
    with (output / 'comparison.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['method', 'cases', 'safe_task_success_pct', 'unsafe_executions', 'verification_calls'])
        for m, s in arms.items():
            writer.writerow([m, s['cases'], s['safe_success_pct'], s['unsafe_executions'], s['verification_calls']])
    return arms


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='results/summaries/flash_other_methods_v1')
    parser.add_argument('--budget-cny', type=float, default=15)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--methods', nargs='+', choices=METHODS, default=list(METHODS))
    parser.add_argument('--limit', type=int, default=196)
    args = parser.parse_args()
    output = ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)
    data = ROOT / 'data/flash_business_geometry_final_v4/test.jsonl'
    cases = [json.loads(line) for line in data.read_text(encoding='utf-8').splitlines()]
    assert len(cases) == 196
    sources = [Path(__file__), *sorted(VENDOR.glob('progent_defense/secagent/*.py')),
               VENDOR / 'drift_defense/drift_llm.py', VENDOR / 'drift_defense/drift_prompts.py',
               VENDOR / 'drift_defense/drift_client.py', VENDOR / 'filter_defenses/piguard_defense.py',
               VENDOR / 'filter_defenses/protectai_defense.py']
    protocol = {'cases': 196, 'dataset_sha256': hashlib.sha256(data.read_bytes()).hexdigest(),
        'model': 'deepseek-flash', 'temperature': 0, 'thinking': 'disabled',
        'max_planner_tokens': 650, 'max_defense_tokens': 2048, 'max_turns': 10,
        'verification_budget': 4, 'system_prompt': SYSTEM,
        'verification_metrics': {'verification_calls': 'all invoked verify_field tools, including preflight refusals',
                                 'registry_verifications': 'registry attempts after the required preflight'},
        'reused_arms': {'full': 'flash_business_geometry_final_v4/full',
                        'no_defense': 'flash_business_geometry_final_v4/no_geometric_region'},
        'filters': 'original sentence filtering, all tool results, threshold 0.5, CPU',
        'detector_revisions': DETECTORS,
        'progent': 'original generation, refinement and checking; per-task module state; read tools always allowed',
        'drift': 'original constraint building, injection isolation, trajectory and checklist validation; new environment context',
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    frozen = output / 'frozen_protocol.json'
    # JSON normalizes revision tuples into lists for repeatable resume checks.
    protocol = json.loads(json.dumps(protocol))
    if frozen.exists():
        assert json.loads(frozen.read_text(encoding='utf-8')) == protocol, 'Protocol changed'
    dump(frozen, protocol)
    (output / 'runner_snapshot.py').write_bytes(Path(__file__).read_bytes())
    rows_file = output / 'rows.jsonl'
    rows = [json.loads(line) for line in rows_file.read_text(encoding='utf-8').splitlines()] if rows_file.exists() else []
    if not rows:
        source = ROOT / 'results/summaries/flash_business_geometry_final_v4/rows.jsonl'
        for line in source.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            if row['arm'] in ('full_surface', 'no_geometric_region'):
                row['reused_from'] = str(source.relative_to(ROOT))
                row['arm'] = 'full' if row['arm'] == 'full_surface' else 'no_defense'
                rows.append(row)
        rows_file.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
    done = {(r['id'], r['arm']) for r in rows}
    filters = {m: FilterAdapter(m) for m in args.methods if m in ('piguard', 'protectai')}
    client = BudgetClient(args.budget_cny, output)
    prior = output / 'usage.json'
    if prior.exists():
        usage = json.loads(prior.read_text(encoding='utf-8'))
        client.spent_upper = usage['conservative_cost_cny']
        client.usage = {k: usage[k] for k in client.usage}
    jobs = [(c, m) for c in cases[:args.limit] for m in args.methods if (c['id'], m) not in done]
    random.Random(20261027).shuffle(jobs)
    print(json.dumps({'event': 'started', 'jobs': len(jobs), 'budget_cny': client.budget}), flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool, rows_file.open('a', encoding='utf-8') as stream:
        futures = [pool.submit(episode, c, m, client, filters) for c, m in jobs]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            stream.write(json.dumps(row) + '\n')
            stream.flush()
            summarize(rows, output)
            dump(output / 'usage.json', {**client.usage, 'conservative_cost_cny': client.spent_upper,
                                       'budget_cny': client.budget})
            print(json.dumps({'method': row['arm'], 'id': row['id'], 'termination': row['termination'],
                              'safe': row['safe_success'], 'completed_new': len(rows) - 392,
                              'cost_upper_cny': round(client.spent_upper, 4)}), flush=True)
    dump(output / 'balance_after.json', client.balance())
    print(json.dumps(summarize(rows, output)), flush=True)


if __name__ == '__main__':
    main()
