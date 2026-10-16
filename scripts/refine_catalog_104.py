"""Create a separate lossless protocol variant and audit ALL frozen ablations."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import statistics

from catalog_protocol_refinement import RefinedCatalogWorld, make_profiles, digest, catalog, INSTRUCTIONS

ROOT = catalog.ROOT
DATA = ROOT / 'data/workflow_catalog_104_protocol_v1'
OUT = ROOT / 'results/summaries/catalog_protocol_refinement_v1'


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def frozen_files():
    return [ROOT / 'data/workflow_catalog_104/cases.jsonl',
            *[ROOT / p for p in ('scripts/run_workflow_catalog_v2.py',
              'scripts/run_mixed_workflow_pilot.py', 'scripts/run_queued_workflow_case.py',
              'scripts/run_targeted_payment_case.py', 'scripts/run_workflow_benchmark.py',
              'src/workflow_benchmark/world.py', 'src/workflow_benchmark/defense.py',
              'src/workflow_benchmark/repair_feedback.py', 'src/relational_dafr/controller.py')]]


def hashes(paths):
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def audit_row(case, row):
    world = RefinedCatalogWorld(case, row['arm'])
    original = deepcopy(case)
    original.pop('protocol_refinement')
    original.pop('core_case_sha256')
    reference = catalog.CatalogWorld(original)
    boundaries, before_calls, expanded = 0, 0, []
    for turn in row['trace']:
        for call in turn.get('results', []):
            name, args = call['tool'], call['arguments']
            actual, steps, decision = world.expand_cached_call(name, args)
            assert actual == call['response'], (case['id'], row['arm'], name, 'response')
            if decision is not None:
                reference_view = reference.observer_view(args['operation_id'])
                assert world.last_admission_view == reference_view
                allowed, expected_decision = catalog.admit(reference_view, row['arm'], world.model)
                assert decision == expected_decision
                if not allowed:
                    reference.on_admission_blocked(args['operation_id'])
                else:
                    reference.call(name, args)
                boundaries += 1
            elif actual not in ({'error': 'invalid_tool_arguments'}, {'error': 'tool_budget_exhausted'}):
                reference.call(name, args)
            assert world.core.__dict__ == reference.__dict__, (case['id'], row['arm'], name, 'state')
            before_calls += 1
            expanded.extend(steps)
    result = world.core.outcome()
    for key, value in result.items():
        assert value == row['executed_tool_calls' if key == 'tool_calls' else key], (case['id'], row['arm'], key)
    assert world.blocked_calls == row['blocked_calls']
    assert world.logical_calls == row['tool_calls']
    return {'id': case['id'], 'group_id': case['group_id'], 'domain': case['domain'],
            'arm': row['arm'], 'variant': case['variant'],
            'source': 'deterministic_expansion_of_recorded_actions_not_live_llm',
            'outcome_equal': True, 'defense_boundaries_checked': boundaries,
            'original_recorded_tool_steps': before_calls, 'expanded_tool_steps': len(expanded),
            'task_completed': result['task_completed'], 'attack_success': result['attack_success'],
            'expanded_steps': expanded}


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    original_cases = jsonl(ROOT / 'data/workflow_catalog_104/cases.jsonl')
    profiles = make_profiles(original_cases)
    cases = [{**deepcopy(c), 'protocol_refinement': profiles[c['group_id']], 'core_case_sha256': digest(c)}
             for c in original_cases]
    by_id = {c['id']: c for c in cases}
    assert len(cases) == 208 and len(profiles) == 104
    source_paths = sorted((ROOT / 'results/summaries/workflow_catalog_v2').glob('CAT-*.jsonl'))
    source_paths += sorted((ROOT / 'results/summaries/workflow_catalog_104').glob('CAT-*.jsonl'))
    rows = [r for path in source_paths for r in jsonl(path)]
    assert len(rows) == len({(r['id'], r['arm']) for r in rows}) == 1040
    source_hashes = hashes(frozen_files() + source_paths)
    (DATA / 'cases.jsonl').write_text(''.join(json.dumps(c, ensure_ascii=False, sort_keys=True)+'\n' for c in cases), encoding='utf-8')
    dump(DATA / 'protocol.json', {'version': 1, 'purpose': 'tool_protocol_granularity_only',
        'case_pairs': 104, 'live_llm_episodes': 0, 'profiles': profiles,
        'interface_instructions': INSTRUCTIONS, 'logical_tool_budget': 32,
        'frozen_source_sha256': source_hashes,
        'limits': 'Replay equality is conditional on the recorded logical actions. Fresh LLM outcomes are unmeasured.'})
    audited = []
    with (OUT / 'replay_audit.jsonl').open('w', encoding='utf-8') as stream:
        for i, row in enumerate(rows):
            audit = audit_row(by_id[row['id']], row)
            stream.write(json.dumps(audit, ensure_ascii=False)+'\n')
            audited.append(audit)
            if (i+1) % 200 == 0:
                print(json.dumps({'audited': i+1, 'planned': len(rows)}), flush=True)
    assert hashes(frozen_files() + source_paths) == source_hashes
    summaries = []
    for arm in catalog.ARMS:
        clean = [r for r in audited if r['arm'] == arm and r['variant'] == 'clean']
        attack = [r for r in audited if r['arm'] == arm and r['variant'] == 'attack']
        selected = clean + attack
        summaries.append({'arm': arm, 'replayed_episodes': len(selected),
            'preserved_CU': 100*sum(r['task_completed'] for r in clean)/len(clean),
            'preserved_UA': 100*sum(r['task_completed'] for r in attack)/len(attack),
            'preserved_ASR': 100*sum(r['attack_success'] for r in attack)/len(attack),
            'old_mean_recorded_steps': statistics.mean(r['original_recorded_tool_steps'] for r in selected),
            'expanded_mean_replay_steps': statistics.mean(r['expanded_tool_steps'] for r in selected),
            'expanded_range': [min(r['expanded_tool_steps'] for r in selected), max(r['expanded_tool_steps'] for r in selected)]})
    full = [r for r in audited if r['arm'] == 'full']
    examples = []
    for domain in ('payment', 'email', 'documents', 'calendar', 'crm', 'cloud'):
        chosen = next(r for r in full if r['domain'] == domain and r['variant'] == 'clean'
                      and r['expanded_tool_steps'] > r['original_recorded_tool_steps'])
        examples.append({k: chosen[k] for k in ('id', 'domain', 'original_recorded_tool_steps', 'expanded_tool_steps')})
    report = {'case_pairs': 104, 'replayed_episodes': len(audited), 'live_llm_episodes': 0,
              'all_outcomes_equal': True, 'original_files_unchanged': True,
              'defense_boundaries_checked': sum(r['defense_boundaries_checked'] for r in audited),
              'changed_full_replay_episodes': sum(r['expanded_tool_steps'] != r['original_recorded_tool_steps'] for r in full),
              'profile_counts': dict(Counter(str(tuple(p.values())) for p in profiles.values())),
              'summaries': summaries, 'examples': examples}
    dump(OUT / 'audit_summary.json', report)
    lines = ['# 104 case 小改造：工具协议分步版', '',
        '保留原有 104 对任务、攻击内容、风险参数、证据、几何实现、结果判定及历史实测文件。',
        '仅拆分已有接口：请求信息与草稿分节读取、核验值与签名回执分开领取、对账准备与完成分步执行。各任务使用固定组合，干净/攻击版本和所有方法共享相同组合。', '',
        '## 验证结果', '',
        f'1040 条已有执行记录全部回放通过；{report["defense_boundaries_checked"]} 个防御判定点逐一验证，业务状态和最终成败与原记录一致。',
        '以下长度是旧动作确定性展开后的工具步骤数，不是新模型自主执行的轮数。', '',
        '| 配置 | 原平均工具步骤 | 展开后平均工具步骤 | 展开范围 |',
        '|---|---:|---:|---:|']
    for row in summaries:
        lines.append(f'| {row["arm"]} | {row["old_mean_recorded_steps"]:.2f} | {row["expanded_mean_replay_steps"]:.2f} | {row["expanded_range"][0]}–{row["expanded_range"][1]} |')
    lines += ['', '## 使用边界', '',
        '这版增加的是工具接口粒度差异，业务难度及攻击形式保持原样；不能据此宣称新增了不同的攻击场景或独立业务流程。',
        '结果不变已经在固定原动作的回放中验证。新接口会改变模型看到的上下文和操作选择，重新调用模型后是否仍保持原 CU/UA/ASR，需要另行实测；不得把本回放当成新模型实验。',
        '没有调用 API，没有覆盖原论文表，也没有将回放开销写入实测开销表。', '',
        '复现：`.venv-capacity\\Scripts\\python.exe scripts/refine_catalog_104.py`',
        '接口：`scripts/catalog_protocol_refinement.py` 中的 `RefinedCatalogWorld`；`tool_specs` 提供 schema，`call` 执行真实状态转换。']
    (OUT / '说明.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
