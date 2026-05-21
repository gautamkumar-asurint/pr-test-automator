"""Validation tests for PRTestConfig."""

import pytest

from pr_test_automator.config import PRTestConfig


def _valid_kwargs() -> dict:
    return {
        "github_token": "ghp_token",
        "claude_api_key": "sk-ant-key",
        "repo": "owner/repo",
        "repo_path": "/tmp/repo",
    }


def test_valid_config_parses_owner_and_repo() -> None:
    cfg = PRTestConfig(**_valid_kwargs())
    assert cfg.owner == "owner"
    assert cfg.repo_name == "repo"


def test_missing_slash_in_repo_raises() -> None:
    kwargs = _valid_kwargs()
    kwargs["repo"] = "no-slash"
    with pytest.raises(ValueError, match="owner/repo"):
        PRTestConfig(**kwargs)


def test_empty_github_token_raises() -> None:
    kwargs = _valid_kwargs()
    kwargs["github_token"] = ""
    with pytest.raises(ValueError, match="github_token"):
        PRTestConfig(**kwargs)


def test_empty_claude_key_raises() -> None:
    kwargs = _valid_kwargs()
    kwargs["claude_api_key"] = ""
    with pytest.raises(ValueError, match="claude_api_key"):
        PRTestConfig(**kwargs)


def test_negative_retries_raises() -> None:
    kwargs = _valid_kwargs()
    kwargs["max_fix_retries"] = -1
    with pytest.raises(ValueError, match="max_fix_retries"):
        PRTestConfig(**kwargs)


def test_github_headers_contains_bearer_token() -> None:
    cfg = PRTestConfig(**_valid_kwargs())
    headers = cfg.github_headers
    assert headers["Authorization"] == "Bearer ghp_token"
    assert headers["Accept"] == "application/vnd.github.v3+json"


def test_all_test_dirs_merges_base_and_extra() -> None:
    cfg = PRTestConfig(
        **_valid_kwargs(),
        test_dirs=["tests"],
        test_file_extra_dirs=["app/tests"],
    )
    assert cfg.all_test_dirs == ["tests", "app/tests"]
