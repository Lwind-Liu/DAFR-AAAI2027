"""Resume frozen v2 executions with schema-faithful trace replay.

Only the auditor is replaced; frozen data, defenses and episode execution
are imported unchanged. Invalid calls never mutate the execution world.
"""
import jsonschema
import run_workflow_catalog_v2 as catalog


def replay(case, row, model):
    world = catalog.CatalogWorld(case)
    validators = {t['function']['name']: t['function']['parameters']
                  for t in catalog.runner.schemas()}
    blocked, submitted = 0, 0
    for turn in row['trace']:
        for call in turn.get('results', []):
            name, args = call['tool'], call['arguments']
            try:
                if name not in validators:
                    raise ValueError('unknown_tool')
                jsonschema.validate(args, validators[name])
                if submitted >= 32:
                    actual = {'error': 'tool_budget_exhausted'}
                else:
                    submitted += 1
                    if name == 'commit_operation':
                        allowed, detail = catalog.admit(
                            world.observer_view(args['operation_id']), row['arm'], model)
                        if not allowed:
                            blocked += 1
                            world.on_admission_blocked(args['operation_id'])
                            actual = detail
                        else:
                            actual = world.call(name, args)
                    else:
                        actual = world.call(name, args)
            except (ValueError, TypeError, jsonschema.ValidationError):
                actual = {'error': 'invalid_tool_arguments'}
            assert actual == call['response'], (case['id'], row['arm'], name)
    assert blocked == row['blocked_calls']
    assert submitted == row['tool_calls']
    for key, value in world.outcome().items():
        assert value == row['executed_tool_calls' if key == 'tool_calls' else key], (
            case['id'], row['arm'], key)


if __name__ == '__main__':
    catalog.replay = replay
    catalog.main()
