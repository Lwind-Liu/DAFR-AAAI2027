"""Predefined verifier availability scenarios, independent of policy scores."""
import random

from .business_world import AgentWorld as BusinessWorld, build_cases as business_cases


def build_cases(seed=20261026):
    cases = business_cases(4, seed, 'test')
    rng = random.Random(seed + 127)
    scenarios = ('available', 'transient_outage', 'field_unavailable', 'retry_pressure')
    for index, case in enumerate(cases):
        scenario = scenarios[index % len(scenarios)]
        case['verification_service'] = {'scenario': scenario,
            'unavailable_field': rng.choice(case['fields']) if scenario == 'field_unavailable' else None,
            'initial_failed_attempts': {'available': 0, 'transient_outage': 1,
                                        'field_unavailable': 0, 'retry_pressure': 3}[scenario]}
        case['operational_scenario'] = scenario
        case['group_id'] = case['id']
    return cases


class AgentWorld(BusinessWorld):
    def read(self, name, args):
        service = self.case.get('verification_service')
        if name == 'verify_field' and service and self.preflight_attempted and self.verifications < 4:
            unavailable = (service['scenario'] == 'field_unavailable'
                           and args.get('field') == service['unavailable_field'])
            temporary = self.verifications < service['initial_failed_attempts']
            if unavailable or temporary:
                self.verifications += 1
                return {'channel': 'registry', 'verified': False, 'error': 'service_unavailable',
                        'field': args.get('field'), 'retryable': not unavailable}
        return super().read(name, args)
