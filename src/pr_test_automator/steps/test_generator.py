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

logger = get_logger(__name__)

_SYSTEM_PROMPT = """\
You are an expert Python test engineer specializing in pytest.
Generate high-quality, production-ready tests following these rules:

- Use pytest with @pytest.mark.unit for unit tests
- For async functions, combine @pytest.mark.asyncio with async def
- Always test: happy path, edge cases (empty/None/boundary values), error cases
- Mock all external dependencies (DB, HTTP clients, queues, AWS, etc.) using
  pytest-mock or unittest.mock
- Name tests as test_{function_name}_{scenario} (e.g. test_get_user_not_found)
- Write descriptive assertion messages
- Import only what is needed — no unused imports
- Output ONLY valid Python code, no markdown, no explanation
"""

_USER_TEMPLATE = """\
Generate pytest tests for the following Python function(s).

Source file: {source_file}

Functions to test:
```python
{functions_code}
```

{existing_tests_section}

Produce a complete, self-contained test module. Import the functions under
test from their correct module path. Use unittest.mock or pytest-mock for all
external dependencies.
"""

_EXISTING_TESTS_SECTION = """\
Existing tests in this project (match the style exactly):
```python
{existing_code}
```
"""

_MAX_TOKENS = 4096


class TestGenerator:
    """Generates pytest test modules via the Claude API."""

    def __init__(self, config: PRTestConfig, test_finder: TestFinder) -> None:
        self._config = config
        self._test_finder = test_finder
        self._client = anthropic.Anthropic(api_key=config.claude_api_key)

    async def generate(
        self,
        affected: list[AffectedFunction],
        existing_tests: list[ExistingTest],
    ) -> list[GeneratedTest]:
        """Generate one test module per unique source file."""
        by_file = self._group_by_file(affected)
        existing_by_source = {t.source_file_path: t for t in existing_tests}
        results: list[GeneratedTest] = []

        for source_path, functions in by_file.items():
            existing = existing_by_source.get(source_path)
            generated = self._generate_for_file(source_path, functions, existing)
            results.append(generated)
            logger.info("generated tests", extra={"source": source_path})

        return results

    def _generate_for_file(
        self,
        source_path: str,
        functions: list[AffectedFunction],
        existing: ExistingTest | None,
    ) -> GeneratedTest:
        prompt = self._build_prompt(source_path, functions, existing)

        try:
            message = self._client.messages.create(
                model=self._config.model,
                max_tokens=_MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise TestGeneratorError(
                f"Claude API error for {source_path}: {exc}"
            ) from exc

        raw = message.content[0].text
        code = extract_code_block(raw)
        test_path = self._test_finder.suggest_test_path(source_path)

        return GeneratedTest(
            source_file_path=source_path,
            test_file_path=test_path,
            content=code,
            covered_functions=[fn.qualified_name for fn in functions],
        )

    def _build_prompt(
        self,
        source_path: str,
        functions: list[AffectedFunction],
        existing: ExistingTest | None,
    ) -> str:
        functions_code = "\n\n".join(fn.source_code for fn in functions)
        existing_section = (
            _EXISTING_TESTS_SECTION.format(existing_code=existing.content)
            if existing
            else ""
        )
        return _USER_TEMPLATE.format(
            source_file=source_path,
            functions_code=functions_code,
            existing_tests_section=existing_section,
        )

    @staticmethod
    def _group_by_file(
        affected: list[AffectedFunction],
    ) -> dict[str, list[AffectedFunction]]:
        groups: dict[str, list[AffectedFunction]] = {}
        for fn in affected:
            groups.setdefault(fn.file_path, []).append(fn)
        return groups
