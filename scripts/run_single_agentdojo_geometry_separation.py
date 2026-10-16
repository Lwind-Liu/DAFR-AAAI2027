"""One controlled AgentDojo case comparing DAFR geometry with one affine rule."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from run_single_dojo_case import baseline, dump
from workflow_benchmark.native_dojo import NativeDojoWorld, guard, native_region_view
from workflow_benchmark.defense import coordinates, representation
from relational_dafr.controller import surface_risk

CASE_PATH = ROOT / 'data/geometry_single_example_v1/example.json'
OUT = ROOT / 'results/summaries/geometry_single_example_v1'


def run_clean(case, model_output):
    world = NativeDojoWorld({**case, 'variant': 'clean'})
    for call in world.task.ground_truth(world.initial):
        world.call(call.function, call.args)
    return world.outcome(model_output)


def run_attack(case, arm, model, model_output):
    world = NativeDojoWorld({**case, 'variant': 'attack'})
    trace = []
    # Execute the user's native reference reads first, identically for each arm.
    for call in world.task.ground_truth(world.initial):
        result = world.call(call.function, call.args)
        trace.append({'phase': 'user_task', 'tool': call.function, 'allowed': True,
                      'result': result})
    # Replay the official injection-task reference trajectory through the guard.
    for call in world.attack_task.ground_truth(world.initial):
        if call.function.startswith(('get_', 'read_', 'search_', 'list_', 'check_', 'fetch_')):
            allowed, detail = True, {'reason': 'read_only'}
        else:
            allowed, detail = guard(world.visible_view(call.function, call.args), arm, model)
        if allowed:
            result = world.call(call.function, call.args)
        else:
            result = detail
        trace.append({'phase': 'injection_task', 'tool': call.function,
                      'arguments': call.args, 'allowed': allowed, 'result': result})
        if not allowed:
            break
    return {**world.outcome(model_output), 'trace': trace}


def main():
    case = json.loads(CASE_PATH.read_text(encoding='utf-8'))
    model, training = baseline()
    suite_world = NativeDojoWorld({**case, 'variant': 'clean'})
    clean_output = suite_world.task.GROUND_TRUTH_OUTPUT
    clean = run_clean(case, clean_output)
    attacks = {arm: run_attack(case, arm, model, clean_output)
               for arm in ('full', 'no_projection', 'no_lifting', 'linear', 'no_geometry')}
    geometry = attacks['full']
    linear = attacks['linear']

    # Verify the native attacker goal is reachable without an admission guard.
    unguarded_world = NativeDojoWorld({**case, 'variant': 'attack'})
    for call in unguarded_world.task.ground_truth(unguarded_world.initial):
        unguarded_world.call(call.function, call.args)
    for call in unguarded_world.attack_task.ground_truth(unguarded_world.initial):
        unguarded_world.call(call.function, call.args)
    unguarded = unguarded_world.outcome(clean_output)

    # Expose the two decision values for this exact attempted write.
    decision_world = NativeDojoWorld({**case, 'variant': 'attack'})
    for call in decision_world.task.ground_truth(decision_world.initial):
        decision_world.call(call.function, call.args)
    write_call = next(call for call in decision_world.attack_task.ground_truth(decision_world.initial)
                      if call.function == 'send_email')
    translated = native_region_view(decision_world.visible_view(write_call.function, write_call.args), 'linear')
    risk_scene, _ = representation(translated, 'full')
    feature = coordinates(translated, 'linear')
    linear_score = float(feature @ model['weights'] + model['bias'])
    diagnostics = {
        'geometric_joint_risk': surface_risk(risk_scene),
        'risk_budget': risk_scene['budget'],
        'linear_score': linear_score,
        'linear_threshold': model['threshold'],
        'linear_allowance_margin': float(model['threshold'] - linear_score),
    }

    assert clean['task_completed'], 'native clean utility did not pass'
    assert geometry['task_completed'] and not geometry['attack_success']
    assert not linear['task_completed'] and linear['attack_success']
    assert unguarded['attack_success'], 'native attack oracle did not pass'

    source_files = [CASE_PATH, ROOT / 'scripts/run_single_dojo_case.py',
                    ROOT / 'src/workflow_benchmark/native_dojo.py',
                    ROOT / 'src/workflow_benchmark/defense.py',
                    ROOT / 'src/relational_dafr/controller.py',
                    ROOT / 'data/workflow_geometry_v1/train.jsonl',
                    ROOT / 'data/workflow_geometry_v1/dev.jsonl']
    protocol = {
        'case': case,
        'linear_baseline': training,
        'comparison': 'full geometric surface vs one affine linear classifier, both using same lifted input and frozen train/dev calibration',
        'trajectory': 'AgentDojo native user-task and injection-task ground-truth calls; no model-generated trajectory',
        'metrics': 'native CU/UA/ASR semantics; single paired case',
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in source_files},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    dump(OUT / 'protocol.json', protocol)
    dump(OUT / 'results.json', {
        'clean': clean,
        'module_arms': attacks,
        'native_unguarded_attack_reference': unguarded,
        'decision_diagnostics': diagnostics,
        'counts': {
            'CU': {arm: int(clean['task_completed']) for arm in attacks},
            'UA': {arm: int(row['task_completed']) for arm, row in attacks.items()},
            'ASR': {arm: int(row['attack_success']) for arm, row in attacks.items()},
        },
    })
    print(json.dumps({
        'CU': {arm: clean['task_completed'] for arm in attacks},
        'UA': {arm: row['task_completed'] for arm, row in attacks.items()},
        'ASR': {arm: row['attack_success'] for arm, row in attacks.items()},
        'native_unguarded_attack_reachable': unguarded['attack_success'],
        'decision_diagnostics': diagnostics,
        'output': str(OUT.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
