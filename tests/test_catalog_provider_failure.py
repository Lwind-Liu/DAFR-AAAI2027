"""Permission failures must not trigger repeated paid-model submissions."""
import io
import json
from pathlib import Path
import sys
import urllib.error
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from flash_catalog_client import CatalogClient, ProviderError


def test_denied_access_latches_across_calls_and_releases_the_reservation(tmp_path, monkeypatch):
    calls=[]
    def denied(request, **kwargs):
        calls.append(request)
        raise urllib.error.HTTPError(request.full_url, 403, 'Forbidden', {}, io.BytesIO(b'{}'))
    monkeypatch.setattr('urllib.request.urlopen', denied)
    client=CatalogClient('test-key', tmp_path, 1)
    for _ in range(5):
        with pytest.raises(ProviderError, match='provider_http_403'):
            client.chat([{'role':'user','content':'OK'}], max_tokens=16)
    assert len(calls)==1
    assert client.reserved==0
    assert client.usage['failed_requests']==1
    assert client.usage['rejected_requests']==1
    assert client.usage['estimated_cost_cny']==0


def test_restart_can_probe_restored_access_with_the_same_model_payload(tmp_path, monkeypatch):
    (tmp_path/'usage.json').write_text(json.dumps({'requests':0,'failed_requests':1,
        'prompt_tokens':0,'completion_tokens':0,'estimated_cost_cny':0,
        'fatal_provider_http_status':403}))
    def accepted(request, **kwargs):
        body=json.loads(request.data)
        assert body['model']=='deepseek-v4-flash-0731'
        assert body['temperature']==0 and body['enable_thinking'] is False
        return io.BytesIO(json.dumps({'choices':[{'message':{'role':'assistant','content':'OK'}}],
            'usage':{'prompt_tokens':100,'completion_tokens':2}}).encode())
    monkeypatch.setattr('urllib.request.urlopen', accepted)
    client=CatalogClient('test-key', tmp_path, 1)
    message, usage=client.chat([{'role':'user','content':'OK'}], max_tokens=16)
    assert message['content']=='OK'
    assert client.usage['requests']==1
    assert client.reserved==0
