"""Step 5: Run generated tests with pytest and parse results."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile

from pr_test_automator._logging import get_logger
from pr_test_automator.config import PRTestConfig
from pr_test_automator.models import GeneratedTest, TestRunResult
from pr_test_automator.utils.exceptions import TestRunnerError

logger = get_logger(__name__)

_SUMMARY_RE = re.compile(
    r"(?P<count>\d+)\s+(?P<kind>passed|failed|error|errors)",
    re.IGNORECASE,
)
_FAILED_ID_RE = re.compile(r"FAILED\s+(\S+)")
_TIMEOUT_SECONDS = 120


class TestRunner:
    """Writes generated tests to a temp directory and executes pytest."""

    def __init__(self, config: PRTestConfig) -> None:
        self._config = config

    def run(self, tests: list[GeneratedTest]) -> TestRunResult:
        if not tests:
            return TestRunResult(
                passed=0,
                failed=0,
                errors=0,
                total=0,
                output="No tests to run.",
                failed_test_ids=[],
                is_passing=True,
            )

        with tempfile.TemporaryDirectory(prefix="pr_tests_") as tmp:
            test_files = self._write_tests(tests, tmp)
            output, return_code = self._run_pytest(test_files)

        result = self._parse_output(output, return_code)
        logger.info(
            "pytest finished",
            extra={
                "passed": result.passed,
                "failed": result.failed,
                "errors": result.errors,
            },
        )
        return result

    def _write_tests(
        self,
        tests: list[GeneratedTest],
        directory: str,
    ) -> list[str]:
        paths: list[str] = []
        for gen in tests:
            base = os.path.basename(gen.test_file_path)
            dest = os.path.join(directory, base)
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(gen.content)
            paths.append(dest)
            logger.info("wrote temp test file", extra={"path": dest})
        return paths

    def _run_pytest(self, test_files: list[str]) -> tuple[str, int]:
        cmd = [
            "python",
            "-m",
            "pytest",
            "--tb=short",
            "--no-header",
            "-q",
            *test_files,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self._config.repo_path,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
            return proc.stdout + proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            raise TestRunnerError(
                f"pytest timed out after {_TIMEOUT_SECONDS}s"
            ) from exc
        except FileNotFoundError as exc:
            raise TestRunnerError(
                f"pytest not found — is it installed? {exc}"
            ) from exc

    def _parse_output(self, output: str, return_code: int) -> TestRunResult:
        passed = failed = errors = 0
        for match in _SUMMARY_RE.finditer(output):
            count = int(match.group("count"))
            kind = match.group("kind").lower()
            if kind == "passed":
                passed = count
            elif kind == "failed":
                failed = count
            elif kind in {"error", "errors"}:
                errors = count

        failed_ids = _FAILED_ID_RE.findall(output)

        return TestRunResult(
            passed=passed,
            failed=failed,
            errors=errors,
            total=passed + failed + errors,
            output=output,
            failed_test_ids=failed_ids,
            is_passing=return_code == 0,
        )
