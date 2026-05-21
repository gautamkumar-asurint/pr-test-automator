# pr-test-automator

Auto-generate pytest tests for Python code changed in a GitHub PR, run them, fix failures with Claude, and post the result as a PR comment.

This is a vendor-neutral, drop-in GitHub Action and Python library. Point it at any Python repo, give it an Anthropic API key, and every PR gets:

- New tests generated for any function or class touched by the diff
- A pytest run inside the workflow
- Up to N rounds of Claude-driven test-fixing if anything fails
- A formatted Markdown comment on the PR with the results
- Optionally, a commit pushing the generated tests back to the PR branch

## Pipeline

The library runs an 8-step pipeline. Each step is its own class under `pr_test_automator.steps` and can be unit-tested in isolation.

| # | Step | What it does |
|---|------|--------------|
| 1 | `PRReader` | Fetches PR metadata and the full changed-file list from GitHub (paginated). |
| 2 | `CodeAnalyzer` | Parses each changed `.py` file with `ast` and returns the functions/classes whose lines overlap with the diff. |
| 3 | `TestFinder` | Locates existing `test_*.py` files for the touched sources so generated tests match the project's style. |
| 4 | `TestGenerator` | Prompts Claude for one self-contained pytest module per source file. |
| 5 | `TestRunner` | Writes the generated tests to a temp dir and runs `pytest`, parsing the output. |
| 6 | `FailureFixer` | If anything failed, sends the failing module + pytest output back to Claude up to `max_fix_retries` times. |
| 7 | `PRCommenter` | Posts a Markdown summary as a PR comment via the GitHub Issues API. |
| 8 | `TestPusher` | Optional — commits the generated tests back to the PR branch with a configurable bot identity. |

## Quick start (as a GitHub Action)

Add this to `.github/workflows/pr-tests.yml` in any Python repo:

```yaml
name: PR Test Automator
on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: write       # only needed if push-test-commit is "true"
  pull-requests: write

jobs:
  automate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.head_ref }}
          fetch-depth: 0

      - uses: your-org/pr-test-automator@v0.1.0
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
          pr-number: ${{ github.event.pull_request.number }}
          source-root: src
          install-extra-requirements: requirements.txt
```

Add `ANTHROPIC_API_KEY` to the repo's Actions secrets, open a PR, and watch the bot comment appear.

## Action inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `github-token` | yes | — | Use `${{ secrets.GITHUB_TOKEN }}`. |
| `anthropic-api-key` | yes | — | Anthropic API key from Actions secrets. |
| `pr-number` | yes | — | Usually `${{ github.event.pull_request.number }}`. |
| `python-version` | no | `3.13` | Python version for `actions/setup-python`. |
| `test-dirs` | no | `tests` | Comma-separated. First entry is where new tests are written. |
| `source-root` | no | `""` | Restrict analysis to files under this repo-relative path. |
| `install-extra-requirements` | no | `""` | Requirements file to install before running. |
| `push-test-commit` | no | `false` | Commit generated tests back to the PR branch. |
| `max-fix-retries` | no | `3` | Fixer-loop attempts after a failing run. |
| `model` | no | `claude-sonnet-4-5` | Anthropic model id. |
| `hard-gate` | no | `false` | Set `true` to fail the workflow on test failures. |

## Using as a Python library

```python
import asyncio
from pr_test_automator import PRTestConfig, PRTestPipeline

config = PRTestConfig(
    github_token="ghp_...",
    claude_api_key="sk-ant-...",
    repo="owner/repo",
    repo_path="/path/to/local/checkout",
    test_dirs=["tests"],
    source_root="src",
    push_test_commit=False,
    max_fix_retries=3,
)

result = asyncio.run(PRTestPipeline(config).run(pr_number=42))
print(result.is_passing, result.tests_generated)
```

`PipelineResult` exposes `pr_number`, `files_changed`, `functions_affected`, `tests_generated`, `test_result` (with `passed`/`failed`/`errors`/`output`), `comment_url`, `commit_sha`, and a `steps` list of per-step outcomes.

## CLI usage

The package ships an entry point that reads from environment variables — this is what the Action invokes under the hood:

```bash
export GITHUB_TOKEN=ghp_...
export ANTHROPIC_API_KEY=sk-ant-...
export GITHUB_REPOSITORY=owner/repo
export PR_NUMBER=42
export TEST_DIRS=tests
export SOURCE_ROOT=src

python -m pr_test_automator
```

## How files are matched

- A file is **considered for analysis** if it ends in `.py`, lives outside any `tests/` directory, and (if `source_root` is set) lives under `source_root`.
- Existing tests for `src/foo/bar.py` are searched in (priority order):
  1. Each entry in `test_dirs` plus `extra_dirs`, joined with `test_bar.py`
  2. `src/foo/test_bar.py` (sibling)
  3. `src/foo/../tests/test_bar.py`
- New tests are written to `{test_dirs[0]}/test_{stem}.py`.

## Permissions and security

- The Action only needs `pull-requests: write` to comment. Add `contents: write` only if you enable `push-test-commit`.
- Generated tests run inside the runner's working directory. Make sure the runner has access to all your project's runtime dependencies (use `install-extra-requirements` for that).
- Your Anthropic key never leaves the runner — it's passed via env var to the Python process.

## Development

```bash
git clone https://github.com/your-org/pr-test-automator.git
cd pr-test-automator
pip install -e ".[dev]"
pytest
```

## License

MIT
