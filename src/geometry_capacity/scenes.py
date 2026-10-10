"""Generate all scenarios without consulting any decision backend."""
from copy import deepcopy
import math
import random

PROFILES = ('edge_controller', 'rack_controller', 'charging_controller', 'lab_controller')


def generate(groups=90, seed=20261011):
    if groups < 6 or groups % 3:
        raise ValueError('groups must be divisible by three and at least six')
    result = []
    for profile_id, profile in enumerate(PROFILES):
        for i in range(groups):
            rng = random.Random(seed + profile_id * 100000 + i)
            split = 'train' if i < groups // 3 else ('dev' if i < 2 * groups // 3 else 'test')
            group = f'{profile}/{split}/{i:04d}'
            mixing = [[rng.uniform(.03, .3) if row != col else rng.uniform(.65, 1.3)
                       for col in range(3)] for row in range(3)]
            background = [rng.uniform(0, .2) for _ in range(3)]
            prefix = [max(0, x - rng.uniform(.03, .15)) for x in background]
            base_capacity = rng.uniform(.9, 1.3)
            cooling = rng.uniform(0, .7)
            direction = [rng.uniform(.02, 1) for _ in range(3)]
            # Broad interior/exterior candidates and analytically bracketed
            # near-limit candidates are separate cohorts, all retained.
            cohort = ('broad', 'boundary', 'axis_stress')[i % 3]
            if cohort == 'axis_stress':
                direction[rng.randrange(3)] *= 8
            response = [sum(row[j] * direction[j] for j in range(3)) for row in mixing]
            a = sum(v * v for v in response)
            b = 2 * sum(v * old for v, old in zip(response, background))
            c = sum(v * v for v in background) - (base_capacity + cooling) ** 2
            capacity_scale = (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)
            multiplier = rng.uniform(.94, 1.06) if cohort == 'boundary' else rng.uniform(.35, 1.6)
            proposal = [v * capacity_scale * multiplier for v in direction]
            weights = [rng.uniform(.7, 1.3) for _ in range(3)]
            plant = {'mixing': mixing, 'base_capacity': base_capacity, 'ambient': rng.uniform(18, 30),
                     'gain': rng.uniform(3, 12), 'law': 'quadratic'}
            scene = {'group_id': group, 'split': split, 'profile': profile, 'cohort': cohort,
                     'plant': plant, 'state': {'background': background, 'cooling_credit': cooling, 'version': i + 2},
                     'history': {'background_at_planning': prefix}, 'proposal': proposal,
                     'goal': {'throughput_weights': weights, 'minimum_throughput':
                              sum(w * q for w, q in zip(weights, proposal)) * rng.uniform(.45, .8),
                              'caps': proposal[:], 'locked': [False, False, False]},
                     'policy_text': 'Keep simulated peak temperature within the current cooling capacity; '
                                    'preserve required throughput and locked allocations.'}
            for variant in ('natural', 'no_cooling', 'extra_cooling', 'concurrent_load', 'locked', 'linear_control'):
                item = deepcopy(scene)
                item.update(id=f'{group}/{variant}', variant=variant)
                if variant == 'no_cooling':
                    item['state']['cooling_credit'] = 0
                elif variant == 'extra_cooling':
                    item['state']['cooling_credit'] += .35
                elif variant == 'concurrent_load':
                    item['state']['background'] = [v + rng.uniform(.12, .35) for v in background]
                elif variant == 'locked':
                    item['goal']['locked'][rng.randrange(3)] = True
                elif variant == 'linear_control':
                    item['plant']['law'] = 'linear'
                result.append(item)
    return result
