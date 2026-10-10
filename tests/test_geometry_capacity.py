"""Contracts for the independent simulator and the controlled experiment."""
from copy import deepcopy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from geometry_capacity.scenes import generate
from geometry_capacity.simulator import replay
from geometry_capacity.backends import decide, edit_candidates, repair


class GeometryCapacityContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = generate(groups=6)

    def test_grouped_split_and_complete_counterfactuals(self):
        splits = {s: {c['group_id'] for c in self.cases if c['split'] == s} for s in ('train', 'dev', 'test')}
        self.assertFalse(splits['train'] & splits['dev'] | splits['train'] & splits['test'] | splits['dev'] & splits['test'])
        for group in set.union(*splits.values()):
            self.assertEqual(len([c for c in self.cases if c['group_id'] == group]), 6)
        self.assertEqual(self.cases, generate(groups=6))

    def test_exact_controls_and_maximal_grammar_repair(self):
        for c in self.cases:
            options = list(edit_candidates(c))
            expected = next((q for q in options if replay(c, q)['success']), None)
            self.assertEqual(repair(c, 'full'), expected)
            self.assertEqual(repair(c, 'arithmetic_control'), expected)
            for q in options:
                truth = replay(c, q)
                self.assertTrue(truth['goal_met'])
                self.assertEqual(decide(c, q), truth['safe'])
                self.assertEqual(decide(c, q, 'arithmetic_control'), truth['safe'])

    def test_replay_is_atomic_and_does_not_mutate_input(self):
        for c in self.cases:
            before = deepcopy(c)
            result = replay(c, c['proposal'])
            self.assertEqual(c, before)
            if result['safe']:
                self.assertEqual(result['after']['version'], c['state']['version'] + 1)
            else:
                self.assertEqual(result['after'], c['state'])

    def test_lock_and_throughput_cannot_be_repaired_away(self):
        c = deepcopy(next(c for c in self.cases if c['variant'] == 'locked'))
        bad = c['proposal'][:]
        j = c['goal']['locked'].index(True)
        bad[j] *= .5
        result = replay(c, bad)
        self.assertIn('locked_effect', result['violations'])
        self.assertEqual(result['after'], c['state'])
        self.assertFalse(decide(c, bad))
        c['goal']['locked'] = [False] * 3
        result = replay(c, [0, 0, 0])
        self.assertFalse(result['success'])
        self.assertFalse(decide(c, [0, 0, 0]))


if __name__ == '__main__':
    unittest.main()
