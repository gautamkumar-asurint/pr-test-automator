"""Step 4: Generate pytest tests for affected functions using Claude."""

from __future__ import annotations

import anthropic

from pr_test_automator._logging import get_logger
from pr_test_automator.config import PRTestConfig
from pr_test_automator.models import (
    AffectedFunction,
    ExistingTest,
    GeneratedTest,
)
from pr_test_automator.steps.test_finder import TestFinder
from pr_test_automator.utils.diff_parser import extract_code_block
from pr_test_automator.utils.exceptions import TestGeneratorError
from pr_test_automator.utils.test_parser import (
    TestFunction,
    covers,
    parse_test_functions,
)

logger = get_logger(__name__)

_SYSTEM_PROMPT_FRESH = """\
You are an expert Python test engineer specializing in pytest.
Generate high-quality, production-ready tests following these rules:

- Use pytest with @pytest.mark.unit for unit tests
- For async functions, combine @pytest.mark.asyncio with async def
- Always test: happy path, edge cases (empty/None/boundary values), error cases
- Mock all external dependencies using pytest-mock or unittest.mock
- Name tests as test_{function_name}_{scenario}
- Write descriptive assertion messages
- Import only what is needed
- Do NOT manipulate sys.path; assume the package is installed
- Output ONLY valid Python code, no markdown, no explanation
"""

_SYSTEM_PROMPT_INCREMENTAL = """\
You are an expert Python test engineer specializing in pytest.
You are writing test functions to be ADDED to an existing test module.

CRITICAL — STYLE PRESERVATION:
- Match the EXACT style of the existing tests in the user's prompt
- If existing tests use @pytest.mark.unit, your tests must use it
- If existing tests use `-> None` annotation, your tests must too
- If existing tests omit docstrings, your tests must too
- If existing tests use inline asserts (no `result =` variable), match that
- Mirror the existing naming pattern exactly

Your output will be inserted into a file that already has its imports
and other tests. Other rules:

- Output ONLY the new test functions (decorators + definitions) — no
  import statements, no module-level code, no markdown, no explanation
- For async functions, use @pytest.mark.asyncio with async def
- Test happy path, edge cases, and error cases for each function
- Mock external dependencies using pytest-mock or unittest.mock
- Name tests as test_{function_name}_{scenario}
- Do not rename existing tests; if replacing a test named X, your new
  test for the same scenario should also be named X
"""

_USER_TEMPLATE_FRESH = (
    "Generate pytest tests for the following Python function(s).\n"
    "\n"
    "Source file: {source_file}\n"
    "\n"
    "To import from this file, derive the module path by dropping any 'src/' "
    "prefix and converting slashes to dots, omitting the '.py' extension. "
    "For example, 'src/calculator/discount.py' becomes "
    "'from calculator.discount import ...'.\n"
    "\n"
    "Functions to test:\n"
    "```python\n"
    "{functions_code}\n"
    "```\n"
    "\n"
    "Produce a complete test module with imports and all test functions.\n"
)

_USER_TEMPLATE_INCREMENTAL = (
    "Write pytest test functions to be added to an existing test file.\n"
    "\n"
    "Source file:    {source_file}\n"
    "Test file:      {test_file}\n"
    "\n"
    "Existing test file content (PRESERVE this style — match decorators, "
    "type annotations, naming, and assertion patterns exactly):\n"
    "```python\n"
    "{existing_content}\n"
    "```\n"
    "{style_reference_section}"
    "Write tests for ONLY these functions. Existing tests for these "
    "functions are being replaced because the source changed.\n"
    "\n"
    "{functions_section}"
    "\n"
    "Output ONLY the new test function definitions (with their decorators). "
    "Do NOT include imports or other module-level code. Match the EXACT "
    "style of the existing tests above — same decorators (e.g. "
    "@pytest.mark.unit), same type annotations (e.g. -> None), same "
    "assertion style.\n"
)

_STYLE_REFERENCE_SECTION = (
    "\n"
    "Style reference — the tests being replaced for these functions had "
    "this style (match it exactly in your output):\n"
    "```python\n"
    "{removed_tests_code}\n"
    "```\n"
)

_FUNCTION_BLOCK = (
    "Function `{name}` (status: {status}):\n"
    "```python\n"
    "{code}\n"
    "```\n"
    "\n"
)

_MAX_TOKENS = 4096


