"""Run the PR Test Automator locally against a real GitHub PR.

Usage:
    export GITHUB_TOKEN=ghp_...
    export ANTHROPIC_API_KEY=sk-ant-...
    python examples/run_locally.py <owner/repo> <pr_number>
"""

from __future__ import annotations

import asyncio
import os
import sys

from pr_test_automator import PRTestConfig, PRTestPipeline


def _require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        print(f"ERROR: {name} environment variable is not set", file=sys.stderr)
        sys.exit(1)
    return value


async def main(repo: str, pr_number: int) -> None:
    config = PRTestConfig(
        github_token=_require_env("GITHUB_TOKEN"),
        claude_api_key=_require_env("ANTHROPIC_API_KEY"),
        repo=repo,
        repo_path=os.getcwd(),
        # Match your project layout:
        test_dirs=["tests"],
        # Optional: limit analysis to one subtree:
        # source_root="src",
        push_test_commit=False,
        max_fix_retries=3,
    )

    print(f"\nRunning PR Test Automator for {repo} PR #{pr_number} ...\n")
    result = await PRTestPipeline(config).run(pr_number)

    print(f"\nPR #{result.pr_number} — {'PASS ✓' if result.is_passing else 'FAIL ✗'}")
    print(f"  Functions analyzed : {result.functions_affected}")
    print(f"  Tests generated    : {result.tests_generated}")
    if result.test_result:
        r = result.test_result
        print(f"  Tests passed       : {r.passed}")
        print(f"  Tests failed       : {r.failed}")
        print(f"  Tests errored      : {r.errors}")
    if result.comment_url:
        print(f"  PR comment         : {result.comment_url}")

    for step in result.steps:
        icon = "✓" if step.success else "✗"
        print(f"  {icon} {step.step}: {step.message}")


if __name__ == "__main__":
    if len(sys.argv) != 3 or not sys.argv[2].isdigit():
        print(f"Usage: python {sys.argv[0]} <owner/repo> <pr_number>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], int(sys.argv[2])))
