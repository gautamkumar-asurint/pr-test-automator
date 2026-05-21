"""Step 3: Locate existing test files for the affected source files."""

from __future__ import annotations

import os

from pr_test_automator._logging import get_logger
from pr_test_automator.config import PRTestConfig
from pr_test_automator.models import AffectedFunction, ExistingTest

logger = get_logger(__name__)


class TestFinder:
    """Discovers existing pytest files that correspond to changed sources."""

    def __init__(self, config: PRTestConfig) -> None:
        self._config = config

    def find(self, affected: list[AffectedFunction]) -> list[ExistingTest]:
        """Return existing test files for each unique source file."""
        source_files = {fn.file_path for fn in affected}
        results: list[ExistingTest] = []

        for source_path in source_files:
            test_file = self._find_test_file(source_path)
            if test_file:
                results.append(test_file)
            else:
                logger.info("no existing tests", extra={"source": source_path})

        return results

    def _find_test_file(self, source_path: str) -> ExistingTest | None:
        stem = os.path.splitext(os.path.basename(source_path))[0]
        for candidate in self._candidate_paths(stem, source_path):
            full = os.path.join(self._config.repo_path, candidate)
            if os.path.isfile(full):
                logger.info("found existing tests", extra={"path": candidate})
                return ExistingTest(
                    test_file_path=candidate,
                    source_file_path=source_path,
                    content=self._read(full),
                )
        return None

    def _candidate_paths(self, stem: str, source_path: str) -> list[str]:
        test_name = f"test_{stem}.py"
        candidates: list[str] = []

        for test_dir in self._config.all_test_dirs:
            candidates.append(os.path.join(test_dir, test_name))

        source_dir = os.path.dirname(source_path)
        candidates.append(os.path.join(source_dir, test_name))
        candidates.append(os.path.join(source_dir, "..", "tests", test_name))
        return candidates

    @staticmethod
    def _read(path: str) -> str:
        with open(path, encoding="utf-8") as fh:
            return fh.read()

def suggest_test_path(
    self,
    source_path: str,
    existing: ExistingTest | None = None,
) -> str:
    """Return the preferred path for a NEW test file for ``source_path``.

    If existing tests for this source already exist, write to a
    ``test_<stem>_generated.py`` file so we never overwrite the human's tests.
    """
    stem = os.path.splitext(os.path.basename(source_path))[0]
    suffix = "_generated" if existing else ""
    test_name = f"test_{stem}{suffix}.py"
    preferred_dir = (
        self._config.test_dirs[0] if self._config.test_dirs else "tests"
    )
    return os.path.join(preferred_dir, test_name)