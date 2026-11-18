"""Unit tests for the shared parent-display resolver (task 4.1).

Covers the precedence rule (override > show-level > fallback), the
non_biological = foster + adoptive rule, the fallback gating, per-link
connection-type selection, and the Parent_Set cardinality / derived-vs-biological
grouping that lets the views obey the single-parent rule.

Requirements: 3.8, 3.9, 3.10, 4.1, 4.2, 4.3, 4.4, 5.2, 5.3, 5.6, 6.2, 6.3, 6.4,
6.5, 6.6
"""

from __future__ import annotations

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.ui.views.parent_display import (
    ParentDisplay,
    link_identity,
    resolve_parent_display,
)
from slaktbusken.ui.widgets.connection_line import ConnectionType


CHILD = "child"


def _family(
    family_id: str, parentage_type: str, parent_ids: list[str]
) -> Family:
    """A Family holding one Parent_Set of ``parentage_type`` for ``CHILD``."""
    return Family(
        id=family_id,
        partners=[FamilyPartner(person_id=pid, role="partner") for pid in parent_ids],
        children=[CHILD],
        parent_child_links=[
            ParentChildLink(child_id=CHILD, parent_id=pid, parentage_type=parentage_type)
            for pid in parent_ids
        ],
    )


def _parent_ids(display: ParentDisplay) -> set[str]:
    return {link.parent_id for link in display.links_to_draw}


def _types_drawn(display: ParentDisplay) -> set[str]:
    return {s.parentage_type for s in display.sets}


# --------------------------------------------------------------------------
# Show_Level behaviour (Req 4.2–4.4)
# --------------------------------------------------------------------------


def test_show_biological_draws_only_biological() -> None:
    bio = _family("fam_bio", "biological", ["dad", "mom"])
    foster = _family("fam_foster", "foster", ["f1"])
    display = resolve_parent_display(
        CHILD, [bio, foster], "biological", override=None, fallback_enabled=True
    )
    assert _types_drawn(display) == {"biological"}
    assert _parent_ids(display) == {"dad", "mom"}


def test_show_non_biological_draws_foster_and_adoptive() -> None:
    bio = _family("fam_bio", "biological", ["dad"])
    foster = _family("fam_foster", "foster", ["f1"])
    adoptive = _family("fam_adopt", "adoptive", ["a1"])
    display = resolve_parent_display(
        CHILD, [bio, foster, adoptive], "non_biological",
        override=None, fallback_enabled=True,
    )
    assert _types_drawn(display) == {"foster", "adoptive"}
    assert _parent_ids(display) == {"f1", "a1"}


def test_show_all_draws_everything() -> None:
    bio = _family("fam_bio", "biological", ["dad", "mom"])
    foster = _family("fam_foster", "foster", ["f1"])
    adoptive = _family("fam_adopt", "adoptive", ["a1"])
    display = resolve_parent_display(
        CHILD, [bio, foster, adoptive], "all",
        override=None, fallback_enabled=True,
    )
    assert _types_drawn(display) == {"biological", "foster", "adoptive"}
    assert _parent_ids(display) == {"dad", "mom", "f1", "a1"}


def test_unknown_show_level_treated_as_biological() -> None:
    bio = _family("fam_bio", "biological", ["dad"])
    foster = _family("fam_foster", "foster", ["f1"])
    display = resolve_parent_display(
        CHILD, [bio, foster], "nonsense", override=None, fallback_enabled=True
    )
    assert _types_drawn(display) == {"biological"}


# --------------------------------------------------------------------------
# Override precedence (Req 5.2, 5.3, 5.6)
# --------------------------------------------------------------------------


def test_override_wins_over_show_level() -> None:
    """An override for a present set beats the global Show_Level (Req 5.2)."""
    bio = _family("fam_bio", "biological", ["dad"])
    foster = _family("fam_foster", "foster", ["f1"])
    display = resolve_parent_display(
        CHILD, [bio, foster], "biological", override="foster", fallback_enabled=True
    )
    assert _types_drawn(display) == {"foster"}
    assert _parent_ids(display) == {"f1"}


