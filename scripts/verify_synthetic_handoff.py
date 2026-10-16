"""Offline integration verification against a local mock compatible endpoint."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading


def main():
    package = Path(sys.argv[1]).resolve()
    # Exercise actual tool state transitions and the DAFR/replay path, without an LLM.
    sys.path.insert(0, str(package/'scripts'))
    sys.path.insert(0, str(package/'src'))
    sys.path.insert(0, str(package/'external/official_baselines/AutoDojo/agentdojo/src'))
    import catalog_baseline_adapter_v11 as baseline
    baseline.catalog.configure_runner()
    baseline.catalog.runner.WorkflowWorld = baseline.catalog.CatalogWorld
    baseline.catalog.runner.admit = baseline.catalog.admit
    cases = [json.loads(line) for line in (package/'data/workflow_catalog_104/cases.jsonl').read_text().splitlines()]
    case = next(c for c in cases if c['id'].startswith('CAT-101-') and c['variant'] == 'clean')
    model = baseline.catalog.simple_linear()
    class ScriptedTools:
        def __init__(self): self.turn = 0
        def chat(self, messages, tools=None, max_tokens=650):
            calls = [('read_request', {'request_id': case['request_id']}),
                     ('commit_operation', {'operation_id': 'OP-1'}),
                     ('get_status', {'request_id': case['request_id']}),
                     ('close_request', {'request_id': case['request_id'], 'operation_id': 'OP-1'})]
            if self.turn == len(calls): return {'role': 'assistant', 'content': 'Done.'}, {}
            name, arguments = calls[self.turn]; self.turn += 1
            return {'role': 'assistant', 'content': None, 'tool_calls': [dict(
                id=f'call_{self.turn}', type='function', function=dict(name=name, arguments=json.dumps(arguments)))]}, {}
    for arm in ('full', 'no_geometry'):
        row = baseline.catalog.runner.episode(case, arm, model, ScriptedTools(), max_turns=12)
        baseline.dafr_replay(case, row, model)
        assert row['task_completed'] and not row['attack_success'] and row['tool_calls'] == 4
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert self.path == '/v1/chat/completions'
            assert body['model'] == 'local-transport-test'
            requests.append(body)
            response = dict(choices=[dict(message=dict(role='assistant', content='Done.'))],
                            usage=dict(prompt_tokens=10, completion_tokens=2))
            raw = json.dumps(response).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            config = folder/'config.json'
            config.write_text(json.dumps(dict(model='local-transport-test',
                 base_url=f'http://127.0.0.1:{server.server_port}/v1')), encoding='utf-8')
            command = [sys.executable, 'scripts/run_synthetic_main_table.py', '--config', str(config),
                       '--output', str(folder/'results'), '--pairs', '2', '--workers', '2',
                       '--methods', 'no_defense', 'full']
            import os
            env = dict(os.environ, SYNTH_API_KEY='local-mock-only')
            subprocess.run(command, cwd=package, env=env, check=True, stdout=subprocess.PIPE)
            summary = json.loads((folder/'results/summary.json').read_text())
            assert summary['complete'] and summary['completed_episodes'] == 8
            assert all(r['clean_n'] == r['attack_n'] == 2 for r in summary['rows'])
            assert all(r['CU'] == r['UA'] == r['ASR'] == 0 for r in summary['rows'])
            assert len(list((folder/'results/episodes').glob('*.json'))) == 8
            count = len(requests)
            assert count == 9  # access probe plus eight mock episodes
            subprocess.run(command, cwd=package, env=env, check=True, stdout=subprocess.PIPE)
            assert len(requests) == count, 'Resume reissued completed API requests'
            assert json.loads((folder/'results/audit.json').read_text())['errors'] == 0
            print(json.dumps(dict(mock_endpoint=True, episodes=8, scripted_tool_episodes=2, replay_errors=0,
                                  resume_new_requests=0, real_api_calls=0)))
    finally:
        server.shutdown(); server.server_close()


if __name__ == '__main__': main()
