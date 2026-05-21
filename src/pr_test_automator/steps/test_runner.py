"""Step 5: Run generated tests with pytest and parse results."""

from __future__ import annotations

import contextlib
import os
import re
import subprocess

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
_TEMP_PREFIX = "_pr_automator_"


class TestRunner:
    """Writes generated tests into the consumer's test directory, runs pytest,
    then cleans up — so pytest config (markers, conftest, fixtures) applies.
    """

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

        target_dir = self._target_test_dir()
        os.makedirs(target_dir, exist_ok=True)

        written: list[str] = []
        try:
            written = self._write_tests(tests, target_dir)
            output, return_code = self._run_pytest(written)
        finally:
            self._cleanup(written)

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

    def _target_test_dir(self) -> str:
        """Choose where to drop the generated tests inside the repo.

        Uses the first entry in test_dirs; falls back to 'tests' if none.
        """
        first = (
            self._config.test_dirs[0] if self._config.test_dirs else "tests"
        )
        return os.path.join(self._config.repo_path, first)

    def _write_tests(
        self,
        tests: list[GeneratedTest],
        target_dir: str,
    ) -> list[str]:
        """Write each generated test file with a prefix to prevent collisions.

        Returns the list of absolute paths actually written.
        """
        written: list[str] = []
        for gen in tests:
            base = os.path.basename(gen.test_file_path)
            safe_name = f"{_TEMP_PREFIX}{base}"
            dest = os.path.join(target_dir, safe_name)

            # Defensive: refuse to overwrite a file that's somehow already there.
            if os.path.exists(dest):
                logger.warning(
                    "skipping write — temp file already exists",
                    extra={"path": dest},
                )
                continue

            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(gen.content)
            written.append(dest)
            logger.info("wrote ephemeral test file", extra={"path": dest})
        return written

    def _cleanup(self, paths: list[str]) -> None:
        """Best-effort removal of files we wrote. Never raises."""
        for path in paths:
            with contextlib.suppress(OSError):
                os.remove(path)
                logger.info("cleaned up ephemeral test", extra={"path": path})

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