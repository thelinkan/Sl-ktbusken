"""Property-based tests for the shared parent-display resolver.

Feature: foster-parents, Property 5: Display precedence and set cardinality

**Validates: Requirements 3.8, 4.2, 4.3, 4.4, 5.2, 5.3, 5.6, 6.2, 6.3, 6.6**

The system under test is
``slaktbusken/ui/views/parent_display.py:resolve_parent_display(...)``. This
property is expected to HOLD against the implemented module (this is NOT a
bugfix exploration test).

Property 5 encodes the resolver's three-tier decision and its set-grouping
contract, deriving the *expected* drawn sets independently from the inputs and
comparing against the resolver's output:

* Precedence (Req 5.2, 5.3, 5.6): a Connection_Override naming a set the child
  HAS wins over the Show_Level and the fallback; an override naming a set the
  child LACKS is ignored and the result equals the no-override result for the
  same Show_Level.
* Show_Level ``non_biological`` draws foster + adoptive, never biological
  (Req 4.3); ``all`` draws every present set (Req 4.4); ``biological`` draws
  biological when present else the fallback (Req 4.2).
* Fallback (Req 6.2, 6.3, 6.6): only under ``biological`` with no biological
  parents, no override, and ``fallback_enabled`` does it draw the
  non-biological sets (both foster and adoptive when both present, Req 6.6);
  otherwise it draws nothing.
* Cardinality / grouping (Req 3.8): each drawn set's ``cardinality`` equals the
  number of that family's links for the child (1 or 2); a one-parent
  foster/adoptive set has cardinality 1 and ``is_derived`` True; a biological
  family is ``is_derived`` False. The flat ``links_to_draw`` and
  ``connection_type_for`` stay consistent with the grouped ``sets``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.ui.views.parent_display import (
    link_identity,
    resolve_parent_display,
)
from slaktbusken.ui.widgets.connection_line import ConnectionType


CHILD = "child_under_test"

_SHOW_LEVELS = ("biological", "non_biological", "all")
_PARENTAGE_TYPES = ("biological", "foster", "adoptive")

#: connection type each parentage type must draw with
_EXPECTED_CONNECTION = {
    "biological": ConnectionType.PARENT_CHILD,
    "foster": ConnectionType.FOSTER,
    "adoptive": ConnectionType.ADOPTIVE,
}


# ---------------------------------------------------------------------------
# A planning record describing the single child's parent sets.
# ---------------------------------------------------------------------------


@dataclass
class DisplayPlan:
    """What families a single child has, plus the resolver inputs to test.

    ``parents_by_type`` maps a parentage type to that set's parent ids (1 or 2
    parents). A type absent from the dict means the child has no set of that
    type.
    """

    parents_by_type: dict[str, list[str]]
    show_level: str
    override: Optional[str]
    fallback_enabled: bool

    def present_types(self) -> set[str]:
        return set(self.parents_by_type)


# ---------------------------------------------------------------------------
# Strategy: generate one child's families + resolver inputs.
# ---------------------------------------------------------------------------


@st.composite
def display_plan(draw: DrawFn) -> DisplayPlan:
    """Draw a :class:`DisplayPlan` for a single child.

    Independently includes/excludes a biological, a foster, and an adoptive set
    (each with one or two parents) so every combination of present sets is
    reachable. The override is drawn from the three parentage values, ``None``,
    *and* values for sets the child may or may not have (so "missing-set
    override" cases arise naturally).
    """
    parents_by_type: dict[str, list[str]] = {}
    counter = 0
    for ptype in _PARENTAGE_TYPES:
        if draw(st.booleans()):
            n_parents = draw(st.integers(min_value=1, max_value=2))
            parents: list[str] = []
            for _ in range(n_parents):
                parents.append(f"{ptype}_parent_{counter}")
                counter += 1
            parents_by_type[ptype] = parents

    show_level = draw(st.sampled_from(_SHOW_LEVELS))
    # Override: any parentage value (present or absent for this child) or None.
    override = draw(st.sampled_from([None, "biological", "foster", "adoptive"]))
    fallback_enabled = draw(st.booleans())

    return DisplayPlan(
        parents_by_type=parents_by_type,
        show_level=show_level,
        override=override,
        fallback_enabled=fallback_enabled,
    )


def _build_families(plan: DisplayPlan) -> list[Family]:
    """Turn a plan into the ``parent_families`` list the resolver consumes."""
    families: list[Family] = []
    for ptype, parents in plan.parents_by_type.items():
        families.append(
            Family(
                id=f"fam_{ptype}",
                partners=[
                    FamilyPartner(person_id=pid, role="partner") for pid in parents
                ],
                children=[CHILD],
                parent_child_links=[
                    ParentChildLink(
                        child_id=CHILD, parent_id=pid, parentage_type=ptype
                    )
                    for pid in parents
                ],
            )
        )
    return families


def _expected_drawn_types(plan: DisplayPlan) -> set[str]:
    """Independently derive which parentage types the resolver should draw.

    Mirrors the specification's precedence rules without reusing the resolver's
    internals.
    """
    present = plan.present_types()

    # Precedence 1: override for a set the child HAS wins outright (Req 5.2).
    if plan.override is not None and plan.override in present:
        return {plan.override}
    # An override for a missing set is ignored (Req 5.6) -> fall through.

    # Precedence 2: the Show_Level (Req 4.2-4.4).
    if plan.show_level == "all":
        return set(present)
    if plan.show_level == "non_biological":
        return present & {"foster", "adoptive"}

    # "biological" (and any unknown value) shows biological if present.
    if "biological" in present:
        return {"biological"}

    # Precedence 3: fallback, only here (Req 6.2, 6.6).
    if plan.fallback_enabled:
        non_biological = present & {"foster", "adoptive"}
        if non_biological:
            return non_biological

    return set()


# ---------------------------------------------------------------------------
# Property 5
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(plan=display_plan())
def test_display_precedence_and_set_cardinality(plan: DisplayPlan) -> None:
    """Feature: foster-parents, Property 5: precedence + set cardinality.

    **Validates: Requirements 3.8, 4.2, 4.3, 4.4, 5.2, 5.3, 5.6, 6.2, 6.3, 6.6**
    """
    families = _build_families(plan)
    display = resolve_parent_display(
        CHILD,
        families,
        plan.show_level,
        override=plan.override,
        fallback_enabled=plan.fallback_enabled,
    )

    expected_types = _expected_drawn_types(plan)
    drawn_types = {s.parentage_type for s in display.sets}

    # --- Precedence / Show_Level / fallback: the right *types* are drawn. ---
    assert drawn_types == expected_types

    # non_biological never draws biological via the Show_Level path (Req 4.3):
    # biological may only appear when a present-set "biological" override forced
    # it, never from the Show_Level itself.
    if plan.show_level == "non_biological" and "biological" in drawn_types:
        assert plan.override == "biological" and "biological" in plan.present_types()

    # --- Missing-set override equals the no-override result (Req 5.6). ------
    if plan.override is not None and plan.override not in plan.present_types():
        no_override = resolve_parent_display(
            CHILD,
            families,
            plan.show_level,
            override=None,
            fallback_enabled=plan.fallback_enabled,
        )
        assert {s.parentage_type for s in no_override.sets} == drawn_types
        assert [link_identity(l) for l in no_override.links_to_draw] == [
            link_identity(l) for l in display.links_to_draw
        ]

    # --- Present-set override wins over everything (Req 5.2). ---------------
    if plan.override is not None and plan.override in plan.present_types():
        assert drawn_types == {plan.override}

    # --- Per-set cardinality and derived/biological nature (Req 3.8). -------
    for parent_set in display.sets:
        expected_parents = plan.parents_by_type[parent_set.parentage_type]
        assert parent_set.cardinality == len(expected_parents)
        assert parent_set.cardinality == len(parent_set.links)
        assert parent_set.cardinality in (1, 2)
        if parent_set.parentage_type == "biological":
            assert parent_set.is_derived is False
        else:
            assert parent_set.is_derived is True
        # A one-parent foster/adoptive set is a complete single-parent set.
        if parent_set.is_derived and parent_set.cardinality == 1:
            assert len(parent_set.links) == 1

    # --- Consistency invariants across the grouped and flat views. ----------
    flattened = [link for s in display.sets for link in s.links]
    assert flattened == display.links_to_draw

    # One connection-type entry per drawn link, keyed by link_identity.
    assert len(display.connection_type_for) == len(display.links_to_draw)
    for parent_set in display.sets:
        for link in parent_set.links:
            key = link_identity(link)
            assert display.connection_type_for[key] == parent_set.connection_type
            # The set's connection type matches its parentage type, and so does
            # every link drawn within it.
            assert (
                parent_set.connection_type
                == _EXPECTED_CONNECTION[link.parentage_type]
            )
            assert parent_set.connection_type == _EXPECTED_CONNECTION[
                parent_set.parentage_type
            ]
