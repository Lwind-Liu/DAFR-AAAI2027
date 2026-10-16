"""Predeclared oracle-boundary stress distribution, without baseline filtering."""
from collections import defaultdict
import random

from .business_world import AgentWorld, build_cases as business_cases, schemas
from .worlds import expected_loss


def build_cases(per_domain=16, seed=20261023, split='test'):
    cases = business_cases(per_domain, seed, split)
    rng = random.Random(seed + 4041)
    seen = defaultdict(int)
    for case in cases:
        index = seen[case['domain']]
        seen[case['domain']] += 1
        if index % 4 == 0:
            case['stress_stratum'] = 'broad'
        else:
            case['stress_stratum'] = 'boundary'
            # Budget is set by the independent event-world oracle. No fitted
            # weight, controller score or previously observed winner is read.
            ratio = rng.uniform(.9, 1.1)
            risk = expected_loss(case['scene'])
            case['scene']['budget'] = risk / ratio
        case['oracle_risk_to_budget'] = expected_loss(case['scene']) / case['scene']['budget']
    return cases
