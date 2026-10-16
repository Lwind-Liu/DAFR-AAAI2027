"""Package Git-visible workspace files; scan credentials and hash every entry.

No environment variables or credentials are read. Ignored local files (venvs,
API configuration, caches) are not included. ZIP members are scanned recursively.
"""
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist/workspace-update-20261016'
PATTERNS = {
    'api-key': re.compile(rb'\bsk-(?:ws-)?[A-Za-z0-9._-]{22,}'),
    'github-token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),
    'bearer-literal': re.compile(rb'(?i)Bearer\s+[a-zA-Z0-9_-]{32,}'),
    'aws-access': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
}


def git_paths(*args):
    raw = subprocess.check_output(['git', *args, '-z'], cwd=ROOT)
    return [p.decode('utf-8') for p in raw.split(b'\0') if p]


def scan_bytes(name, data, findings, depth=0):
    for label, pattern in PATTERNS.items():
        if pattern.search(data):
            findings.append({'path': name, 'type': label})
    if data.startswith(b'PK\x03\x04'):
        if depth >= 5:
            raise ValueError('Archive nesting exceeds scan limit: '+name)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                if not info.is_dir():
                    scan_bytes(name+'!'+info.filename, archive.read(info), findings, depth+1)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    paths = sorted(set(git_paths('ls-files') + git_paths('ls-files', '--others', '--exclude-standard')))
    paths = [p for p in paths if (ROOT/p).is_file()]
    findings, manifest = [], {}
    for relative in paths:
        path = ROOT/relative
        if any(part in ('.git', '.env', '.venv', '.venv-capacity') for part in path.relative_to(ROOT).parts):
            raise ValueError('Unexpected local-private path: '+relative)
        if path.name.endswith('.dpapi') or path.name.startswith('.env.') and path.name != '.env.example':
            raise ValueError('Credential file: '+relative)
        data = path.read_bytes()
        scan_bytes(relative, data, findings)
        manifest[relative] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    (OUT/'credential_scan.json').write_text(json.dumps({'files': len(paths), 'findings': findings}, indent=2), encoding='utf-8')
    if findings:
        print(json.dumps({'blocked': True, 'findings': findings}, ensure_ascii=True))
        raise SystemExit(2)
    archive_path = OUT/'DAFR-workspace-update-20261016.zip'
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    archive_manifest = {'base_commit_at_packaging': head, 'files': manifest,
                        'description': 'Full Git-visible working tree, including uncommitted updates; excludes ignored local files.'}
    manifest_bytes = (json.dumps(archive_manifest, ensure_ascii=False, indent=2)+'\n').encode()
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for relative in paths:
            data = (ROOT/relative).read_bytes()
            assert hashlib.sha256(data).hexdigest() == manifest[relative]['sha256'], relative
            archive.writestr('DAFR-workspace-update-20261016/'+relative, data)
        archive.writestr('DAFR-workspace-update-20261016/WORKSPACE_PACKAGE_MANIFEST.json', manifest_bytes)
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        for relative, entry in manifest.items():
            assert hashlib.sha256(archive.read('DAFR-workspace-update-20261016/'+relative)).hexdigest() == entry['sha256'], relative
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    (OUT/'SHA256SUMS.txt').write_text(checksum+'  '+archive_path.name+'\n', encoding='utf-8')
    (OUT/'package_summary.json').write_text(json.dumps({'files': len(paths), 'bytes': archive_path.stat().st_size,
        'sha256': checksum, 'credentials_found': 0, 'all_entry_hashes_verified': True}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'files': len(paths), 'zip_mb': round(archive_path.stat().st_size/1024**2, 2),
                      'sha256': checksum, 'zip': str(archive_path)}, ensure_ascii=True))


if __name__ == '__main__':
    main()
