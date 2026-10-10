from copy import deepcopy

from relational_dafr.episodes import build_episodes, EpisodeRuntime
from relational_dafr.pipeline import extract_context, run_episode, upper_context
from relational_dafr.controller import surface_risk
from relational_dafr.worlds import expected_loss


def episodes():
    return build_episodes(per_domain=8)


def test_public_inputs_hide_world_ledger_and_labels():
    for episode in episodes():
        public = episode['input']
        assert set(public) == {'id', 'action', 'policy', 'records'}
        assert 'safe' not in public and 'verification_ledger' not in public
        for record in public['records']:
            if record['body']['kind'] == 'current_measurements':
                for value in record['body']['events'].values():
                    assert set(value) == {'estimate', 'radius'}


def test_rounded_upper_bound_covers_independent_world():
    for episode in episodes():
        upper = upper_context(extract_context(episode['input']))
        assert surface_risk(upper) + 1e-12 >= expected_loss(episode['hidden_world'])


def test_full_execution_is_safe_and_budgeted_with_actual_replies():
    for episode in episodes():
        before = deepcopy(episode)
        runtime = EpisodeRuntime(episode)
        result = run_episode(episode['input'], runtime)
        assert result['queries'] <= episode['input']['policy']['verification_query_budget']
        assert not result['committed'] or result['policy_safe']
        assert len(runtime.executions) == int(result['committed'])
        assert episode == before


def test_denied_verification_cannot_create_grants_or_repair():
    count = 0
    for episode in episodes():
        e = deepcopy(episode)
        e['verification_ledger'] = []
        e['input']['policy']['verification_query_budget'] = 5
        runtime = EpisodeRuntime(e)
        result = run_episode(e['input'], runtime)
        if not result['initial_allowed']:
            count += 1
            assert not result['committed']
            assert runtime.grants == e['hidden_world']['grants']
    assert count > 0


def test_no_repair_makes_no_verification_calls():
    for e in episodes():
        result = run_episode(e['input'], EpisodeRuntime(e), repair=False)
        assert result['queries'] == 0
        assert result['committed'] == result['initial_allowed']


def test_foreign_claim_only_enters_when_projection_is_disabled():
    for e in episodes():
        if e['variant'] == 'foreign_grant':
            assert not extract_context(e['input'])['grants']
            assert len(extract_context(e['input'], projection=False)['grants']) == 1


def test_current_revision_and_snapshot_are_distinct():
    for e in episodes():
        assert extract_context(e['input'])['revision'] == 2
        assert extract_context(e['input'], dynamic=False)['revision'] == 1


def test_runtime_execution_does_not_silently_block_unsafe_actions():
    witnesses = 0
    for e in episodes():
        result = EpisodeRuntime(e).execute(e['input']['action'])
        assert result['committed']
        assert result['expected_unauthorized_loss'] == expected_loss(e['hidden_world'])
        witnesses += not result['policy_safe']
    assert witnesses > 0
