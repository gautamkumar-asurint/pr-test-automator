"""Main pipeline orchestrator — coordinates all steps."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from pr_test_automator._logging import get_logger
from pr_test_automator.config import PRTestConfig
from pr_test_automator.models import (
    GeneratedTest,
    PipelineResult,
    StepOutcome,
    TestRunResult,
)
from pr_test_automator.steps import (
    CodeAnalyzer,
    FailureFixer,
    PRCommenter,
    PRReader,
    TestFinder,
    TestGenerator,
    TestPusher,
    TestRunner,
)
from pr_test_automator.utils.exceptions import PRTestAutomatorError

logger = get_logger(__name__)

_EMPTY_RUN = TestRunResult(
    passed=0,
    failed=0,
    errors=0,
    total=0,
    output="No tests generated.",
    failed_test_ids=[],
    is_passing=True,
)


class PRTestPipeline:
    """Orchestrates the full PR test automation pipeline.

    Usage:
        config = PRTestConfig(
            github_token="ghp_...",
            claude_api_key="sk-ant-...",
            repo="owner/repo",
            repo_path="/path/to/local/checkout",
            push_test_commit=True,
        )
        result = await PRTestPipeline(config).run(pr_number=42)
    """

    def __init__(self, config: PRTestConfig) -> None:
        self._config = config
        self._reader = PRReader(config)
        self._analyzer = CodeAnalyzer(config)
        self._finder = TestFinder(config)
        self._runner = TestRunner(config)
        self._generator = TestGenerator(config, self._finder)
        self._fixer = FailureFixer(config, self._runner)
        self._commenter = PRCommenter(config)
        self._pusher = TestPusher(config)

    async def run(self, pr_number: int) -> PipelineResult:
        """Execute all pipeline steps and return an aggregated result."""
        steps: list[StepOutcome] = []
        tests: list[GeneratedTest] = []
        test_result: TestRunResult = _EMPTY_RUN
        comment_url: str | None = None
        commit_sha: str | None = None
        fix_attempts = 0
        files_changed = 0

        logger.info(
            "pipeline starting",
            extra={"pr": pr_number, "repo": self._config.repo},
        )

        # Step 1 — read PR
        pr_info, step1 = await self._step("pr_reader", self._reader.read(pr_number))
        steps.append(step1)
        if not step1.success or pr_info is None:
            return self._build_result(
                pr_number, steps, tests, test_result, comment_url, commit_sha,
                files_changed,
            )
        files_changed = len(pr_info.files)

        # Step 2 — analyze code
        affected, step2 = self._sync_step(
            "code_analyzer",
            lambda: self._analyzer.analyze(pr_info.files),
        )
        steps.append(step2)

        if not affected:
            logger.info("no Python functions affected — pipeline complete")
            return self._build_result(
                pr_number, steps, tests, test_result, comment_url, commit_sha,
                files_changed,
            )

        # Step 3 — find existing tests
        existing_tests, step3 = self._sync_step(
            "test_finder",
            lambda: self._finder.find(affected),
        )
        steps.append(step3)

        # Step 4 — generate tests
        tests, step4 = await self._step(
            "test_generator",
            self._generator.generate(affected, existing_tests or []),
        )
        steps.append(step4)
        if not step4.success or not tests:
            return self._build_result(
                pr_number, steps, tests, test_result, comment_url, commit_sha,
                files_changed,
            )

        # Step 5 — run tests
        test_result, step5 = self._sync_step(
            "test_runner",
            lambda: self._runner.run(tests),
        )
        steps.append(step5)

        # Step 6 — fix failures (if any)
        if test_result and not test_result.is_passing:
            fixed, step6 = self._sync_step(
                "failure_fixer",
                lambda: self._fixer.fix(tests, test_result),
            )
            if fixed is not None:
                tests, test_result = fixed
            fix_attempts = self._config.max_fix_retries
            steps.append(step6)

        # Step 7 — post PR comment
        comment_url, step7 = await self._step(
            "pr_commenter",
            self._commenter.post(pr_info, tests, test_result, fix_attempts),
        )
        steps.append(step7)

        # Step 8 — push test commit (optional)
        if self._config.push_test_commit:
            commit_sha, step8 = self._sync_step(
                "test_pusher",
                lambda: self._pusher.push(tests, pr_info),
            )
            steps.append(step8)

        logger.info(
            "pipeline complete",
            extra={"pr": pr_number, "is_passing": test_result.is_passing},
        )
        return self._build_result(
            pr_number, steps, tests, test_result, comment_url, commit_sha,
            files_changed,
        )

    async def _step(
        self, name: str, coro: Awaitable[Any]
    ) -> tuple[Any, StepOutcome]:
        try:
            result = await coro
            return result, StepOutcome(
                step=name,
                success=True,
                message=f"{name} completed successfully",
            )
        except PRTestAutomatorError as exc:
            logger.error(f"step {name} failed: {exc}")
            return None, StepOutcome(step=name, success=False, message=str(exc))

    def _sync_step(
        self, name: str, fn: Callable[[], Any]
    ) -> tuple[Any, StepOutcome]:
        try:
            result = fn()
            return result, StepOutcome(
                step=name,
                success=True,
                message=f"{name} completed successfully",
            )
        except PRTestAutomatorError as exc:
            logger.error(f"step {name} failed: {exc}")
            return None, StepOutcome(step=name, success=False, message=str(exc))

    @staticmethod
    def _build_result(
        pr_number: int,
        steps: list[StepOutcome],
        tests: list[GeneratedTest],
        test_result: TestRunResult,
        comment_url: str | None,
        commit_sha: str | None,
        files_changed: int,
    ) -> PipelineResult:
        return PipelineResult(
            pr_number=pr_number,
            repo="",  # filled in by caller wrapper if needed
            files_changed=files_changed,
            functions_affected=sum(len(t.covered_functions) for t in (tests or [])),
            tests_generated=len(tests or []),
            test_result=test_result,
            comment_url=comment_url,
            commit_sha=commit_sha,
            steps=steps,
            is_passing=test_result.is_passing,
        )
