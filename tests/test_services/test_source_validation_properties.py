"""Property-based tests for source validation functions.

Feature: source-management, Property 5: Källtyp name uniqueness within Leverantör
Feature: source-management, Property 2: Referenced entities cannot be deleted
Feature: source-management, Property 4: Källtyp filtering by Leverantör

Validates: Requirements 2.7, 1.6, 2.5, 2.1
"""

from __future__ import annotations

import copy

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from slaktbusken.model.source import Kalltyp, Leverantor, Source
from slaktbusken.services.source_validation import (
    delete_kalltyp,
    delete_leverantor,
    get_kalltyper_for_leverantor,
    is_kalltyp_name_unique,
    is_kalltyp_referenced,
    is_leverantor_referenced,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def kalltyp_strategy(draw: st.DrawFn) -> Kalltyp:
    """Generate a valid Kalltyp with random fields."""
    return Kalltyp(
        id=draw(st.uuids().map(str)),
        leverantor_id=draw(st.uuids().map(str)),
        name=draw(st.text(min_size=1, max_size=100).filter(lambda s: s.strip())),
        comment="",
        root_url="",
    )


# ---------------------------------------------------------------------------
# Property 5: Källtyp name uniqueness within Leverantör
# ---------------------------------------------------------------------------


class TestKalltypNameUniquenessProperty:
    """Feature: source-management, Property 5: Källtyp name uniqueness within Leverantör

    For any Leverantör that already contains a Källtyp with name N, attempting
    to create or rename another Källtyp within the same Leverantör to name N
    (case-sensitive) SHALL be rejected.

    **Validates: Requirements 2.7**
    """

    @given(kt=kalltyp_strategy())
    @settings(max_examples=100, deadline=None)
    def test_duplicate_name_same_leverantor_is_rejected(self, kt: Kalltyp) -> None:
        """When a Källtyp with a given name exists for a Leverantör,
        is_kalltyp_name_unique returns False for that same name + leverantor_id.

        Feature: source-management, Property 5: Källtyp name uniqueness within Leverantör
        **Validates: Requirements 2.7**
        """
        kalltyper = [kt]
        result = is_kalltyp_name_unique(kt.leverantor_id, kt.name, kalltyper)
        assert result is False, (
            f"Expected False (conflict) for name='{kt.name}' in "
            f"leverantor_id='{kt.leverantor_id}', but got True"
        )

    @given(kt=kalltyp_strategy(), other_name=st.text(min_size=1, max_size=100).filter(lambda s: s.strip()))
    @settings(max_examples=100, deadline=None)
    def test_different_name_same_leverantor_is_accepted(
        self, kt: Kalltyp, other_name: str
    ) -> None:
        """When the name doesn't exist for that Leverantör, returns True.

        Feature: source-management, Property 5: Källtyp name uniqueness within Leverantör
        **Validates: Requirements 2.7**
        """
        from hypothesis import assume

        assume(other_name != kt.name)

        kalltyper = [kt]
        result = is_kalltyp_name_unique(kt.leverantor_id, other_name, kalltyper)
        assert result is True, (
            f"Expected True (unique) for name='{other_name}' when existing "
            f"name is '{kt.name}', but got False"
        )

    @given(kt=kalltyp_strategy())
    @settings(max_examples=100, deadline=None)
    def test_exclude_id_allows_self_rename(self, kt: Kalltyp) -> None:
        """When using exclude_id for the Källtyp being renamed, it should return
        True (not conflict with itself).

        Feature: source-management, Property 5: Källtyp name uniqueness within Leverantör
        **Validates: Requirements 2.7**
        """
        kalltyper = [kt]
        result = is_kalltyp_name_unique(
            kt.leverantor_id, kt.name, kalltyper, exclude_id=kt.id
        )
        assert result is True, (
            f"Expected True when excluding own id='{kt.id}' for name='{kt.name}', "
            f"but got False"
        )

    @given(kt=kalltyp_strategy(), other_leverantor_id=st.uuids().map(str))
    @settings(max_examples=100, deadline=None)
    def test_same_name_different_leverantor_no_conflict(
        self, kt: Kalltyp, other_leverantor_id: str
    ) -> None:
        """Different Leverantörer with the same Källtyp name don't conflict
        (returns True).

        Feature: source-management, Property 5: Källtyp name uniqueness within Leverantör
        **Validates: Requirements 2.7**
        """
        from hypothesis import assume

        assume(other_leverantor_id != kt.leverantor_id)

        kalltyper = [kt]
        result = is_kalltyp_name_unique(other_leverantor_id, kt.name, kalltyper)
        assert result is True, (
            f"Expected True (no conflict across leverantörer) for name='{kt.name}' "
            f"in different leverantor_id='{other_leverantor_id}', but got False"
        )

    @given(kt=kalltyp_strategy())
    @settings(max_examples=100, deadline=None)
    def test_case_sensitivity_names_differing_in_case_are_unique(
        self, kt: Kalltyp
    ) -> None:
        """Case-sensitivity: names differing only in case are considered unique.

        Feature: source-management, Property 5: Källtyp name uniqueness within Leverantör
        **Validates: Requirements 2.7**
        """
        from hypothesis import assume

        # Generate a case-variant that is actually different
        swapped_name = kt.name.swapcase()
        assume(swapped_name != kt.name)

        kalltyper = [kt]
        result = is_kalltyp_name_unique(kt.leverantor_id, swapped_name, kalltyper)
        assert result is True, (
            f"Expected True (case-sensitive uniqueness) for name='{swapped_name}' "
            f"vs existing '{kt.name}', but got False"
        )


# ---------------------------------------------------------------------------
# Strategies for Property 2
# ---------------------------------------------------------------------------


@st.composite
def referenced_leverantor_scenario(draw: st.DrawFn) -> tuple[Leverantor, list[Source]]:
    """Generate a Leverantör referenced by at least one Source."""
    lev_id = draw(st.uuids().map(str))
    lev = Leverantor(
        id=lev_id,
        name=draw(st.text(min_size=1, max_size=50).filter(str.strip)),
        comment="",
    )
    # At least one source references this leverantor
    num_sources = draw(st.integers(min_value=1, max_value=5))
    sources = [
        Source(
            id=draw(st.uuids().map(str)),
            provider="",
            source_type="",
            title="Test",
            leverantor_id=lev_id,
        )
        for _ in range(num_sources)
    ]
    return lev, sources


@st.composite
def referenced_kalltyp_scenario(draw: st.DrawFn) -> tuple[Kalltyp, list[Source]]:
    """Generate a Källtyp referenced by at least one Source."""
    kt_id = draw(st.uuids().map(str))
    lev_id = draw(st.uuids().map(str))
    kt = Kalltyp(
        id=kt_id,
        leverantor_id=lev_id,
        name=draw(st.text(min_size=1, max_size=50).filter(str.strip)),
        comment="",
        root_url="",
    )
    # At least one source references this kalltyp
    num_sources = draw(st.integers(min_value=1, max_value=5))
    sources = [
        Source(
            id=draw(st.uuids().map(str)),
            provider="",
            source_type="",
            title="Test",
            kalltyp_id=kt_id,
        )
        for _ in range(num_sources)
    ]
    return kt, sources


@st.composite
def leverantor_with_referenced_kalltyp_scenario(
    draw: st.DrawFn,
) -> tuple[Leverantor, list[Kalltyp], list[Source]]:
    """Generate a Leverantör whose Källtyp is referenced by a Source.

    The Leverantör itself is NOT directly referenced, but one of its Källtyper is.
    """
    lev_id = draw(st.uuids().map(str))
    lev = Leverantor(
        id=lev_id,
        name=draw(st.text(min_size=1, max_size=50).filter(str.strip)),
        comment="",
    )
    kt_id = draw(st.uuids().map(str))
    kt = Kalltyp(
        id=kt_id,
        leverantor_id=lev_id,
        name=draw(st.text(min_size=1, max_size=50).filter(str.strip)),
        comment="",
        root_url="",
    )
    # Source references the kalltyp but NOT the leverantor directly
    source = Source(
        id=draw(st.uuids().map(str)),
        provider="",
        source_type="",
        title="Test",
        kalltyp_id=kt_id,
        leverantor_id="",  # Not referencing the leverantor directly
    )
    return lev, [kt], [source]


# ---------------------------------------------------------------------------
# Property 2: Referenced entities cannot be deleted
# ---------------------------------------------------------------------------


class TestReferencedEntitiesCannotBeDeletedProperty:
    """Feature: source-management, Property 2: Referenced entities cannot be deleted

    For any project state where a Leverantör or Källtyp is referenced by one or
    more Sources (via leverantor_id or kalltyp_id), attempting to delete that
    entity SHALL fail and the entity SHALL remain in the project data unchanged.

    **Validates: Requirements 1.6, 2.5**
    """

    @given(scenario=referenced_leverantor_scenario())
    @settings(max_examples=100, deadline=None)
    def test_referenced_leverantor_cannot_be_deleted(
        self, scenario: tuple[Leverantor, list[Source]]
    ) -> None:
        """When a Leverantör is referenced by at least one Source,
        delete_leverantor returns (False, error_msg) and the leverantorer list
        is unchanged.

        Feature: source-management, Property 2: Referenced entities cannot be deleted
        **Validates: Requirements 1.6, 2.5**
        """
        lev, sources = scenario
        leverantorer = [lev]
        kalltyper: list[Kalltyp] = []

        # Take a snapshot before attempting deletion
        leverantorer_before = copy.deepcopy(leverantorer)

        success, msg = delete_leverantor(lev.id, leverantorer, kalltyper, sources)

        assert success is False, (
            f"Expected deletion to fail for referenced leverantor '{lev.id}', "
            f"but got success=True"
        )
        assert msg != "", "Expected a non-empty error message on failed deletion"
        assert leverantorer == leverantorer_before, (
            "Leverantorer list was modified even though deletion should have failed"
        )

    @given(scenario=referenced_kalltyp_scenario())
    @settings(max_examples=100, deadline=None)
    def test_referenced_kalltyp_cannot_be_deleted(
        self, scenario: tuple[Kalltyp, list[Source]]
    ) -> None:
        """When a Källtyp is referenced by at least one Source,
        delete_kalltyp returns (False, error_msg) and the kalltyper list
        is unchanged.

        Feature: source-management, Property 2: Referenced entities cannot be deleted
        **Validates: Requirements 1.6, 2.5**
        """
        kt, sources = scenario
        kalltyper = [kt]

        # Take a snapshot before attempting deletion
        kalltyper_before = copy.deepcopy(kalltyper)

        success, msg = delete_kalltyp(kt.id, kalltyper, sources)

        assert success is False, (
            f"Expected deletion to fail for referenced kalltyp '{kt.id}', "
            f"but got success=True"
        )
        assert msg != "", "Expected a non-empty error message on failed deletion"
        assert kalltyper == kalltyper_before, (
            "Kalltyper list was modified even though deletion should have failed"
        )

    @given(scenario=leverantor_with_referenced_kalltyp_scenario())
    @settings(max_examples=100, deadline=None)
    def test_leverantor_with_referenced_kalltyp_cannot_be_deleted(
        self, scenario: tuple[Leverantor, list[Kalltyp], list[Source]]
    ) -> None:
        """When a Leverantör has Källtyper that are referenced by Sources,
        delete_leverantor also fails even if the Leverantör itself is not
        directly referenced.

        Feature: source-management, Property 2: Referenced entities cannot be deleted
        **Validates: Requirements 1.6, 2.5**
        """
        lev, kalltyper, sources = scenario
        leverantorer = [lev]

        # Verify precondition: leverantor is NOT directly referenced
        assert not is_leverantor_referenced(lev.id, sources), (
            "Precondition: leverantor should not be directly referenced"
        )
        # Verify precondition: at least one of its kalltyper IS referenced
        assert any(
            is_kalltyp_referenced(kt.id, sources)
            for kt in kalltyper
            if kt.leverantor_id == lev.id
        ), "Precondition: at least one kalltyp should be referenced"

        # Take snapshots before attempting deletion
        leverantorer_before = copy.deepcopy(leverantorer)
        kalltyper_before = copy.deepcopy(kalltyper)

        success, msg = delete_leverantor(lev.id, leverantorer, kalltyper, sources)

        assert success is False, (
            f"Expected deletion to fail for leverantor '{lev.id}' with "
            f"referenced kalltyper, but got success=True"
        )
        assert msg != "", "Expected a non-empty error message on failed deletion"
        assert leverantorer == leverantorer_before, (
            "Leverantorer list was modified even though deletion should have failed"
        )
        assert kalltyper == kalltyper_before, (
            "Kalltyper list was modified even though deletion should have failed"
        )



# ---------------------------------------------------------------------------
# Strategies for Property 4
# ---------------------------------------------------------------------------


@st.composite
def kalltyper_multi_leverantor(draw: st.DrawFn) -> tuple[list[Kalltyp], str]:
    """Generate a list of Källtyper belonging to 2-3 different Leverantörer."""
    lev_ids = [draw(st.uuids().map(str)) for _ in range(draw(st.integers(2, 3)))]
    kalltyper: list[Kalltyp] = []
    for _ in range(draw(st.integers(3, 15))):
        kt = Kalltyp(
            id=draw(st.uuids().map(str)),
            leverantor_id=draw(st.sampled_from(lev_ids)),
            name=draw(st.text(min_size=1, max_size=50).filter(str.strip)),
        )
        kalltyper.append(kt)
    target_id = draw(st.sampled_from(lev_ids))
    return kalltyper, target_id


# ---------------------------------------------------------------------------
# Property 4: Källtyp filtering by Leverantör
# ---------------------------------------------------------------------------


class TestKalltypFilteringByLeverantorProperty:
    """Feature: source-management, Property 4: Källtyp filtering by Leverantör

    For any project data containing multiple Leverantörer each with different
    sets of Källtyper, querying Källtyper for a specific Leverantör SHALL return
    exactly the Källtyper whose leverantor_id matches that Leverantör's ID,
    and no others.

    **Validates: Requirements 2.1**
    """

    @given(data=kalltyper_multi_leverantor())
    @settings(max_examples=100, deadline=None)
    def test_filtered_results_match_target_leverantor_id(
        self, data: tuple[list[Kalltyp], str]
    ) -> None:
        """All returned Källtyper have leverantor_id equal to the target.

        Feature: source-management, Property 4: Källtyp filtering by Leverantör
        **Validates: Requirements 2.1**
        """
        kalltyper, target_id = data
        result = get_kalltyper_for_leverantor(target_id, kalltyper)

        for kt in result:
            assert kt.leverantor_id == target_id, (
                f"Filtered result contains Källtyp with leverantor_id='{kt.leverantor_id}' "
                f"but target was '{target_id}'"
            )

    @given(data=kalltyper_multi_leverantor())
    @settings(max_examples=100, deadline=None)
    def test_no_results_have_different_leverantor_id(
        self, data: tuple[list[Kalltyp], str]
    ) -> None:
        """None of the returned Källtyper have a different leverantor_id.

        Feature: source-management, Property 4: Källtyp filtering by Leverantör
        **Validates: Requirements 2.1**
        """
        kalltyper, target_id = data
        result = get_kalltyper_for_leverantor(target_id, kalltyper)

        non_matching = [kt for kt in result if kt.leverantor_id != target_id]
        assert non_matching == [], (
            f"Found {len(non_matching)} Källtyper with wrong leverantor_id in result"
        )

    @given(data=kalltyper_multi_leverantor())
    @settings(max_examples=100, deadline=None)
    def test_all_matching_kalltyper_are_included(
        self, data: tuple[list[Kalltyp], str]
    ) -> None:
        """All Källtyper with the target leverantor_id appear in the result
        (nothing is missed).

        Feature: source-management, Property 4: Källtyp filtering by Leverantör
        **Validates: Requirements 2.1**
        """
        kalltyper, target_id = data
        result = get_kalltyper_for_leverantor(target_id, kalltyper)

        expected = [kt for kt in kalltyper if kt.leverantor_id == target_id]
        result_ids = {kt.id for kt in result}
        for kt in expected:
            assert kt.id in result_ids, (
                f"Källtyp id='{kt.id}' with matching leverantor_id='{target_id}' "
                f"was not included in filtered result"
            )

    @given(data=kalltyper_multi_leverantor())
    @settings(max_examples=100, deadline=None)
    def test_filtered_count_equals_expected_count(
        self, data: tuple[list[Kalltyp], str]
    ) -> None:
        """The count of filtered results equals the count of Källtyper with
        that leverantor_id in the full list.

        Feature: source-management, Property 4: Källtyp filtering by Leverantör
        **Validates: Requirements 2.1**
        """
        kalltyper, target_id = data
        result = get_kalltyper_for_leverantor(target_id, kalltyper)

        expected_count = sum(
            1 for kt in kalltyper if kt.leverantor_id == target_id
        )
        assert len(result) == expected_count, (
            f"Expected {expected_count} Källtyper for leverantor_id='{target_id}', "
            f"got {len(result)}"
        )


# ---------------------------------------------------------------------------
# Strategies for Property 3
# ---------------------------------------------------------------------------


@st.composite
def cascade_delete_scenario(draw: st.DrawFn) -> tuple[
    Leverantor, list[Kalltyp], Leverantor, Kalltyp
]:
    """Generate a Leverantör with N Källtyper, none referenced by any Source.

    Also generates an "other" Leverantör with one Källtyp that should be preserved.
    """
    lev_id = draw(st.uuids().map(str))
    lev = Leverantor(
        id=lev_id,
        name=draw(st.text(min_size=1, max_size=50).filter(str.strip)),
        comment="",
    )

    n_kalltyper = draw(st.integers(min_value=0, max_value=10))
    kalltyper = [
        Kalltyp(
            id=draw(st.uuids().map(str)),
            leverantor_id=lev_id,
            name=draw(st.text(min_size=1, max_size=50).filter(str.strip)),
            comment="",
            root_url="",
        )
        for _ in range(n_kalltyper)
    ]

    # Also generate some "other" leverantörer/källtyper that should be preserved
    other_lev_id = draw(st.uuids().map(str))
    other_lev = Leverantor(id=other_lev_id, name="Other", comment="")
    other_kt = Kalltyp(
        id=draw(st.uuids().map(str)),
        leverantor_id=other_lev_id,
        name="OtherKT",
        comment="",
        root_url="",
    )

    return lev, kalltyper, other_lev, other_kt


# ---------------------------------------------------------------------------
# Property 3: Cascade delete removes all associated Källtyper
# ---------------------------------------------------------------------------


class TestCascadeDeleteProperty:
    """Feature: source-management, Property 3: Cascade delete removes all associated Källtyper

    For any Leverantör that is not referenced by any Source but has N associated
    Källtyper (also not referenced by any Source), deleting the Leverantör SHALL
    remove the Leverantör and all N associated Källtyper from the project data,
    and the resulting project data SHALL contain no Källtyper with that Leverantör's ID.

    **Validates: Requirements 1.8**
    """

    @given(scenario=cascade_delete_scenario())
    @settings(max_examples=100, deadline=None)
    def test_leverantor_is_removed_after_cascade_delete(
        self,
        scenario: tuple[Leverantor, list[Kalltyp], Leverantor, Kalltyp],
    ) -> None:
        """After delete_leverantor succeeds, the leverantorer list no longer
        contains the deleted Leverantör.

        Feature: source-management, Property 3: Cascade delete removes all associated Källtyper
        **Validates: Requirements 1.8**
        """
        lev, target_kalltyper, other_lev, other_kt = scenario

        leverantorer = [lev, other_lev]
        kalltyper = target_kalltyper + [other_kt]
        sources: list[Source] = []  # No sources reference anything

        success, msg = delete_leverantor(lev.id, leverantorer, kalltyper, sources)

        assert success is True, (
            f"Expected deletion to succeed for unreferenced leverantor '{lev.id}', "
            f"but got failure: {msg}"
        )
        assert all(l.id != lev.id for l in leverantorer), (
            f"Leverantör '{lev.id}' still present in leverantorer after deletion"
        )

    @given(scenario=cascade_delete_scenario())
    @settings(max_examples=100, deadline=None)
    def test_all_associated_kalltyper_removed_after_cascade_delete(
        self,
        scenario: tuple[Leverantor, list[Kalltyp], Leverantor, Kalltyp],
    ) -> None:
        """After delete_leverantor succeeds, the kalltyper list contains no
        Källtyp with the deleted Leverantör's ID.

        Feature: source-management, Property 3: Cascade delete removes all associated Källtyper
        **Validates: Requirements 1.8**
        """
        lev, target_kalltyper, other_lev, other_kt = scenario

        leverantorer = [lev, other_lev]
        kalltyper = target_kalltyper + [other_kt]
        sources: list[Source] = []

        success, _ = delete_leverantor(lev.id, leverantorer, kalltyper, sources)

        assert success is True
        remaining_for_lev = [kt for kt in kalltyper if kt.leverantor_id == lev.id]
        assert remaining_for_lev == [], (
            f"Found {len(remaining_for_lev)} Källtyper still associated with "
            f"deleted leverantor '{lev.id}'"
        )

    @given(scenario=cascade_delete_scenario())
    @settings(max_examples=100, deadline=None)
    def test_other_leverantorer_and_kalltyper_preserved(
        self,
        scenario: tuple[Leverantor, list[Kalltyp], Leverantor, Kalltyp],
    ) -> None:
        """After cascade delete, other Leverantörer and their Källtyper remain
        unchanged.

        Feature: source-management, Property 3: Cascade delete removes all associated Källtyper
        **Validates: Requirements 1.8**
        """
        lev, target_kalltyper, other_lev, other_kt = scenario

        leverantorer = [lev, other_lev]
        kalltyper = target_kalltyper + [other_kt]
        sources: list[Source] = []

        success, _ = delete_leverantor(lev.id, leverantorer, kalltyper, sources)

        assert success is True
        # Other leverantör should still be present
        assert any(l.id == other_lev.id for l in leverantorer), (
            f"Other leverantör '{other_lev.id}' was incorrectly removed"
        )
        # Other källtyp should still be present
        assert any(kt.id == other_kt.id for kt in kalltyper), (
            f"Other källtyp '{other_kt.id}' was incorrectly removed"
        )