def test_override_adoptive_wins_over_all() -> None:
    bio = _family("fam_bio", "biological", ["dad"])
    foster = _family("fam_foster", "foster", ["f1"])
    adoptive = _family("fam_adopt", "adoptive", ["a1"])
    display = resolve_parent_display(
        CHILD, [bio, foster, adoptive], "all",
        override="adoptive", fallback_enabled=True,
    )
    assert _types_drawn(display) == {"adoptive"}
    assert _parent_ids(display) == {"a1"}


def test_override_for_missing_set_ignored_falls_back_to_show_level() -> None:
    """An override naming a set the child lacks is ignored (Req 5.6)."""
    bio = _family("fam_bio", "biological", ["dad", "mom"])
    # No foster family exists; override="foster" must be ignored.
    display = resolve_parent_display(
        CHILD, [bio], "biological", override="foster", fallback_enabled=True
    )
    # Falls through to Show_Level biological.
    assert _types_drawn(display) == {"biological"}
    assert _parent_ids(display) == {"dad", "mom"}


def test_no_override_uses_show_level() -> None:
    """Absent override defers to the Show_Level (Req 5.3)."""
    bio = _family("fam_bio", "biological", ["dad"])
    foster = _family("fam_foster", "foster", ["f1"])
    display = resolve_parent_display(
        CHILD, [bio, foster], "non_biological", override=None, fallback_enabled=True
    )
    assert _types_drawn(display) == {"foster"}


# --------------------------------------------------------------------------
# Parentage_Fallback (Req 6.2, 6.3, 6.6)
# --------------------------------------------------------------------------


def test_fallback_triggers_only_without_biological_parents() -> None:
    """Biological show + no biological parents + enabled => draw non-bio (Req 6.2)."""
    foster = _family("fam_foster", "foster", ["f1"])
    display = resolve_parent_display(
        CHILD, [foster], "biological", override=None, fallback_enabled=True
    )
    assert _types_drawn(display) == {"foster"}
    assert _parent_ids(display) == {"f1"}


def test_fallback_not_triggered_when_biological_present() -> None:
    """With a biological parent, fallback has no effect (Req 6.4-style)."""
    bio = _family("fam_bio", "biological", ["dad"])
    foster = _family("fam_foster", "foster", ["f1"])
    display = resolve_parent_display(
        CHILD, [bio, foster], "biological", override=None, fallback_enabled=True
    )
    assert _types_drawn(display) == {"biological"}


def test_fallback_disabled_draws_nothing_leaving_placeholders() -> None:
    """Fallback off + no biological parents => draw nothing (Req 6.3)."""
    foster = _family("fam_foster", "foster", ["f1"])
    display = resolve_parent_display(
        CHILD, [foster], "biological", override=None, fallback_enabled=False
    )
    assert display.sets == []
    assert display.links_to_draw == []


def test_fallback_draws_both_foster_and_adoptive_when_both_present() -> None:
    """Fallback with both non-biological types draws both (Req 6.6)."""
    foster = _family("fam_foster", "foster", ["f1"])
    adoptive = _family("fam_adopt", "adoptive", ["a1"])
    display = resolve_parent_display(
        CHILD, [foster, adoptive], "biological", override=None, fallback_enabled=True
    )
    assert _types_drawn(display) == {"foster", "adoptive"}
    assert _parent_ids(display) == {"f1", "a1"}


def test_fallback_not_triggered_under_non_biological_show_level() -> None:
    """Fallback is a biological-show-level concern only; non_bio draws directly."""
    foster = _family("fam_foster", "foster", ["f1"])
    display = resolve_parent_display(
        CHILD, [foster], "non_biological", override=None, fallback_enabled=False
    )
    # non_biological draws foster regardless of fallback flag.
    assert _types_drawn(display) == {"foster"}


# --------------------------------------------------------------------------
# Connection type per link parentage_type (Req 3.x)
# --------------------------------------------------------------------------


def test_connection_type_chosen_per_parentage_type() -> None:
    bio = _family("fam_bio", "biological", ["dad"])
    foster = _family("fam_foster", "foster", ["f1"])
    adoptive = _family("fam_adopt", "adoptive", ["a1"])
    display = resolve_parent_display(
        CHILD, [bio, foster, adoptive], "all",
        override=None, fallback_enabled=True,
    )

    by_parent = {link.parent_id: link for link in display.links_to_draw}
    assert (
        display.connection_type_for[link_identity(by_parent["dad"])]
        == ConnectionType.PARENT_CHILD
    )
    assert (
        display.connection_type_for[link_identity(by_parent["f1"])]
        == ConnectionType.FOSTER
    )
    assert (
        display.connection_type_for[link_identity(by_parent["a1"])]
        == ConnectionType.ADOPTIVE
    )


