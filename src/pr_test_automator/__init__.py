"""PR Test Automator — auto-generate, run, and post pytest tests on GitHub PRs.

A standalone, vendor-neutral pipeline for generating pytest tests for the code
changed in a pull request, running them, fixing failures with Claude, and
posting a result comment back to the PR.

Quickstart:

    import asyncio
    from pr_test_automator import PRTestConfig, PRTestPipeline

    config = PRTestConfig(
        github_token="ghp_...",
        claude_api_key="sk-ant-...",
        repo="owner/repo",
        repo_path="/path/to/checkout",
    )
    result = asyncio.run(PRTestPipeline(config).run(pr_number=42))
    print(result.is_passing)
"""

from pr_test_automator.config import PRTestConfig
from pr_test_automator.models import (
    AffectedFunction,
    ExistingTest,
    GeneratedTest,
    PipelineResult,
    PRFile,
    PRInfo,
    StepOutcome,
    TestRunResult,
)
from pr_test_automator.orchestrator import PRTestPipeline
from pr_test_automator.utils.exceptions import (
    CodeAnalyzerError,
    FailureFixerError,
    PRCommenterError,
    PRReaderError,
    PRTestAutomatorError,
    TestFinderError,
    TestGeneratorError,
    TestPusherError,
    TestRunnerError,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # public API
    "PRTestConfig",
    "PRTestPipeline",
    # models
    "PipelineResult",
    "PRFile",
    "PRInfo",
    "AffectedFunction",
    "ExistingTest",
    "GeneratedTest",
    "TestRunResult",
    "StepOutcome",
    # exceptions
    "PRTestAutomatorError",
    "PRReaderError",
    "CodeAnalyzerError",
    "TestFinderError",
    "TestGeneratorError",
    "TestRunnerError",
    "FailureFixerError",
    "PRCommenterError",
    "TestPusherError",
]
