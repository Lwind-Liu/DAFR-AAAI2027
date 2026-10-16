"""Report provider access errors without logging credentials or response text."""
import json
import sys
import urllib.error
import urllib.request

key = sys.stdin.readline().strip()
assert key
request = urllib.request.Request(
    'https://ws-8a63tglzccujk0y9.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions',
    data=json.dumps({'model': 'deepseek-v4-flash-0731',
                     'messages': [{'role': 'user', 'content': 'Reply OK.'}],
                     'temperature': 0, 'max_tokens': 16, 'enable_thinking': False}).encode(),
    headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        print(json.dumps({'status': response.status, 'ok': True}))
except urllib.error.HTTPError as error:
    body = json.loads(error.read())
    print(json.dumps({'status': error.code, 'error': body.get('error', body)}))
