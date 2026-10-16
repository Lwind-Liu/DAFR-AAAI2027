"""Recompute native scores from executed tool messages, without API requests."""
import json
from pathlib import Path
from run_ustc_qualitative_nodefense import ROOT, get_suite, FunctionsRuntime
from agentdojo.functions_runtime import FunctionCall
from agentdojo.task_suite.task_suite import model_output_from_messages, functions_stack_trace_from_messages
from agentdojo.agent_pipeline.tool_execution import tool_result_to_str


def main():
    base=ROOT/'results/summaries/qualitative_ustc_nodefense'
    results=[]
    for path in sorted(base.glob('*/no_defense.json')):
        row=json.loads(path.read_text(encoding='utf-8'))
        suite=get_suite('v1.2.2',row['suite_name'])
        task=suite.get_user_task_by_id(row['user_task_id'])
        attack=suite.get_injection_task_by_id(row['injection_task_id'])
        env=task.init_environment(suite.load_and_inject_default_environment(row['injections']))
        before=env.model_copy(deep=True)
        runtime=FunctionsRuntime(suite.tools)
        tools=[]
        for m in row['messages']:
            if m['role']!='tool':continue
            call=m['tool_call']
            result,error=runtime.run_function(env,call['function'],call['args'])
            assert error==m['error'],call['function']
            assert tool_result_to_str(result)==m['content'][0]['content'],call['function']
            tools.append(call['function'])
        messages=[]
        for message in row['messages']:
            m=dict(message)
            if m.get('tool_calls'):
                m['tool_calls']=[FunctionCall(**c) for c in m['tool_calls']]
            if m.get('tool_call'):
                m['tool_call']=FunctionCall(**m['tool_call'])
            messages.append(m)
        output=model_output_from_messages(messages) or []
        stack=functions_stack_trace_from_messages(messages)
        utility=suite._check_task_result(task,output,before,env,stack)
        security=suite._check_task_result(attack,output,before,env,stack)
        assert utility==row['utility'] and security==row['security']
        record={'case':path.parent.name,'utility':bool(utility),'attack_success':bool(security),
                'executed_tools':tools,'tool_response_replay':'exact_match','native_scores':'match',
                'api_error':row['error']}
        (path.parent/'audit.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
        results.append(record)
    (base/'summary.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results))


if __name__=='__main__':main()
