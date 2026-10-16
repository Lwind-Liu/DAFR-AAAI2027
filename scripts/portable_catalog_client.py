"""OpenAI-compatible transport; no embedded endpoints, models or credentials."""
import json
import threading
import time
import urllib.error
import urllib.request
from flash_catalog_client import ProviderError


class PortableClient:
    def __init__(self, key, config, out):
        self.key, self.config, self.out = key, config, out
        self.model = config['model']
        base = config['base_url'].rstrip('/')
        self.endpoint = base if base.endswith('/chat/completions') else base+'/chat/completions'
        self.lock = threading.Lock()
        self.fatal = None
        path = out/'usage.json'
        self.usage = json.loads(path.read_text()) if path.exists() else dict(requests=0,
            failed_requests=0, prompt_tokens=0, completion_tokens=0)

    def chat(self, messages, tools=None, max_tokens=650):
        payload = dict(model=self.model, messages=messages, temperature=0,
                       **{self.config.get('max_tokens_field', 'max_tokens'): max_tokens})
        if tools: payload.update(tools=tools, parallel_tool_calls=False)
        extra = self.config.get('extra_body', {})
        if any(k in extra for k in ('model', 'messages', 'tools', 'temperature', 'max_tokens', 'max_completion_tokens')):
            raise ValueError('extra_body cannot override experiment settings')
        payload.update(extra)
        for name in self.config.get('omit_fields', []):
            if name not in ('temperature', 'parallel_tool_calls'):
                raise ValueError('Only temperature/parallel_tool_calls may be omitted for API compatibility')
            payload.pop(name, None)
        raw = json.dumps(payload).encode()
        for attempt in range(3):
            with self.lock:
                if self.fatal: raise ProviderError(self.fatal)
                total = self.usage['requests'] + self.usage['failed_requests']
                if total >= self.config.get('max_requests', 20000):
                    self.fatal = 'request_limit_reached'
                    raise ProviderError(self.fatal)
                self.usage['requests'] += 1
            usage = {}; success = False
            try:
                request = urllib.request.Request(self.endpoint, data=raw,
                    headers={'Content-Type': 'application/json', 'Authorization': 'Bearer '+self.key})
                with urllib.request.urlopen(request, timeout=self.config.get('timeout_seconds', 120)) as response:
                    data = json.load(response)
                usage = data.get('usage') or {}
                message = data['choices'][0]['message']
                success = True
                return {k: message[k] for k in ('role', 'content', 'tool_calls') if k in message}, usage
            except urllib.error.HTTPError as error:
                if error.code in (401, 402, 403):
                    with self.lock: self.fatal = 'provider_http_'+str(error.code)
                if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise ProviderError('provider_http_'+str(error.code)) from None
            except (urllib.error.URLError, TimeoutError):
                if attempt == 2: raise ProviderError('provider_connection_error') from None
            finally:
                with self.lock:
                    if not success:
                        self.usage['requests'] -= 1
                        self.usage['failed_requests'] += 1
                    for k in ('prompt_tokens', 'completion_tokens'): self.usage[k] += usage.get(k, 0)
                    temp = self.out/'usage.tmp'
                    temp.write_text(json.dumps(self.usage, indent=2), encoding='utf-8')
                    temp.replace(self.out/'usage.json')
            time.sleep(2**attempt)
