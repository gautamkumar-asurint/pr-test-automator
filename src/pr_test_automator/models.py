"""Pydantic models shared across all pipeline steps."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PRFile(BaseModel):
    """A single file changed in a pull request."""

    filename: str
    status: str  # added | modified | removed | renamed
    patch: str | None = None
    sha: str | None = None
    raw_url: str | None = None


class PRInfo(BaseModel):
    """Metadata about the pull request being processed."""

    number: int
    title: str
    head_branch: str
    base_branch: str
    author: str
    files: list[PRFile]


class AffectedFunction(BaseModel):
    """A Python function or class whose lines overlap with the PR diff."""

    file_path: str
    name: str
    qualified_name: str  # ClassName.method for methods, bare name otherwise
    kind: str  # function | async_function | method | async_method | class
    source_code: str
    line_start: int
    line_end: int


class ExistingTest(BaseModel):
    """An existing test file related to a changed source file."""

    test_file_path: str
    source_file_path: str
    content: str


class GeneratedTest(BaseModel):
    """A Claude-generated test module for one source file."""

    source_file_path: str
    test_file_path: str
    content: str
    covered_functions: list[str]


class TestRunResult(BaseModel):
    """Outcome of a single pytest execution."""

    passed: int
    failed: int
    errors: int
    total: int
    output: str
    failed_test_ids: list[str]
    is_passing: bool


class StepOutcome(BaseModel):
    """Records whether a pipeline step succeeded and any useful metadata."""

    step: str
    success: bool
    message: str
    data: dict[str, Any] = {}


class PipelineResult(BaseModel):
    """Aggregated result of the full pipeline run."""

    pr_number: int
    repo: str
    files_changed: int
    functions_affected: int
    tests_generated: int
    test_result: TestRunResult | None = None
    comment_url: str | None = None
    commit_sha: str | None = None
    steps: list[StepOutcome] = []
    is_passing: bool = False
