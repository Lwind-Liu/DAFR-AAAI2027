"""Probe model access once, then resume the frozen v11 comparison."""
import argparse
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
import sys

import run_catalog_fixed104_adapter_v11_full as frozen
from flash_catalog_client import CatalogClient, ProviderError


def prepare_verified_catalog():
    """Initialize the frozen world while allowing the recorded transport fix."""
    catalog = frozen.baseline.catalog
    protocol = json.loads((catalog.OUT / 'protocol.json').read_text(encoding='utf-8'))
    allowed_client = 'a8765af5ed157dd9df64561aa0b7334dd311a0ce5f533cb8bf1f4b52f03caf35'
    for relative, expected in protocol['source_sha256'].items():
        path = catalog.ROOT / relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if path.name == 'flash_catalog_client.py':
            assert actual in (expected, allowed_client), 'Unrecognized API client change'
        else:
            assert actual == expected, f'Frozen source changed: {relative}'
    catalog.configure_runner()
    catalog.runner.WorkflowWorld = catalog.CatalogWorld
    catalog.runner.admit = catalog.admit
    pairs, model = catalog.make_pairs(), catalog.simple_linear()
    content = ''.join(json.dumps(c, sort_keys=True) + '\n' for pair in pairs for c in pair)
    assert (catalog.DATA / 'cases.jsonl').read_text(encoding='utf-8') == content
    assert hashlib.sha256(content.encode()).hexdigest() == protocol['data_sha256']
    assert model == protocol['linear']
    assert catalog.runner.SYSTEM == protocol['system']
    assert catalog.runner.schemas() == protocol['tools']
    assert [catalog.preflight(c, model) for pair in pairs for c in pair] == protocol['reference_checks']
    assert catalog.capacity_check(pairs) == protocol['capacity_check']
    return pairs, model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--additional-budget-cny', type=float, default=35.,
        help='Additional estimated request-cost ceiling; previous usage remains intact.')
    args = parser.parse_args()
    assert args.additional_budget_cny > 0 and args.workers > 0
    folder = frozen.OUT
    protocol = json.loads((folder / 'protocol.json').read_text())
    rows = frozen.read_valid(folder / 'rows.jsonl')
    dataset = frozen.ROOT / 'data/workflow_catalog_104/cases.jsonl'
    assert hashlib.sha256(dataset.read_bytes()).hexdigest() == protocol['data_sha256']
    assert hashlib.sha256(Path(frozen.baseline.__file__).read_bytes()).hexdigest() == protocol['adapter_sha256']
    assert hashlib.sha256(Path(frozen.__file__).read_bytes()).hexdigest() == protocol['runner_sha256']
    completed = {(r['id'], r['arm']) for r in rows}
    expected = {(cid, method) for cid in protocol['ids'] for method in protocol['methods']}
    assert len(completed) == len(rows) and completed <= expected
    missing = expected - completed
    usage = json.loads((folder / 'usage.json').read_text())
    ceiling = usage['estimated_cost_cny'] + args.additional_budget_cny
    print(json.dumps({'valid_episodes': len(rows), 'remaining_episodes': len(missing),
        'remaining_by_method': dict(Counter(method for _, method in missing)),
        'model': protocol['model'], 'additional_cost_ceiling_cny': args.additional_budget_cny}), flush=True)
    if args.dry_run or not missing:
        prepare_verified_catalog()
        return
    key = sys.stdin.readline().strip()
    assert key, 'Provide the API key through stdin.'
    health = folder / 'access_probe'
    health.mkdir(exist_ok=True)
    probe_usage = json.loads((health / 'usage.json').read_text()) if (health / 'usage.json').exists() else {}
    probe = CatalogClient(key, health, probe_usage.get('estimated_cost_cny', 0.) + 1.)
    try:
        probe.chat([{'role': 'user', 'content': 'Reply OK.'}], max_tokens=16)
    except ProviderError as error:
        print(json.dumps({'resumed': False, 'reason': str(error),
            'accepted_results_unchanged': True}), flush=True)
        raise SystemExit(2)
    # The original runner retains its frozen protocol and skips every completed
    # case/method pair. Accepted model payloads and outcome evaluators are intact.
    sys.stdin = io.StringIO(key + '\n')
    frozen.baseline.catalog.prepare = prepare_verified_catalog
    sys.argv = [frozen.__file__, '--budget-cny', str(ceiling), '--workers', str(args.workers)]
    frozen.main()


if __name__ == '__main__':
    main()
