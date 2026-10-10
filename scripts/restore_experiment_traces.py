"""Restore versioned large JSONL traces and verify their SHA-256 checksums."""

import gzip
import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    manifest = root / "results/summaries/trace_archives.json"
    for entry in json.loads(manifest.read_text(encoding="utf-8")):
        target = root / entry["path"]
        archive = root / entry["archive"]
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError(f"Existing trace differs; refusing to overwrite: {target}")
        else:
            payload = gzip.decompress(archive.read_bytes())
            if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                raise ValueError(f"Archive checksum mismatch: {archive}")
            target.write_bytes(payload)
        print(f"Verified: {entry['path']}")


if __name__ == "__main__":
    main()
