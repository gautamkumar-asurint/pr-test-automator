"""Tests for the test-module parser used by the incremental generator."""

from pr_test_automator.utils.test_parser import (
    covers,
    parse_test_functions,
)


def test_parse_extracts_function_names() -> None:
    content = '''
import pytest

def test_foo():
    pass

@pytest.mark.unit
def test_bar_happy_path():
    pass
'''
    fns = parse_test_functions(content)
    names = [f.name for f in fns]
    assert names == ["test_foo", "test_bar_happy_path"]


def test_parse_handles_decorators() -> None:
    content = '''
import pytest

@pytest.mark.unit
def test_foo():
    pass
'''
    fns = parse_test_functions(content)
    assert fns[0].decorators == ["pytest.mark.unit"]


def test_parse_returns_empty_on_syntax_error() -> None:
    assert parse_test_functions("this is not python") == []


def test_covers_exact_match() -> None:
    assert covers("test_apply_discount", "apply_discount")


def test_covers_prefix_with_scenario() -> None:
    assert covers("test_apply_discount_zero", "apply_discount")


def test_covers_handles_underscore_in_name() -> None:
    assert covers("test_calculate_tax_with_cap_zero", "calculate_tax_with_cap")


def test_parse_ignores_non_test_functions() -> None:
    content = '''
def helper_function():
    pass

def test_real():
    pass
'''
    fns = parse_test_functions(content)
    names = [f.name for f in fns]
    assert names == ["test_real"]


def test_parse_finds_async_test_functions() -> None:
    content = '''
import pytest

@pytest.mark.asyncio
async def test_async_thing():
    pass
'''
    fns = parse_test_functions(content)
    assert fns[0].name == "test_async_thing"