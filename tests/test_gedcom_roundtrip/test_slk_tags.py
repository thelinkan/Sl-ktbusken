"""Registry coverage and the fuzz skeleton of Property 14 (readers are total)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from slaktbusken.gedcom import slk_tags
from slaktbusken.gedcom.parser import GedcomLine
from slaktbusken.gedcom.slk_tags import (
    SLK_TAG_REGISTRY,
    is_known_slk_tag,
    unknown_slk_children,
)

pytestmark = pytest.mark.mandatory_integrity


@pytest.mark.parametrize("tag", sorted(SLK_TAG_REGISTRY))
def test_registry_row_is_complete(tag: str) -> None:
    row = SLK_TAG_REGISTRY[tag]
    assert row.tag == tag and tag.startswith("_SLK_")
    assert row.purpose.strip()
    assert row.parents and all(p.strip() for p in row.parents)
    assert row.structure.strip()
    assert row.cardinality in ("0:1", "0:n", "1:1")
    assert row.supported_values.strip()
    assert row.importer_behaviour.strip()
    assert row.standard_fallback.strip()


def test_registry_has_no_duplicate_tags_and_known_lookup() -> None:
    assert is_known_slk_tag("_SLK_VERS")
    assert not is_known_slk_tag("_SLK_NOPE")


def _line(tag: str, value: str | None, children: list[GedcomLine], depth: int) -> GedcomLine:
    return GedcomLine(level=depth, tag=tag, value=value, xref_id=None,
                      line_number=1, children=children)


_KNOWN_TAGS = sorted(SLK_TAG_REGISTRY) + ["_SLK_UNKNOWN", "_SLK_Z", "TYPE", "DATE",
                                          "NOTE", "SOUR", "QUAY", "PAGE", "HUSB",
                                          "WIFE", "TEXT"]
_VALUES = st.one_of(
    st.none(), st.just(""), st.just("@I1@"), st.just("@@"), st.just("2024-13-40"),
    st.just("{"), st.just("church_book {}"), st.just("parish \"x\""),
    st.just("-5"), st.just("1800-1700"), st.text(max_size=15),
)


def _tree(depth: int):
    leaf = st.builds(lambda t, v: _line(t, v, [], depth),
                     st.sampled_from(_KNOWN_TAGS), _VALUES)
    if depth > 5:
        return leaf
    return st.builds(
        lambda t, v, kids: _line(t, v, kids, depth),
        st.sampled_from(_KNOWN_TAGS), _VALUES,
        st.lists(st.deferred(lambda: _tree(depth + 1)), max_size=4),
    )


_READERS = (
    slk_tags.read_citation,
    slk_tags.read_endpoint,
    slk_tags.read_partners,
    slk_tags.read_plinks,
    slk_tags.read_name_type,
    slk_tags.read_source_fields,
    slk_tags.read_repository,
    slk_tags.read_repository_record,
    slk_tags.read_repository_ref,
    slk_tags.read_legacy_prose,
    slk_tags.unknown_slk_children,
)


# Feature: gedcom-roundtrip-0-3-0, Property 14: Unknown and invalid custom tags never abort and never change known data
# **Validates: Requirements 11.3**
@given(_tree(1))
def test_readers_never_raise_on_arbitrary_slk_lines(node: GedcomLine) -> None:
    for reader in _READERS:
        reader(node)  # total: no exception
    for reader in _READERS[:-1]:
        problems: list = []
        reader(node, problems=problems)
        assert all(isinstance(p, slk_tags.SlkProblem) for p in problems)


@given(_tree(1), st.lists(st.sampled_from(["_SLK_UNKNOWN", "_SLK_Q"]), max_size=3))
def test_unknown_tags_do_not_change_known_data(node: GedcomLine, extra: list) -> None:
    before = slk_tags.read_citation(node)
    unknown_before = len(unknown_slk_children(node))
    for tag in extra:
        node.children.append(_line(tag, "x", [_line("_SLK_QUAL", "bad", [], 3)], 2))
    assert slk_tags.read_citation(node) == before
    assert len(unknown_slk_children(node)) == unknown_before + len(extra)
