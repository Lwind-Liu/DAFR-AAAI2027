from copy import deepcopy
import unittest
from relational_dafr import decide,features,surface_risk,repair
from relational_dafr.scenarios import generate
from relational_dafr.worlds import expected_loss,safe
from relational_dafr.controller import risk_interval


class RelationalControllerContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.cases=generate(per_domain=12)

    def test_surface_matches_independent_execution_worlds(self):
        for c in self.cases:
            self.assertAlmostEqual(surface_risk(c),expected_loss(c),places=12)
            self.assertEqual(decide(c),safe(c))

    def test_foreign_stale_and_other_effect_grants_do_not_authorize(self):
        bygroup={}
        for c in self.cases:bygroup.setdefault(c['group'],{})[c['variant']]=c
        for variants in bygroup.values():
            for v in ('unrelated_grant','stale_grant','foreign_grant'):
                self.assertAlmostEqual(surface_risk(variants[v]),surface_risk(variants['unverified']))

    def test_duplicate_grants_do_not_supply_extra_credit(self):
        c=deepcopy(next(c for c in self.cases if c['variant']=='one_exact_grant'))
        before=surface_risk(c)
        c['grants']*=10
        self.assertEqual(before,surface_risk(c))

    def test_domain_and_tool_labels_do_not_change_decisions(self):
        for original in self.cases[:30]:
            renamed=deepcopy(original)
            renamed['domain']='previously_unseen_tool_family'
            self.assertEqual(decide(original),decide(renamed))
            self.assertEqual(features(original).tolist(),features(renamed).tolist())

    def test_verification_plans_safe_and_do_not_mutate_inputs(self):
        for c in self.cases:
            old=deepcopy(c)
            label,plan=repair(c)
            self.assertIsNotNone(plan)
            self.assertTrue(safe(plan))
            self.assertEqual(c,old)
            self.assertEqual(plan['action'],old['action'])

    def test_shared_primitive_event_is_not_counted_twice(self):
        c=deepcopy(self.cases[0])
        c['grants']=[]
        c['events']={'e0':{'probability':.5},'e1':{'probability':.5},'e2':{'probability':.5}}
        c['paths']=[{'field':'payee','events':['e0','e1']}, {'field':'amount','events':['e0','e2']}]
        c['severity']=1
        self.assertAlmostEqual(surface_risk(c),.375)
        self.assertAlmostEqual(expected_loss(c),.375)
        self.assertAlmostEqual(surface_risk(c,'independent_paths'),.4375)

    def test_probability_intervals_bound_every_checked_execution_world_model(self):
        for c in self.cases:
            low,high=risk_interval(c,.1)
            self.assertLessEqual(low-1e-12,expected_loss(c))
            self.assertGreaterEqual(high+1e-12,expected_loss(c))

    def test_relabelled_fields_effects_and_event_ids_keep_surface_unchanged(self):
        for c in self.cases[:20]:
            r=deepcopy(c)
            r['action']['effect']='new_effect'
            r['action']['arguments']={'renamed_'+k:v for k,v in c['action']['arguments'].items()}
            r['events']={'renamed_'+k:v for k,v in c['events'].items()}
            for p in r['paths']:
                p['field']='renamed_'+p['field']
                p['events']=['renamed_'+e for e in p['events']]
            for g in r['grants']:
                g['field']='renamed_'+g['field']
                if g['effect']==c['action']['effect']:
                    g['effect']='new_effect'
            self.assertAlmostEqual(surface_risk(c),surface_risk(r))

    def test_invalid_probabilities_and_missing_graph_nodes_are_rejected(self):
        for value in (-.1,1.1,float('nan'),float('inf')):
            c=deepcopy(self.cases[0])
            c['events']['e0']['probability']=value
            with self.assertRaises(ValueError):surface_risk(c)
        c=deepcopy(self.cases[0])
        c['paths'][0]['events'].append('missing')
        with self.assertRaises(ValueError):surface_risk(c)


if __name__=='__main__':unittest.main()
