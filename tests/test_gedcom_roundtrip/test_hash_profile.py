"""Property 12 and the golden vectors of both hash profiles."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from slaktbusken.gedcom.parser import GedcomLine
from slaktbusken.gedcom.translation.record_identity import record_hash
from slaktbusken.gedcom.translation.record_identity_golden import (
    GOLDEN_VECTORS,
    SLK1_GOLDEN_VECTORS,
    build_record,
)

pytestmark = pytest.mark.mandatory_integrity

SOURCE_IDS = {"@S1@": "src-0001"}

# Records without any node that the slk1 profile removes.
_BASES = (
    ("1 BIRT", "2 PLAC Stockholm", "2 DATE 12 MAR 1850", "2 SOUR @S1@",
     "2 SOUR @S2@", "3 NOTE Observation: 1875"),
    ("1 RESI", "2 DATE FROM 1870 TO 1880", "2 PLAC Uppsala", "2 NOTE Roll: x",
     "2 SOUR @S1@"),
    ("1 EVEN", "2 TYPE Flytt", "2 DATE 1880", "2 SOUR @S1@", "3 TEXT t"),
)

_SLK_TAGS = ("_SLK_EID", "_SLK_CTX", "_SLK_ASP", "_SLK_START", "_SLK_UNKNOWN",
             "_SLK_X")
_SOUR_CHILD_TAGS = ("QUAY", "PAGE", "DATA", "OBJE", "NOTE")
_VALUE = st.text("abc 12åö", max_size=12)


def _all_nodes(node: GedcomLine) -> list[GedcomLine]:
    found = [node]
    for child in node.children:
        found.extend(_all_nodes(child))
    return found


def _node(tag: str, value: str, depth: int) -> GedcomLine:
    return GedcomLine(level=depth, tag=tag, value=value or None, xref_id=None,
                      line_number=0)


@st.composite
def _slk_node(draw, depth: int) -> GedcomLine:
    node = _node(draw(st.sampled_from(_SLK_TAGS)), draw(_VALUE), depth)
    for _ in range(draw(st.integers(0, 2))):
        child = _node(draw(st.sampled_from(_SLK_TAGS + ("DATE", "NOTE"))),
                      draw(_VALUE), depth + 1)
        node.children.append(child)
    return node


@st.composite
def _record_with_additions(draw):
    base = draw(st.sampled_from(_BASES))
    clean = build_record(base)
    changed = build_record(base)
    for _ in range(draw(st.integers(1, 6))):
        nodes = _all_nodes(changed)
        if draw(st.booleans()):
            parent = draw(st.sampled_from(nodes))
            parent.children.insert(
                draw(st.integers(0, len(parent.children))),
                draw(_slk_node(parent.level + 1)))
        else:
            sours = [n for n in nodes if n.tag == "SOUR"]
            parent = draw(st.sampled_from(sours))
            tag = draw(st.sampled_from(_SOUR_CHILD_TAGS))
            value = draw(_VALUE)
            if tag == "NOTE" and value.strip().startswith("Observation:"):
                value = "x" + value
            parent.children.insert(
                draw(st.integers(0, len(parent.children))),
                _node(tag, value, parent.level + 1))
    return clean, changed


# Feature: gedcom-roundtrip-0-3-0, Property 12: The slk1 record hash ignores exactly the nodes that this spec adds
# **Validates: Requirements 7.10, 12.4, 12.5, 12.6, 12.7**
@given(_record_with_additions())
def test_slk1_hash_ignores_added_nodes(pair) -> None:
    clean, changed = pair
    assert record_hash(changed, SOURCE_IDS, "slk1") == record_hash(
        clean, SOURCE_IDS, "slk1")
    assert record_hash(clean, SOURCE_IDS, "legacy") == record_hash(
        clean, SOURCE_IDS, "slk1")


@pytest.mark.parametrize("vector", GOLDEN_VECTORS, ids=lambda v: v.name)
def test_legacy_golden_vectors(vector) -> None:
    record = build_record(vector.lines)
    assert record_hash(record, vector.source_ids) == vector.expected
    assert record_hash(record, vector.source_ids, "legacy") == vector.expected


@pytest.mark.parametrize("vector", SLK1_GOLDEN_VECTORS, ids=lambda v: v.name)
def test_slk1_golden_vectors(vector) -> None:
    record = build_record(vector.lines)
    assert record_hash(record, vector.source_ids, "slk1") == vector.expected


def test_new_exporter_form_hashes_like_old_form() -> None:
    new, old = SLK1_GOLDEN_VECTORS[0], GOLDEN_VECTORS[0]
    assert new.expected != old.expected  # old form carries a PAGE under SOUR
    stripped = tuple(
        line for line in old.lines if not line.startswith("3 PAGE"))
    assert record_hash(build_record(stripped), old.source_ids, "legacy") == \
        record_hash(build_record(stripped), old.source_ids, "slk1")


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(ValueError):
        record_hash(build_record(("1 BIRT",)), {}, "nope")


def test_slk1_hash_ignores_caus_and_legacy_keeps_it() -> None:
    old = ("1 DEAT", "2 DATE 1900", "2 PLAC Uppsala")
    new = old + ("2 CAUS Lunginflammation",)
    assert record_hash(build_record(new), SOURCE_IDS, "slk1") == record_hash(
        build_record(old), SOURCE_IDS, "slk1")
    assert record_hash(build_record(new), SOURCE_IDS, "legacy") != record_hash(
        build_record(old), SOURCE_IDS, "legacy")
