"""Unit tests for the GEDCOM text writer and the parser's ``@@`` unescape."""

from __future__ import annotations

import pytest

from slaktbusken.gedcom.parser import parse_gedcom
from slaktbusken.gedcom.text_lines import escape_text, text_lines
from slaktbusken.gedcom.translation.record_identity import record_hash


def _read_back(text: str, max_len: int = 200) -> str | None:
    lines = ["0 HEAD", "0 @I1@ INDI"] + text_lines(1, "NOTE", text, max_len) + ["0 TRLR"]
    result = parse_gedcom("\n".join(lines))
    assert not result.warnings
    return result.records[1].children[0].value


def test_escape_text_doubles_only_a_leading_at() -> None:
    assert escape_text("@abc") == "@@abc"
    assert escape_text("a@b") == "a@b"
    assert escape_text("") == ""


def test_single_line() -> None:
    assert text_lines(1, "NOTE", "hej") == ["1 NOTE hej"]


def test_empty_text_gives_bare_line() -> None:
    assert text_lines(1, "NOTE", "") == ["1 NOTE"]


def test_line_breaks_become_cont() -> None:
    assert text_lines(1, "NOTE", "a\n\nb") == ["1 NOTE a", "2 CONT", "2 CONT b"]


def test_long_line_becomes_conc_and_stays_within_255() -> None:
    lines = text_lines(2, "NOTE", "x" * 450)
    assert [line.split(" ")[1] for line in lines] == ["NOTE", "CONC", "CONC"]
    assert all(len(line) <= 255 for line in lines)


def test_leading_at_is_doubled_on_first_and_cont_lines() -> None:
    assert text_lines(1, "NOTE", "@a\n@b") == ["1 NOTE @@a", "2 CONT @@b"]


def test_split_does_not_cut_a_surrogate_pair() -> None:
    lines = text_lines(1, "NOTE", "a\ud83d\ude00b", max_len=2)
    assert lines[0] == "1 NOTE a"
    assert "\ud83d\ude00" in lines[1]


@pytest.mark.parametrize(
    "text",
    [
        "",
        "@",
        "@@x",
        "@I1@",
        "a@@b",
        "rad ett\n@rad två\n\nrad fyra  ",
        "  inledande och avslutande  ",
        "åäö " * 120,
        "x" * 200 + " " + "y" * 10,
        "a\u2028b\x85c",
    ],
)
@pytest.mark.parametrize("max_len", [2, 7, 200])
def test_round_trip(text: str, max_len: int) -> None:
    assert (_read_back(text, max_len) or "") == text


def test_pointer_value_is_not_changed() -> None:
    result = parse_gedcom("0 HEAD\n0 @F1@ FAM\n1 HUSB @I1@\n1 NOTE @@I1@")
    husb, note = result.records[1].children
    assert husb.value == "@I1@"
    assert note.value == "@I1@"


def test_hash_ignores_the_unescape() -> None:
    """The record hash is computed from the value as written in the file."""
    escaped = parse_gedcom("0 HEAD\n0 @I1@ INDI\n1 BIRT\n2 NOTE @@x\n").records[1].children[0]
    assert escaped.children[0].value == "@x"
    assert record_hash(escaped, {}) == _legacy_hash("1 BIRT\n2 NOTE @@x")


def _legacy_hash(canonical: str) -> str:
    import hashlib

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
