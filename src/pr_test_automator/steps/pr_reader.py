"""Step 1: Read PR metadata and changed files from GitHub."""

from __future__ import annotations

import asyncio

import httpx

from pr_test_automator._logging import get_logger
from pr_test_automator.config import PRTestConfig
from pr_test_automator.models import PRFile, PRInfo
from pr_test_automator.utils.exceptions import PRReaderError

logger = get_logger(__name__)

_PYTHON_EXTENSIONS = (".py",)


class PRReader:
    """Fetches PR metadata, changed files, and their diffs from GitHub."""

    def __init__(self, config: PRTestConfig) -> None:
        self._config = config

    async def read(self, pr_number: int) -> PRInfo:
        """Fetch PR metadata and all changed Python source files."""
        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            pr_data, files = await self._fetch_pr_and_files(client, pr_number)

        python_files = [f for f in files if self._is_python_source(f["filename"])]

        if not python_files:
            logger.info("no Python source files changed in this PR")

        pr_files = [
            PRFile(
                filename=f["filename"],
                status=f["status"],
                patch=f.get("patch"),
                sha=f.get("sha"),
                raw_url=f.get("raw_url"),
            )
            for f in python_files
        ]

        logger.info(
            "PR fetched",
            extra={
                "pr": pr_number,
                "repo": self._config.repo,
                "python_files": len(pr_files),
            },
        )

        return PRInfo(
            number=pr_number,
            title=pr_data.get("title", ""),
            head_branch=pr_data["head"]["ref"],
            base_branch=pr_data["base"]["ref"],
            author=pr_data["user"]["login"],
            files=pr_files,
        )

    async def _fetch_pr_and_files(
        self,
        client: httpx.AsyncClient,
        pr_number: int,
    ) -> tuple[dict, list[dict]]:
        """Fetch PR metadata and the full (paginated) file list."""
        pr_url = (
            f"{self._config.github_api_base}/repos"
            f"/{self._config.repo}/pulls/{pr_number}"
        )

        pr_resp_task = client.get(pr_url, headers=self._config.github_headers)
        files_task = self._fetch_all_files(client, pr_url)

        pr_resp, files = await asyncio.gather(pr_resp_task, files_task)

        if pr_resp.status_code != 200:
            raise PRReaderError(
                f"GitHub PR API returned {pr_resp.status_code}: {pr_resp.text}"
            )

        return pr_resp.json(), files

    async def _fetch_all_files(
        self,
        client: httpx.AsyncClient,
        pr_url: str,
    ) -> list[dict]:
        """Walk through the paginated /files endpoint (PRs can have >30 files)."""
        files: list[dict] = []
        page = 1
        while True:
            resp = await client.get(
                f"{pr_url}/files",
                headers=self._config.github_headers,
                params={"per_page": 100, "page": page},
            )
            if resp.status_code != 200:
                raise PRReaderError(
                    f"GitHub PR files API returned {resp.status_code}: {resp.text}"
                )
            batch = resp.json()
            if not batch:
                break
            files.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return files

    def _is_python_source(self, filename: str) -> bool:
        """Return True for non-test Python source files within the source root."""
        if not filename.endswith(_PYTHON_EXTENSIONS):
            return False

        # Skip anything that already lives in a tests/ tree.
        if (
            filename.startswith("test_")
            or "/test_" in filename
            or "/tests/" in filename
            or filename.endswith("_test.py")
        ):
            return False

        # If the consumer scoped the analyzer to a subdirectory, enforce it.
        root = self._config.source_root
        if root and not filename.startswith(root.rstrip("/") + "/"):
            return False

        return True
