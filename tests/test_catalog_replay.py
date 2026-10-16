"""Replay must preserve schema errors without charging/mutating the world."""
import sys
from pathlib import Path
from copy import deepcopy
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_workflow_catalog_v2 as catalog
from resume_catalog_v2 import replay


class InvalidCommitClient:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools, max_tokens):
        self.calls += 1
        if self.calls == 1:
            return {'role': 'assistant', 'content': '', 'tool_calls': [
                {'id': 'invalid-1', 'type': 'function', 'function': {
                    'name': 'commit_operation', 'arguments': '{}'}}]}, {}
        return {'role': 'assistant', 'content': 'Unable to complete.'}, {}


def make_row(monkeypatch):
    catalog.configure_runner()
    monkeypatch.setattr(catalog.runner, 'WorkflowWorld', catalog.CatalogWorld)
    monkeypatch.setattr(catalog.runner, 'admit', catalog.admit)
    case = catalog.make_pairs()[0][0]
    model = catalog.simple_linear()
    row = catalog.runner.episode(case, 'full', model, InvalidCommitClient())
    return case, model, row


def test_missing_commit_argument_replays_without_world_effect(monkeypatch):
    case, model, row = make_row(monkeypatch)
    assert row['tool_calls'] == row['executed_tool_calls'] == row['blocked_calls'] == 0
    assert not row['task_completed']
    assert row['trace'][0]['results'][0]['response'] == {'error': 'invalid_tool_arguments'}
    replay(case, row, model)


def test_replay_detects_tampered_invalid_call_response(monkeypatch):
    case, model, row = make_row(monkeypatch)
    row = deepcopy(row)
    row['trace'][0]['results'][0]['response'] = {'committed': True}
    with pytest.raises(AssertionError):
        replay(case, row, model)
