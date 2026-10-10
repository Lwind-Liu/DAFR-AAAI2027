from clafr import FeatureVector, LinearFacet, RiskBudgetCone
from agentdojo.agent_pipeline.clafr_defense import _trusted_authorization_texts


def test_reading_email_does_not_authorize_side_effects():
    for task in ('Summarize this email.', 'Read the message from an unfamiliar sender.',
                 'Email from a stranger: summarize the agenda.'):
        assert _trusted_authorization_texts(task) == ()


def test_communication_verbs_still_authorize_requested_effects():
    for task in ('Email Alice the approved report.', 'Please message Alice about the meeting.',
                 'Read the agenda, then email Alice the summary.'):
        assert _trusted_authorization_texts(task) == (task,)


def test_machine_roundoff_is_not_a_real_linear_violation():
    facet = LinearFacet('boundary', {'u': 1, 's': .55, 'r': -1.05, 'g': -.35,
                                    'c': -.35, 'e': .45}, -.05, '', '')
    vector = FeatureVector.from_mapping({'u':1, 's':1, 'r':1, 'g':1, 'c':.7, 'e':.1})
    assert facet.margin(vector).slack == 0
    outside = FeatureVector.from_mapping({'u':1 + 1e-10, 's':1, 'r':1, 'g':1, 'c':.7, 'e':.1})
    assert facet.margin(outside).slack < 0


def test_cone_uses_the_same_machine_roundoff_policy():
    cone = RiskBudgetCone('boundary', {'r':1}, {}, 1, '', '')
    assert cone.margin(FeatureVector.from_mapping({'r':1+1e-15})).slack == 0
    assert cone.margin(FeatureVector.from_mapping({'r':1+1e-10})).slack < 0
