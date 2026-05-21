"""Unit tests for the diff parser."""

from pr_test_automator.utils.diff_parser import (
    extract_code_block,
    parse_changed_lines,
)


def test_parse_changed_lines_basic_addition() -> None:
    patch = (
        "@@ -1,3 +1,4 @@\n"
        " line1\n"
        " line2\n"
        "+new_line\n"
        " line3\n"
    )
    assert parse_changed_lines(patch) == {3}


def test_parse_changed_lines_ignores_deletions() -> None:
    patch = (
        "@@ -1,3 +1,2 @@\n"
        " line1\n"
        "-removed\n"
        " line3\n"
    )
    assert parse_changed_lines(patch) == set()


def test_parse_changed_lines_multiple_hunks() -> None:
    patch = (
        "@@ -1,2 +1,3 @@\n"
        " a\n"
        "+b\n"
        " c\n"
        "@@ -10,2 +11,3 @@\n"
        " x\n"
        "+y\n"
        " z\n"
    )
    assert parse_changed_lines(patch) == {2, 12}


def test_extract_code_block_with_fences() -> None:
    text = "Here is the code:\n```python\nprint('hi')\n```\nDone."
    assert extract_code_block(text) == "print('hi')"


def test_extract_code_block_without_language_tag() -> None:
    text = "```\nfoo = 1\n```"
    assert extract_code_block(text) == "foo = 1"


def test_extract_code_block_falls_back_to_full_text() -> None:
    text = "no fences here"
    assert extract_code_block(text) == "no fences here"
