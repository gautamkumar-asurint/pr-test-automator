"""Unified diff parser for extracting changed line numbers from PR patches."""

from __future__ import annotations

import re


def parse_changed_lines(patch: str) -> set[int]:
    """Return the set of new-file line numbers that were added or modified.

    Only addition lines (``+``) are tracked; deletion lines (``-``) do not map
    to line numbers in the new file version.
    """
    changed_lines: set[int] = set()
    current_line = 0

    for line in patch.splitlines():
        if line.startswith("@@"):
            match = re.search(r"\+(\d+)", line)
            if match:
                current_line = int(match.group(1)) - 1
        elif line.startswith("+++") or line.startswith("---"):
            continue
        elif line.startswith("+"):
            current_line += 1
            changed_lines.add(current_line)
        elif line.startswith("-"):
            pass  # removed lines have no position in the new file
        else:
            current_line += 1

    return changed_lines


def extract_code_block(text: str) -> str:
    """Extract the first Python code block from a markdown-formatted string.

    Falls back to returning the full text stripped if no fenced block is found.
    """
    pattern = re.compile(r"```(?:python)?\n(.*?)```", re.DOTALL)
    match = pattern.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()
