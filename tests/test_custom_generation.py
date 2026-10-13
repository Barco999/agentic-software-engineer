"""Static, no-execution tests for new AI file-proposal support."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from agents.testing import inspect_generated_sources
from orchestration.policies import PolicyViolation, validate_proposal
from orchestration.tools import apply_proposal


def sample(files=None):
    return {
        'operations': [{'kind': 'generate_files', 'rationale': 'Build requested app',
                        'files': files or [{'path': 'app/main.py', 'content': 'value = 42\n'}]}],
        'requirement_ids': ['REQ'], 'decision_ids': [], 'summary': 'Custom project',
    }


def test_dynamic_proposal_requires_explicit_custom_mode():
    with pytest.raises(PolicyViolation):
        validate_proposal('greenfield', sample())
    validate_proposal('greenfield', sample(), custom_generation=True)


def test_generated_file_paths_and_syntax_rejected():
    for name in ('../outside.py', 'app/../../foo.py', '.env', 'app/.hidden.py', 'app\\foo.py', 'app/code.exe'):
        with pytest.raises((PolicyViolation, ValidationError)):
            validate_proposal('greenfield', sample([{'path': name, 'content': 'x = 1'}]), custom_generation=True)
    with pytest.raises(PolicyViolation):
        validate_proposal('greenfield', sample([{'path': 'app/main.py', 'content': 'def broken(\n'}]), custom_generation=True)


def test_generated_file_write_and_static_check(tmp_path):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    ledger = apply_proposal('greenfield', workspace, tmp_path, sample(), custom_generation=True)
    assert len(ledger) == 1
    assert ledger[0]['source'] == 'human_approved_model_file'
    assert (workspace / 'app/main.py').read_text() == 'value = 42\n'
    report = inspect_generated_sources(workspace, tmp_path / 'report')
    assert report['success'] and report['passed'] == 1
    assert report['runtime_tests_executed'] is False
    assert report['requires_manual_sandbox_test'] is True


def test_existing_predefined_operation_still_allowed():
    proposal = {'operations': [{'kind': 'bootstrap_reference', 'rationale': 'trusted'}],
                'requirement_ids': ['REQ'], 'decision_ids': [], 'summary': 'baseline'}
    assert validate_proposal('greenfield', proposal).operations[0].kind == 'bootstrap_reference'
