"""Targeted regression neighbors of seven observed affine-baseline failures.

This intentionally conditions on known failures. It must be reported separately
from representative or independently sampled main-test performance.
"""
from copy import deepcopy
from pathlib import Path
import json
import random

from .business_world import AgentWorld, build_cases as business_cases, schemas

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / 'results/summaries/flash_business_geometry_test_v1'


def build_cases(per_domain=4, seed=20261024, split='test'):
    if split != 'test':
        return business_cases(per_domain, seed, split)
    original = {c['id']: c for c in map(json.loads,
        (ROOT / 'data/flash_business_geometry_test_v1/test.jsonl').read_text().splitlines())}
    failures = [r for r in map(json.loads, (REFERENCE / 'rows.jsonl').read_text().splitlines())
                if r['arm'] == 'simple_linear' and r['unsafe_commit']]
    assert len(failures) == 7
    failures.sort(key=lambda r: r['id'])
    pool = business_cases(max(48, 7 * per_domain * 3), seed, 'test')
    used = set()
    rng = random.Random(seed + 7001)
    cases = []
    for failure in failures:
        anchor = original[failure['id']]
        for neighbor_index in range(per_domain):
            fresh = next(c for c in pool if c['domain'] == anchor['domain']
                         and c['variant'] == anchor['variant'] and c['id'] not in used)
            used.add(fresh['id'])
            case = deepcopy(fresh)
            case['graph_family'] = anchor['graph_family']
            case['scene']['paths'] = deepcopy(anchor['scene']['paths'])
            case['scene']['events'] = deepcopy(anchor['scene']['events'])
            for event in case['scene']['events'].values():
                event['probability'] = round(max(.001, min(.999,
                    event['probability'] + rng.uniform(-.015, .015))), 6)
            case['scene']['budget'] = round(anchor['scene']['budget'] * rng.uniform(.97, 1.03), 6)
            case['ancestor_id'] = anchor['id']
            case['neighbor_index'] = neighbor_index
            case['targeted_regression'] = True
            cases.append(case)
    return cases
