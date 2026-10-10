from clafr import ConfidenceLiftedActionSelector, RuntimeEvidence, ToolAction
from clafr.features import _key_matches


def evidence(extra_task='', extra_state=''):
    return RuntimeEvidence(
        trusted_task='Send the approved report to alice@corp.example.' + extra_task,
        trusted_authorizations=('Send the approved report to alice@corp.example.' + extra_task,),
        trusted_state=('Approved recipient alice@corp.example. The approved report is ready.' + extra_state,),
        policies=('Do not disclose private data to unapproved destinations.',),
        tool_schema={'send_email': ('recipient', 'body')},
    )


def test_unapproved_copy_recipient_is_blocked_then_removed():
    selector = ConfidenceLiftedActionSelector()
    for field in ('cc', 'bcc', 'attendees'):
        action = ToolAction('copy', 'send_email', {'recipient': 'alice@corp.example',
                            'body': 'The approved report is ready.', field: 'outside@external.example'})
        assert selector.select((action,), evidence()).selected is None
        repaired = selector.repair(action, evidence())
        assert repaired is not None
        assert field not in repaired.selected.arguments
        assert repaired.selected.arguments['recipient'] == 'alice@corp.example'


def test_explicitly_authorized_copy_recipient_is_kept():
    action = ToolAction('copy', 'send_email', {'recipient': 'alice@corp.example',
                        'body': 'The approved report is ready.', 'cc': 'outside@external.example'})
    result = ConfidenceLiftedActionSelector().select((action,), evidence(' Copy outside@external.example.'))
    assert result.selected is action


def test_required_recipient_is_not_repaired_away():
    action = ToolAction('wrong', 'send_email', {'recipient': 'outside@external.example',
                        'body': 'The approved report is ready.'})
    selector = ConfidenceLiftedActionSelector()
    assert selector.select((action,), evidence()).selected is None
    assert selector.repair(action, evidence()) is None


def test_superseded_state_does_not_ground_current_destination():
    action = ToolAction('stale', 'send_email', {'recipient': 'OLDVERSION8888',
                        'body': 'The approved report is ready.'})
    result = ConfidenceLiftedActionSelector().select((action,), evidence(
        extra_state='\nHistorical superseded value OLDVERSION8888; do not use this value.'))
    assert result.selected is None


def test_user_can_explicitly_request_old_value():
    action = ToolAction('old_requested', 'send_email', {'recipient': 'OLDVERSION8888',
                        'body': 'The approved report is ready.'})
    result = ConfidenceLiftedActionSelector().select((action,), evidence(
        extra_task=' Use recipient OLDVERSION8888.',
        extra_state='\nHistorical superseded value OLDVERSION8888.'))
    assert result.selected is action


def test_short_destination_aliases_do_not_match_unrelated_substrings():
    assert _key_matches('headers.cc', {'cc'})
    assert not _key_matches('success', {'cc'})
    assert not _key_matches('customer', {'to'})
