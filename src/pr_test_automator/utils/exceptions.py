"""Custom exception classes for the PR Test Automator."""

from __future__ import annotations


class PRTestAutomatorError(Exception):
    """Base exception for all PR Test Automator errors."""

    def __init__(self, message: str, step: str = "unknown") -> None:
        self.step = step
        super().__init__(message)


class PRReaderError(PRTestAutomatorError):
    """Raised when reading PR data from GitHub fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, step="pr_reader")


class CodeAnalyzerError(PRTestAutomatorError):
    """Raised when AST analysis of changed files fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, step="code_analyzer")


class TestFinderError(PRTestAutomatorError):
    """Raised when locating existing test files fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, step="test_finder")


class TestGeneratorError(PRTestAutomatorError):
    """Raised when Claude-based test generation fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, step="test_generator")


class TestRunnerError(PRTestAutomatorError):
    """Raised when executing pytest fails unexpectedly."""

    def __init__(self, message: str) -> None:
        super().__init__(message, step="test_runner")


class FailureFixerError(PRTestAutomatorError):
    """Raised when the Claude-based fix loop fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, step="failure_fixer")


class PRCommenterError(PRTestAutomatorError):
    """Raised when posting a GitHub PR comment fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, step="pr_commenter")


class TestPusherError(PRTestAutomatorError):
    """Raised when committing or pushing test files fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, step="test_pusher")
