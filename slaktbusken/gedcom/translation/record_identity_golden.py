"""Fixed golden vectors for ``record_identity.record_hash`` (task 10.5 pins them).

Each vector is a GEDCOM record (level-1 line first), the ``source_ids`` mapping
and the expected SHA-256. Changing the canonical form changes these values and
requires a migration of stored hashes; see design Component 7.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from slaktbusken.gedcom.parser import GedcomLine


@dataclass(frozen=True)
class GoldenVector:
    name: str
    lines: tuple[str, ...]            # "LEVEL TAG [VALUE]", first line is the record
    source_ids: Mapping[str, str]
    expected: str


def build_record(lines: tuple[str, ...]) -> GedcomLine:
    """Build the ``GedcomLine`` tree of a vector (no parser, no I/O)."""
    root: GedcomLine | None = None
    stack: list[GedcomLine] = []
    for n, raw in enumerate(lines, start=1):
        parts = raw.split(" ", 2)
        level = int(parts[0])
        node = GedcomLine(
            level=level,
            tag=parts[1],
            value=parts[2] if len(parts) > 2 else None,
            xref_id=None,
            line_number=n,
        )
        while stack and stack[-1].level >= level:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            root = node
        stack.append(node)
    assert root is not None
    return root


GOLDEN_VECTORS: tuple[GoldenVector, ...] = (
    GoldenVector(
        name="event_birt",
        lines=(
            "1 BIRT",
            "2 PLAC Stockholm",
            "2 DATE 12 MAR 1850",
            "2 SOUR @S1@",
            "3 PAGE s.  14",
            "2 CHAN",
            "3 DATE 1 JAN 2020",
            "2 _UID ABC",
        ),
        source_ids={"@S1@": "src-0001"},
        expected="8ed2c7226aaa1b74040db6406e1bc852453e86ce1025cbb8bbbc172b76969d53",
    ),
    GoldenVector(
        name="event_even_flytt",
        lines=(
            "1 EVEN",
            "2 TYPE Flytt",
            "2 DATE 1880",
            "2 FAMC @F9@",
            "2 NOTE first",
            "2 NOTE second",
            "2 SOUR @S2@",
            "2 SOUR @S1@",
        ),
        source_ids={"@S1@": "src-0001"},
        expected="9319b800e0bf8ec890b994d3a186ffce98e05ef599d6cc926ccce81b2b9906f2",
    ),
    GoldenVector(
        name="resi_basic",
        lines=(
            "1 RESI",
            "2 DATE FROM 1870 TO 1880",
            "2 PLAC Uppsala, Sverige",
            "2 NOTE Bodde hos   föräldrarna",
            "2 SOUR @S1@",
            "3 PAGE 7",
            "2 _UPD 1 JAN 2020",
        ),
        source_ids={"@S1@": "src-0001"},
        expected="00255d47ed1ab640caca138700645f1de0ea2cc04cc5c93e48db0ac26e9c5faf",
    ),
    GoldenVector(
        name="resi_no_date",
        lines=(
            "1 RESI",
            "2 PLAC Malmö",
            "2 SOUR @S3@",
            "2 NOTE a",
            "2 NOTE b",
        ),
        source_ids={},
        expected="1ab0a90985aa27efa9b23ee6d9723bb95e438ead4c45e6dad01f7edc6d56929e",
    ),
)
