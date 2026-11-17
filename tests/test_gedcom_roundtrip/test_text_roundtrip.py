"""Property 2: free text round-trips through text_lines and the parser."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from slaktbusken.gedcom.parser import parse_gedcom
from slaktbusken.gedcom.text_lines import text_lines
from tests.test_gedcom_roundtrip.strategies import free_text, long_free_text, text_value
import pytest

pytestmark = pytest.mark.mandatory_integrity


def _roundtrip(lines: list[str]) -> str:
    text = "\n".join(["0 HEAD", *lines, "0 TRLR"]) + "\n"
    head = parse_gedcom(text).records[0]
    assert len(head.children) == 1
    return head.children[0].value or ""


# Feature: gedcom-roundtrip-0-3-0, Property 2: Free text round-trips
# **Validates: Requirements 2.1, 2.3, 2.5**
@given(st.one_of(text_value(), free_text(), long_free_text()))
def test_free_text_roundtrips_and_lines_are_short(text: str) -> None:
    lines = text_lines(1, "NOTE", text)
    assert all(len(line) <= 255 for line in lines)
    assert _roundtrip(lines) == text


def test_text_examples() -> None:
    for text in (
        "",
        "@",
        "@@x",
        "  leading and trailing  ",
        "a\n\nb\n",
        "\n@start",
        "å" * 700,
        "x" * 199 + " " + "y" * 300,
        "x " * 400,
    ):
        lines = text_lines(1, "NOTE", text)
        assert all(len(line) <= 255 for line in lines)
        assert _roundtrip(lines) == text


def test_conc_splits_at_200_and_cont_per_break() -> None:
    lines = text_lines(1, "NOTE", "a" * 450 + "\nb")
    assert [line.split(" ", 2)[1] for line in lines] == ["NOTE", "CONC", "CONC", "CONT"]
    assert len(lines[0]) == len("1 NOTE ") + 200


def test_leading_at_is_doubled() -> None:
    assert text_lines(1, "NOTE", "@x\n@y") == ["1 NOTE @@x", "2 CONT @@y"]
