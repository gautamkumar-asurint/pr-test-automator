"""Command-line entry point: ``python -m pr_test_automator``.

This is the same module invoked by the GitHub Action and by anyone wanting
to run the pipeline from a shell. All inputs are pulled from environment
variables so the Action wrapper can stay declarative.

Required environment variables:
    GITHUB_TOKEN         GitHub PAT or workflow GITHUB_TOKEN.
    ANTHROPIC_API_KEY    Anthropic API key.
    GITHUB_REPOSITORY    GitHub ``owner/repo`` (set automatically by Actions).
    PR_NUMBER            Pull request number to process.

Optional:
    REPO_PATH            Local checkout path (default: current working dir).
    TEST_DIRS            Comma-separated list of test directories.
    SOURCE_ROOT          Restrict analysis to files under this directory.
    PUSH_TEST_COMMIT     "true" to commit generated tests back to the PR.
    MAX_FIX_RETRIES      Override the default fixer-loop retry count.
    MODEL                Override the default Anthropic model id.
    HARD_GATE            "true" to exit non-zero on test failure.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Iterable

from pr_test_automator.config import PRTestConfig
from pr_test_automator.models import PipelineResult
from pr_test_automator.orchestrator import PRTestPipeline


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"ERROR: required env var {name!r} is not set", file=sys.stderr)
        sys.exit(2)
    return value


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _csv(name: str) -> list[str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return []
    return [piece.strip() for piece in raw.split(",") if piece.strip()]


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"ERROR: env var {name!r} must be an integer, got {raw!r}",
              file=sys.stderr)
        sys.exit(2)


def _build_config() -> tuple[PRTestConfig, int, bool]:
    """Translate env vars into a PRTestConfig + pr_number + hard-gate flag."""
    github_token = _require("GITHUB_TOKEN")
    claude_api_key = _require("ANTHROPIC_API_KEY")
    repo = _require("GITHUB_REPOSITORY")
    pr_number_raw = _require("PR_NUMBER")

    try:
        pr_number = int(pr_number_raw)
    except ValueError:
        print(f"ERROR: PR_NUMBER must be an integer, got {pr_number_raw!r}",
              file=sys.stderr)
        sys.exit(2)

    test_dirs = _csv("TEST_DIRS") or ["tests"]

    config = PRTestConfig(
        github_token=github_token,
        claude_api_key=claude_api_key,
        repo=repo,
        repo_path=os.environ.get("REPO_PATH", os.getcwd()),
        test_dirs=test_dirs,
        source_root=os.environ.get("SOURCE_ROOT") or None,
        push_test_commit=_bool("PUSH_TEST_COMMIT", False),
        max_fix_retries=_int("MAX_FIX_RETRIES", 3),
        model=os.environ.get("MODEL") or PRTestConfig.__dataclass_fields__[
            "model"
        ].default,
    )

    return config, pr_number, _bool("HARD_GATE", False)


def _print_summary(result: PipelineResult, hard_gate: bool) -> int:
    """Print a human-readable summary; return the desired exit code."""
    status = "PASS" if result.is_passing else "FAIL"
    print()
    print("=" * 55)
    print(f"PR #{result.pr_number} — {status}")
    print(f"  Files changed      : {result.files_changed}")
    print(f"  Functions analyzed : {result.functions_affected}")
    print(f"  Tests generated    : {result.tests_generated}")
    if result.test_result:
        r = result.test_result
        print(f"  Tests passed       : {r.passed}")
        print(f"  Tests failed       : {r.failed}")
        print(f"  Tests errored      : {r.errors}")
    if result.comment_url:
        print(f"  PR comment         : {result.comment_url}")
    if result.commit_sha:
        print(f"  Commit SHA         : {result.commit_sha}")
    print("=" * 55)
    print("Step-by-step:")
    for step in result.steps:
        icon = "✓" if step.success else "✗"
        print(f"  {icon} {step.step}: {step.message}")

    if hard_gate and not result.is_passing:
        return 1
    return 0


async def _main_async(config: PRTestConfig, pr_number: int) -> PipelineResult:
    return await PRTestPipeline(config).run(pr_number)


def main(argv: Iterable[str] | None = None) -> int:  # noqa: ARG001
    config, pr_number, hard_gate = _build_config()
    print(f"Running PR Test Automator for PR #{pr_number} in {config.repo} ...")
    result = asyncio.run(_main_async(config, pr_number))
    return _print_summary(result, hard_gate)


if __name__ == "__main__":
    sys.exit(main())