class TestGenerator:
    """Generates pytest test modules via the Claude API.

    Strategy:
    - No existing test file for a source -> generate a fresh test module.
    - Existing test file for a source -> identify which tests cover the
      affected functions, splice them out, and ask Claude for replacements
      plus tests for any uncovered new functions. Merge into existing file.
    """

    def __init__(self, config: PRTestConfig, test_finder: TestFinder) -> None:
        self._config = config
        self._test_finder = test_finder
        self._client = anthropic.Anthropic(api_key=config.claude_api_key)

    async def generate(
        self,
        affected: list[AffectedFunction],
        existing_tests: list[ExistingTest],
    ) -> list[GeneratedTest]:
        by_file = self._group_by_file(affected)
        existing_by_source = {t.source_file_path: t for t in existing_tests}
        results: list[GeneratedTest] = []

        for source_path, functions in by_file.items():
            existing = existing_by_source.get(source_path)
            if existing:
                generated = self._generate_incremental(
                    source_path, functions, existing
                )
            else:
                generated = self._generate_fresh(source_path, functions)
            results.append(generated)
            logger.info(
                "generated tests",
                extra={
                    "source": source_path,
                    "mode": "incremental" if existing else "fresh",
                },
            )

        return results

    def _generate_fresh(
        self,
        source_path: str,
        functions: list[AffectedFunction],
    ) -> GeneratedTest:
        """No existing test file — generate the whole module from scratch."""
        functions_code = "\n\n".join(fn.source_code for fn in functions)
        prompt = _USER_TEMPLATE_FRESH.format(
            source_file=source_path,
            functions_code=functions_code,
        )
        raw = self._call_claude(_SYSTEM_PROMPT_FRESH, prompt, source_path)
        code = extract_code_block(raw)
        test_path = self._test_finder.suggest_test_path(source_path, existing=None)

        return GeneratedTest(
            source_file_path=source_path,
            test_file_path=test_path,
            content=code,
            covered_functions=[fn.qualified_name for fn in functions],
        )

    def _generate_incremental(
        self,
        source_path: str,
        functions: list[AffectedFunction],
        existing: ExistingTest,
    ) -> GeneratedTest:
        """Merge new/updated tests into the existing test file."""
        existing_tests = parse_test_functions(existing.content)

        # For each affected function, find existing tests that cover it.
        function_status: list[tuple[AffectedFunction, str, list[TestFunction]]] = []
        tests_to_remove: list[TestFunction] = []

        for fn in functions:
            matching = [t for t in existing_tests if covers(t.name, fn.name)]
            if matching:
                status = "MODIFIED - existing tests will be replaced"
                tests_to_remove.extend(matching)
            else:
                status = "NEW - no existing tests"
            function_status.append((fn, status, matching))

        functions_section = "".join(
            _FUNCTION_BLOCK.format(
                name=fn.name, status=status, code=fn.source_code
            )
            for fn, status, _ in function_status
        )

        # Extract the source of tests being removed, so we can show them to
        # Claude as a style reference separately from the kept content.
        # Without this, once all covering tests are removed Claude has no
        # style anchor and reverts to defaults (drops decorators, etc.).
        removed_tests_code = self._extract_test_source(
            existing.content, tests_to_remove
        )
        style_reference_section = (
            _STYLE_REFERENCE_SECTION.format(
                removed_tests_code=removed_tests_code
            )
            if removed_tests_code.strip()
            else ""
        )

        trimmed_existing = self._remove_tests(existing.content, tests_to_remove)

        prompt = _USER_TEMPLATE_INCREMENTAL.format(
            source_file=source_path,
            test_file=existing.test_file_path,
            existing_content=trimmed_existing,
            style_reference_section=style_reference_section,
            functions_section=functions_section,
        )

        raw = self._call_claude(
            _SYSTEM_PROMPT_INCREMENTAL, prompt, source_path
        )
        new_test_code = extract_code_block(raw).strip()
        merged = self._merge(trimmed_existing, new_test_code)

        return GeneratedTest(
            source_file_path=source_path,
            test_file_path=existing.test_file_path,
            content=merged,
            covered_functions=[fn.qualified_name for fn in functions],
        )

    @staticmethod
    def _extract_test_source(
        content: str, tests: list[TestFunction]
    ) -> str:
        """Return the source code of the given test functions, concatenated.

        Used to give Claude a style reference for tests being replaced.
        """
        if not tests:
            return ""

        lines = content.splitlines(keepends=True)
        blocks: list[str] = []
        for t in tests:
            block = "".join(lines[t.line_start - 1 : t.line_end])
            blocks.append(block.rstrip())
        return "\n\n".join(blocks)

    @staticmethod
    def _remove_tests(
        content: str, to_remove: list[TestFunction]
    ) -> str:
        """Remove the given test functions from content. Lines are 1-indexed."""
        if not to_remove:
            return content

        lines = content.splitlines(keepends=True)
        drop: set[int] = set()
        for test in to_remove:
            for i in range(test.line_start - 1, test.line_end):
                drop.add(i)

        kept = [line for i, line in enumerate(lines) if i not in drop]
        return _collapse_blank_runs("".join(kept))

    @staticmethod
    def _merge(existing: str, new_tests: str) -> str:
        """Append ``new_tests`` to ``existing`` with proper spacing."""
        if not new_tests:
            return existing
        existing = existing.rstrip() + "\n\n\n"
        return existing + new_tests.rstrip() + "\n"

    def _call_claude(
        self,
        system_prompt: str,
        user_prompt: str,
        source_path: str,
    ) -> str:
        try:
            message = self._client.messages.create(
                model=self._config.model,
                max_tokens=_MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.APIError as exc:
            raise TestGeneratorError(
                f"Claude API error for {source_path}: {exc}"
            ) from exc
        return message.content[0].text

    @staticmethod
    def _group_by_file(
        affected: list[AffectedFunction],
    ) -> dict[str, list[AffectedFunction]]:
        groups: dict[str, list[AffectedFunction]] = {}
        for fn in affected:
            groups.setdefault(fn.file_path, []).append(fn)
        return groups


def _collapse_blank_runs(text: str) -> str:
    """Replace runs of 3+ blank lines with exactly 2."""
    lines = text.split("\n")
    out: list[str] = []
    blank_count = 0
    for line in lines:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 2:
                out.append(line)
        else:
            blank_count = 0
            out.append(line)
    return "\n".join(out)