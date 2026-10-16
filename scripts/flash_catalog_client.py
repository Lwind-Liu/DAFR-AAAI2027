"""Concurrent compatible API client with a shared, resumable spend ceiling."""
import json
from pathlib import Path
import threading
import time
import urllib.request
import urllib.error

from run_flash_other_methods import BudgetExceeded


class ProviderError(RuntimeError):
    pass


class CatalogClient:
    def __init__(self, key, out, ceiling=45.):
        self.key = key
        self.out = Path(out)
        self.ceiling = ceiling
        self.lock = threading.Lock()
        self.reserved = 0.
        self.fatal_error = None
        path = self.out / 'usage.json'
        self.usage = json.loads(path.read_text()) if path.exists() else {
            'requests': 0, 'failed_requests': 0, 'prompt_tokens': 0,
            'completion_tokens': 0, 'estimated_cost_cny': 0.}

    def save(self):
        # Called under lock; replace avoids partially read progress files.
        temp = self.out / 'usage.tmp'
        temp.write_text(json.dumps(self.usage, indent=2), encoding='utf-8')
        temp.replace(self.out / 'usage.json')

    def chat(self, messages, tools=None, max_tokens=650):
        payload = {'model': 'deepseek-v4-flash-0731', 'messages': messages,
                   'temperature': 0, 'max_tokens': max_tokens, 'enable_thinking': False}
        if tools:
            payload.update(tools=tools, parallel_tool_calls=False)
        raw = json.dumps(payload).encode()
        reservation = (len(raw)*3 + max_tokens*9)/1e6
        for attempt in range(3):
            with self.lock:
                if self.fatal_error is not None:
                    raise ProviderError(self.fatal_error)
                if self.usage['estimated_cost_cny'] + self.reserved + reservation > self.ceiling:
                    raise BudgetExceeded('shared_budget_limit')
                self.reserved += reservation
            charged, success, response_usage = reservation, False, {}
            retry = False
            try:
                request = urllib.request.Request(
                    'https://ws-8a63tglzccujk0y9.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions',
                    data=raw, headers={'Content-Type': 'application/json',
                                       'Authorization': 'Bearer ' + self.key})
                with urllib.request.urlopen(request, timeout=90) as response:
                    data = json.load(response)
                response_usage = data.get('usage', {})
                if 'prompt_tokens' in response_usage and 'completion_tokens' in response_usage:
                    charged = (3*response_usage['prompt_tokens'] + 9*response_usage['completion_tokens'])/1e6
                message = data['choices'][0]['message']
                success = True
                return {k: message[k] for k in ('role', 'content', 'tool_calls') if k in message}, response_usage
            except urllib.error.HTTPError as error:
                if error.code in (401, 402, 403):
                    # Denied model access cannot be repaired by policy-parser
                    # retries. Stop further requests in this shared batch.
                    charged = 0.
                    with self.lock:
                        self.fatal_error = 'provider_http_' + str(error.code)
                        self.usage['fatal_provider_http_status'] = error.code
                        self.usage['rejected_requests'] = self.usage.get('rejected_requests', 0) + 1
                retry = error.code in (429, 500, 502, 503, 504) and attempt < 2
                if not retry:
                    raise ProviderError('provider_http_' + str(error.code)) from None
            except (urllib.error.URLError, TimeoutError):
                retry = attempt < 2
                if not retry:
                    raise ProviderError('provider_connection_error') from None
            finally:
                with self.lock:
                    self.reserved -= reservation
                    self.usage['estimated_cost_cny'] += charged
                    self.usage['requests' if success else 'failed_requests'] += 1
                    for name in ('prompt_tokens', 'completion_tokens'):
                        self.usage[name] += response_usage.get(name, 0)
                    self.save()
            if retry:
                time.sleep(2**attempt)