def test_set_connection_type_matches_parentage() -> None:
    foster = _family("fam_foster", "foster", ["f1"])
    display = resolve_parent_display(
        CHILD, [foster], "non_biological", override=None, fallback_enabled=True
    )
    assert display.sets[0].connection_type == ConnectionType.FOSTER


# --------------------------------------------------------------------------
# Set cardinality and derived-vs-biological grouping (Req 3.8–3.10)
# --------------------------------------------------------------------------


def test_one_parent_derived_set_reported_as_cardinality_one() -> None:
    """A one-parent foster set is a complete single-parent derived set."""
    foster = _family("fam_foster", "foster", ["f1"])
    display = resolve_parent_display(
        CHILD, [foster], "non_biological", override=None, fallback_enabled=True
    )
    assert len(display.sets) == 1
    s = display.sets[0]
    assert s.cardinality == 1
    assert s.is_derived is True
    assert s.family_id == "fam_foster"


def test_two_parent_derived_set_reported_as_cardinality_two() -> None:
    adoptive = _family("fam_adopt", "adoptive", ["a1", "a2"])
    display = resolve_parent_display(
        CHILD, [adoptive], "non_biological", override=None, fallback_enabled=True
    )
    assert len(display.sets) == 1
    s = display.sets[0]
    assert s.cardinality == 2
    assert s.is_derived is True


def test_biological_pair_reported_as_biological_pair() -> None:
    """A biological pair is not derived, so the view keeps its placeholders."""
    bio = _family("fam_bio", "biological", ["dad", "mom"])
    display = resolve_parent_display(
        CHILD, [bio], "biological", override=None, fallback_enabled=True
    )
    assert len(display.sets) == 1
    s = display.sets[0]
    assert s.is_derived is False
    assert s.cardinality == 2
    assert s.parentage_type == "biological"


def test_single_biological_parent_still_biological_pair_not_derived() -> None:
    """A one-known-biological-parent set stays a biological pair (Req 3.10)."""
    bio = _family("fam_bio", "biological", ["dad"])
    display = resolve_parent_display(
        CHILD, [bio], "biological", override=None, fallback_enabled=True
    )
    s = display.sets[0]
    assert s.is_derived is False
    assert s.cardinality == 1


def test_multiple_derived_sets_each_grouped_separately() -> None:
    """Two foster placements of one parent each are two distinct sets."""
    foster_a = _family("fam_a", "foster", ["f1"])
    foster_b = _family("fam_b", "foster", ["f2"])
    display = resolve_parent_display(
        CHILD, [foster_a, foster_b], "non_biological",
        override=None, fallback_enabled=True,
    )
    assert len(display.sets) == 2
    assert {s.family_id for s in display.sets} == {"fam_a", "fam_b"}
    assert all(s.cardinality == 1 and s.is_derived for s in display.sets)


# --------------------------------------------------------------------------
# Edge cases
# --------------------------------------------------------------------------


def test_no_families_returns_empty_display() -> None:
    display = resolve_parent_display(
        CHILD, [], "all", override=None, fallback_enabled=True
    )
    assert display.sets == []
    assert display.links_to_draw == []
    assert display.connection_type_for == {}


def test_family_without_link_for_child_contributes_no_set() -> None:
    other = Family(
        id="fam_other",
        partners=[FamilyPartner(person_id="x", role="partner")],
        children=["someone_else"],
        parent_child_links=[
            ParentChildLink(
                child_id="someone_else", parent_id="x", parentage_type="biological"
            )
        ],
    )
    display = resolve_parent_display(
        CHILD, [other], "all", override=None, fallback_enabled=True
    )
    assert display.sets == []


def test_links_to_draw_consistent_with_sets() -> None:
    bio = _family("fam_bio", "biological", ["dad", "mom"])
    foster = _family("fam_foster", "foster", ["f1"])
    display = resolve_parent_display(
        CHILD, [bio, foster], "all", override=None, fallback_enabled=True
    )
    flattened = [link for s in display.sets for link in s.links]
    assert flattened == display.links_to_draw
    assert len(display.connection_type_for) == len(display.links_to_draw)
