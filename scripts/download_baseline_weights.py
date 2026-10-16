"""Download public detector weights in ranges and verify publisher SHA-256."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import urllib.request


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def download(url, target, size, sha256, workers=16):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size == size:
        if hashlib.sha256(target.read_bytes()).hexdigest() == sha256:
            return target
    parts_dir = Path(tempfile.gettempdir()) / 'dafr-baseline-downloads' / sha256
    parts_dir.mkdir(parents=True, exist_ok=True)
    step = math.ceil(size / workers)

    def part(index):
        start, end = index * step, min(size, (index + 1) * step) - 1
        path = parts_dir / f'{index:02d}.part'
        if path.exists() and path.stat().st_size == end - start + 1:
            return path
        for attempt in range(3):
            try:
                offset = path.stat().st_size if path.exists() else 0
                request_start = start + offset
                separator = '&' if '?' in url else '?'
                req = urllib.request.Request(url + separator + f'dafr_part={index}&dafr_start={request_start}',
                    headers={'Range': f'bytes={request_start}-{end}'})
                with urllib.request.urlopen(req, timeout=60) as r, path.open('ab') as stream:
                    assert r.status == 206 and r.headers['Content-Range'].startswith(f'bytes {request_start}-{end}/')
                    shutil.copyfileobj(r, stream, length=1024 * 1024)
                assert path.stat().st_size == end - start + 1
                print(json.dumps({'file': target.name, 'part': index, 'bytes': path.stat().st_size}), flush=True)
                return path
            except Exception:
                if attempt == 2:
                    raise

    with ThreadPoolExecutor(workers) as pool:
        paths = list(pool.map(part, range(workers)))
    assembly = parts_dir / 'assembled'
    digest = hashlib.sha256()
    with assembly.open('wb') as stream:
        for path in paths:
            with path.open('rb') as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                    stream.write(chunk)
    assert digest.hexdigest() == sha256, 'Publisher checksum mismatch'
    shutil.copyfile(assembly, target)
    print(json.dumps({'verified': str(target), 'sha256': sha256}), flush=True)
    return target


def main():
    d = fetch_json('https://pypi.org/pypi/torch/json')
    wheel = next(f for f in d['urls'] if 'cp312-cp312-win_amd64' in f['filename'])
    target = Path(tempfile.gettempdir()) / 'dafr-baseline-downloads' / wheel['filename']
    # A local mirror accelerates the wheel transfer. Verify against the official
    # PyPI digest above before the installer ever opens the downloaded file.
    wheel_url = wheel['url'].replace('https://files.pythonhosted.org/packages/',
                                     'https://pypi.tuna.tsinghua.edu.cn/packages/')
    jobs = [(wheel_url, target, wheel['size'], wheel['digests']['sha256'])]
    for repo, revision in [('leolee99/PIGuard', 'dd78b24e330193a22d2293ac66922dd4f982f563'),
                           ('protectai/deberta-v3-base-prompt-injection-v2', '90c9989b1a342275dd0d1a95aad283c04e075671')]:
        info = fetch_json(f'https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true')
        lfs = next(f['lfs'] for f in info['siblings'] if f['rfilename'] == 'model.safetensors')
        target = (Path.home() / '.cache/huggingface/hub' / ('models--' + repo.replace('/', '--'))
                  / 'snapshots' / revision / 'model.safetensors')
        jobs.append((f'https://huggingface.co/{repo}/resolve/{revision}/model.safetensors?download=true',
                     target, lfs['size'], lfs['sha256']))
    with ThreadPoolExecutor(3) as pool:
        results = list(pool.map(lambda args: download(*args), jobs))
    print(json.dumps({'completed': [str(p) for p in results]}), flush=True)


if __name__ == '__main__':
    main()
