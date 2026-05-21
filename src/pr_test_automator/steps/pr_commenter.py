"""Step 7: Post a formatted Markdown summary comment to the GitHub PR."""

from __future__ import annotations

import httpx

from pr_test_automator._logging import get_logger
from pr_test_automator.config import PRTestConfig
from pr_test_automator.models import GeneratedTest, PRInfo, TestRunResult
from pr_test_automator.utils.exceptions import PRCommenterError

logger = get_logger(__name__)

_PASS_ICON = "✅"
_FAIL_ICON = "❌"


class PRCommenter:
    """Posts a structured Markdown report as a PR comment via the GitHub API."""

    def __init__(self, config: PRTestConfig) -> None:
        self._config = config

    async def post(
        self,
        pr_info: PRInfo,
        tests: list[GeneratedTest],
        result: TestRunResult,
        fix_attempts: int,
    ) -> str:
        body = self._build_comment(pr_info, tests, result, fix_attempts)
        url = await self._post_comment(pr_info.number, body)
        logger.info("comment posted", extra={"url": url})
        return url

    async def _post_comment(self, pr_number: int, body: str) -> str:
        url = (
            f"{self._config.github_api_base}/repos"
            f"/{self._config.repo}/issues/{pr_number}/comments"
        )
        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            resp = await client.post(
                url,
                headers=self._config.github_headers,
                json={"body": body},
            )

        if resp.status_code not in {200, 201}:
            raise PRCommenterError(
                f"GitHub comment API returned {resp.status_code}: {resp.text}"
            )

        return resp.json().get("html_url", url)

    def _build_comment(
        self,
        pr_info: PRInfo,
        tests: list[GeneratedTest],
        result: TestRunResult,
        fix_attempts: int,
    ) -> str:
        status_icon = _PASS_ICON if result.is_passing else _FAIL_ICON
        total_functions = sum(len(t.covered_functions) for t in tests)

        lines: list[str] = [
            f"## {status_icon} PR Test Automator Report",
            "",
            "### Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Files changed | {len(pr_info.files)} |",
            f"| Functions analyzed | {total_functions} |",
            f"| Test modules generated | {len(tests)} |",
            f"| Tests passed | {result.passed} {_PASS_ICON} |",
            f"| Tests failed | {result.failed} "
            f"{_FAIL_ICON if result.failed else _PASS_ICON} |",
            f"| Fix attempts | {fix_attempts} |",
            "",
        ]

        if tests:
            lines += self._generated_tests_section(tests)

        if result.failed_test_ids:
            lines += self._failures_section(result)

        lines += self._pytest_output_section(result)
        lines += ["", "---", self._config.comment_footer]

        return "\n".join(lines)

    @staticmethod
    def _generated_tests_section(tests: list[GeneratedTest]) -> list[str]:
        lines = ["### Generated Tests", ""]
        for gen in tests:
            fn_list = ", ".join(f"`{fn}`" for fn in gen.covered_functions)
            lines += [
                "<details>",
                f"<summary>📄 <code>{gen.test_file_path}</code> — "
                f"covers {fn_list}</summary>",
                "",
                "```python",
                gen.content,
                "```",
                "",
                "</details>",
                "",
            ]
        return lines

    @staticmethod
    def _failures_section(result: TestRunResult) -> list[str]:
        lines = ["### Failures", ""]
        for tid in result.failed_test_ids:
            lines.append(f"- `{tid}`")
        lines.append("")
        return lines

    @staticmethod
    def _pytest_output_section(result: TestRunResult) -> list[str]:
        truncated = (
            result.output[-3000:] if len(result.output) > 3000 else result.output
        )
        return [
            "",
            "<details>",
            "<summary>🔍 pytest output</summary>",
            "",
            "```",
            truncated,
            "```",
            "",
            "</details>",
        ]
