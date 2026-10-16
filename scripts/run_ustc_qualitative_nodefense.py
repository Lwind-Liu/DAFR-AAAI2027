"""Run an original AgentDojo attack with the exact archived prompt and injection.

Only No Defense is newly executed. Historical DAFR stays explicitly attributed
to its original model, rather than being relabeled as the current API model.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'external/official_baselines/AutoDojo/agentdojo/src'))
sys.path.insert(0, str(ROOT / 'src'))

import httpx
from openai import OpenAI
from agentdojo.agent_pipeline.llms.openai_llm import OpenAILLM
from agentdojo.agent_pipeline.tool_execution import ToolsExecutor
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.task_suite.load_suites import get_suite
from agentdojo.task_suite.task_suite import model_output_from_messages, functions_stack_trace_from_messages
from agentdojo.types import text_content_block_from_string


def plain(value):
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    if isinstance(value, dict):
        return {k: plain(v) for k,v in value.items()}
    if isinstance(value, (tuple,list)):
        return [plain(v) for v in value]
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', choices=('calendar','restaurant'), default='calendar')
    args = parser.parse_args()
    filename = {'calendar':'workspace_user_task_11_injection_task_6.json',
                'restaurant':'travel_user_task_9_injection_task_0.json'}[args.candidate]
    source = ROOT / 'results/summaries/qualitative_agentdojo_candidates' / filename
    historical = json.loads(source.read_text(encoding='utf-8'))
    out = ROOT / 'results/summaries/qualitative_ustc_nodefense' / args.candidate
    out.mkdir(parents=True, exist_ok=True)
    result_path = out / 'no_defense.json'
    if result_path.exists():
        raise RuntimeError('Existing result retained; use a separate run directory for a new trial.')
    model='deepseek-v4-flash-ascend'
    suite=get_suite('v1.2.2',historical['suite_name'])
    user=suite.get_user_task_by_id(historical['user_task_id'])
    attack=suite.get_injection_task_by_id(historical['injection_task_id'])
    environment=user.init_environment(suite.load_and_inject_default_environment(historical['injections']))
    initial=environment.model_copy(deep=True)
    runtime=FunctionsRuntime(suite.tools)
    # Use the exact system and user messages from the historical DAFR episode.
    messages=[m for m in historical['messages'][:2]]
    assert messages[0]['role']=='system' and messages[1]['role']=='user'
    assert messages[1]['content'][0]['content']==user.PROMPT
    protocol={'benchmark_version':'v1.2.2','suite':historical['suite_name'],
        'user_task':user.ID,'injection_task':attack.ID,'model':model,
        'base_url':'https://api.llm.ustc.edu.cn/v1','temperature':0,'max_llm_calls':16,
        'historical_dafr_model':historical['pipeline_name'],
        'historical_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'same_prompt_and_injections':True,'comparison_scope':'Case illustration; different recorded model identifiers.'}
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    (out/'historical_dafr.json').write_bytes(source.read_bytes())
    usage=[]
    def record_response(response):
        if response.request.url.path.endswith('/chat/completions'):
            response.read()
            if response.status_code==200:
                body=response.json()
                usage.append(body.get('usage',{}))
    client=OpenAI(api_key=os.environ['USTC_API_KEY'],base_url=protocol['base_url'],
        max_retries=1,timeout=90,
        http_client=httpx.Client(trust_env=False,event_hooks={'response':[record_response]}))
    llm=OpenAILLM(client,model,temperature=0)
    executor=ToolsExecutor()
    start=time.perf_counter()
    termination='turn_limit'
    error=None
    try:
        for turn in range(16):
            _,_,environment,messages,_=llm.query(user.PROMPT,runtime,environment,messages,{})
            calls=messages[-1].get('tool_calls') or []
            print(json.dumps({'turn':turn,'tools':[c.function if hasattr(c,'function') else c['function'] for c in calls]}),flush=True)
            (out/'partial_messages.json').write_text(json.dumps(plain(messages),ensure_ascii=False,indent=2),encoding='utf-8')
            if not calls:
                termination='model_finished';break
            _,_,environment,messages,_=executor.query(user.PROMPT,runtime,environment,messages,{})
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc).replace(os.environ['USTC_API_KEY'],'[REDACTED]')}
        termination='error'
    output=model_output_from_messages(messages) or []
    stack=functions_stack_trace_from_messages(messages)
    utility=suite._check_task_result(user,output,initial,environment,stack)
    security=suite._check_task_result(attack,output,initial,environment,stack)
    result={'suite_name':historical['suite_name'],'pipeline_name':model+'/no_defense',
        'user_task_id':user.ID,'injection_task_id':attack.ID,
        'benchmark_version':'v1.2.2','injections':historical['injections'],
        'messages':plain(messages),'utility':bool(utility),'security':bool(security),
        'termination':termination,'error':error,'usage':usage,
        'duration':time.perf_counter()-start}
    result_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    summary={k:result[k] for k in ('pipeline_name','utility','security','termination','error','duration')}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=True),flush=True)
    client.close()


if __name__=='__main__':
    main()
