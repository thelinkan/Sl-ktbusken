"""Property-based tests for the Parentage_Sync_Service.

Feature: foster-parents, Property 1: Sync idempotence
Feature: foster-parents, Property 2: Foster/adoptive-only reconciliation

Validates: Requirements 2.2, 2.8

The system under test is
``slaktbusken/services/foster_sync.py:sync_parentage_links(project)``. Both
properties are expected to HOLD against the implemented module (these are not
bugfix exploration tests).

Property 1 (idempotence, Req 2.8): running ``sync_parentage_links`` twice in
succession with no intervening change leaves the project's derived links
identical to running it once.

Property 2 (foster/adoptive-only reconciliation, Req 2.2): sync leaves every
biological link and every link whose parentage is neither ``"foster"`` nor
``"adoptive"`` unchanged.
"""

from __future__ import annotations

import copy

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.family import Family, ParentChildLink
from slaktbusken.model.project import ProjectData
from slaktbusken.services.foster_sync import sync_parentage_links

from tests.test_foster.foster_strategies import (
    DERIVED_PARENTAGE,
    foster_project,
    foster_project_with_placement,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _family_fingerprint(family: Family) -> tuple:
    """An order-insensitive, identity-independent fingerprint of a family.

    Captures everything the sync is responsible for: which parents partner the
    family, which children belong to it, the derived links, and the recorded
    event ids. Lists are sorted so that a mere reordering (which is not a
    semantic change) does not make two equal families compare unequal.
    """
    partners = sorted((p.person_id, p.role) for p in family.partners)
    children = sorted(family.children)
    links = sorted(
        (link.child_id, link.parent_id, link.parentage_type)
        for link in family.parent_child_links
    )
    event_ids = sorted(family.event_ids)
    return (family.id, tuple(partners), tuple(children), tuple(links), tuple(event_ids))


def _project_fingerprint(project: ProjectData) -> frozenset:
    """A whole-project fingerprint over its families, order-insensitive."""
    return frozenset(_family_fingerprint(family) for family in project.families)


def _non_derived_links(project: ProjectData) -> list[tuple]:
    """Every link whose parentage is neither ``"foster"`` nor ``"adoptive"``.

    Returned as a sorted list of ``(parentage_type, child_id, parent_id)`` tuples
    so two snapshots can be compared regardless of family or link ordering.
    """
    out: list[tuple] = []
    for family in project.families:
        for link in family.parent_child_links:
            if link.parentage_type not in DERIVED_PARENTAGE:
                out.append((link.parentage_type, link.child_id, link.parent_id))
    return sorted(out)


# ---------------------------------------------------------------------------
# Property 1: Sync idempotence (Requirement 2.8)
# ---------------------------------------------------------------------------


class TestSyncIdempotence:
    """Feature: foster-parents, Property 1: Sync idempotence

    ``sync_parentage_links`` applied twice in succession, with no intervening
    change, leaves the project's derived links identical to applying it once.

    **Validates: Requirements 2.8**
    """

    @given(fp=foster_project())
    @settings(max_examples=100, deadline=None)
    def test_sync_twice_equals_once(self, fp) -> None:
        """Property 1: sync twice == sync once.

        Feature: foster-parents, Property 1: Sync idempotence
        **Validates: Requirements 2.8**
        """
        once = copy.deepcopy(fp.project)
        twice = copy.deepcopy(fp.project)

        sync_parentage_links(once)

        sync_parentage_links(twice)
        sync_parentage_links(twice)

        assert _project_fingerprint(twice) == _project_fingerprint(once), (
            "Running sync twice produced a different project state than once"
        )

    @given(fp=foster_project_with_placement())
    @settings(max_examples=100, deadline=None)
    def test_sync_twice_equals_once_with_placement(self, fp) -> None:
        """Property 1 on projects guaranteed to have a derivable placement.

        Feature: foster-parents, Property 1: Sync idempotence
        **Validates: Requirements 2.8**
        """
        once = copy.deepcopy(fp.project)
        twice = copy.deepcopy(fp.project)

        sync_parentage_links(once)

        sync_parentage_links(twice)
        sync_parentage_links(twice)

        assert _project_fingerprint(twice) == _project_fingerprint(once)


# ---------------------------------------------------------------------------
# Property 2: Foster/adoptive-only reconciliation (Requirement 2.2)
# ---------------------------------------------------------------------------


class TestFosterAdoptiveOnlyReconciliation:
    """Feature: foster-parents, Property 2: Foster/adoptive-only reconciliation

    ``sync_parentage_links`` never changes any biological link or any link whose
    parentage is neither ``"foster"`` nor ``"adoptive"``.

    **Validates: Requirements 2.2**
    """

    @given(fp=foster_project())
    @settings(max_examples=100, deadline=None)
    def test_non_derived_links_unchanged(self, fp) -> None:
        """Property 2: every non-foster/non-adoptive link survives sync intact.

        Feature: foster-parents, Property 2: Foster/adoptive-only reconciliation
        **Validates: Requirements 2.2**
        """
        before = _non_derived_links(fp.project)

        sync_parentage_links(fp.project)

        after = _non_derived_links(fp.project)

        assert after == before, (
            "sync_parentage_links altered links it must leave untouched.\n"
            f"  before: {before}\n"
            f"  after:  {after}"
        )

    @given(fp=foster_project_with_placement())
    @settings(max_examples=100, deadline=None)
    def test_non_derived_links_unchanged_with_placement(self, fp) -> None:
        """Property 2 on projects guaranteed to have a derivable placement.

        Feature: foster-parents, Property 2: Foster/adoptive-only reconciliation
        **Validates: Requirements 2.2**
        """
        before = _non_derived_links(fp.project)

        sync_parentage_links(fp.project)

        after = _non_derived_links(fp.project)

        assert after == before
