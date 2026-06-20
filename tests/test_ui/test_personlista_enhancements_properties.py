"""Property tests for personlista-enhancements feature.

Feature: personlista-enhancements, Property 5: Column visibility round-trip persistence

**Validates: Requirements 2.4**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.persistence.app_settings_io import AppSettings, AppSettingsService, ColumnVisibility


class TestPropertyColumnVisibilityRoundTrip:
    """Property 5: Column visibility round-trip persistence.

    # Feature: personlista-enhancements, Property 5: Column visibility round-trip persistence

    For any ColumnVisibility configuration (arbitrary combination of True/False
    for each column), serializing to JSON and deserializing back SHALL produce
    an identical ColumnVisibility instance.

    **Validates: Requirements 2.4**
    """

    @given(
        titel=st.booleans(),
        yrke=st.booleans(),
        kluster=st.booleans(),
        dna_company=st.booleans(),
    )
    @settings(max_examples=100)
    def test_column_visibility_serialize_deserialize_round_trip(
        self,
        titel: bool,
        yrke: bool,
        kluster: bool,
        dna_company: bool,
    ) -> None:
        """For any ColumnVisibility config, JSON round-trip produces identical instance.

        # Feature: personlista-enhancements, Property 5: Column visibility round-trip persistence
        """
        original = ColumnVisibility(
            titel=titel,
            yrke=yrke,
            kluster=kluster,
            dna_company=dna_company,
        )

        # Wrap in AppSettings for serialization
        app_settings = AppSettings(column_visibility=original)

        svc = AppSettingsService()

        # Serialize then deserialize
        serialized = svc._serialize(app_settings)
        deserialized = svc._deserialize(serialized)

        # Assert the deserialized ColumnVisibility is identical to the original
        assert deserialized.column_visibility == original
        assert deserialized.column_visibility.titel == original.titel
        assert deserialized.column_visibility.yrke == original.yrke
        assert deserialized.column_visibility.kluster == original.kluster
        assert deserialized.column_visibility.dna_company == original.dna_company


# ---------------------------------------------------------------------------
# Property tests 6-9: Name and cluster filtering
# ---------------------------------------------------------------------------

from slaktbusken.model.person import Name
from slaktbusken.ui.person_list_panel import FilterCriteria, PersonDisplayInfo, filter_persons


# Strategy: non-empty text that is not whitespace-only (for filter strings)
_non_empty_filter_text = st.text(min_size=1, max_size=20).filter(lambda s: s.strip() != "")

# Strategy: arbitrary name strings (may include asterisks for given)
_given_text = st.text(min_size=0, max_size=30, alphabet=st.characters(categories=("L", "N", "P", "Z")))
_surname_text = st.text(min_size=0, max_size=30, alphabet=st.characters(categories=("L", "N", "P", "Z")))

# Strategy: a Name record
_name_st = st.builds(
    Name,
    type=st.sampled_from(["birth", "married", "adopted", ""]),
    given=_given_text,
    surname=_surname_text,
)


def _make_person(person_id: str, names: list[Name], cluster_names: set[str] | None = None) -> PersonDisplayInfo:
    """Helper to create a PersonDisplayInfo from Name records."""
    first_given = names[0].given.replace("*", "") if names else ""
    first_surname = names[0].surname if names else ""
    return PersonDisplayInfo(
        person_id=person_id,
        given=first_given,
        surname=first_surname,
        title="",
        birth_year="",
        death_year="",
        marriage_year="",
        event_types=set(),
        parish_names=set(),
        cluster_names=cluster_names or set(),
        name_count=len(names),
        all_names=[(n.type, n.given, n.surname) for n in names],
    )


class TestPropertyMultiNameGivenFilter:
    """Property 6: Multi-name given name filter.

    # Feature: personlista-enhancements, Property 6: Multi-name given name filter

    For any person with one or more Name records and a non-empty given name
    filter string, the person SHALL be included in the filtered results if and
    only if at least one of the person's Name records has a given field (with
    asterisk markers stripped) that contains the filter string as a
    case-insensitive substring.

    **Validates: Requirements 6.1, 6.3, 6.4**
    """

    @given(
        names=st.lists(_name_st, min_size=1, max_size=5),
        filter_str=_non_empty_filter_text,
    )
    @settings(max_examples=100)
    def test_given_name_filter_if_and_only_if(
        self,
        names: list[Name],
        filter_str: str,
    ) -> None:
        """Person included iff any Name.given (asterisk-stripped) contains filter as case-insensitive substring.

        # Feature: personlista-enhancements, Property 6: Multi-name given name filter
        """
        person = _make_person("p1", names)
        all_persons_names = {"p1": names}
        criteria = FilterCriteria(given=filter_str)

        result = filter_persons([person], criteria, all_persons_names=all_persons_names)

        # Expected: at least one name record has given (stripped of *) containing
        # filter_str as case-insensitive substring
        filter_lower = filter_str.strip().lower()
        expected_match = any(
            filter_lower in name.given.replace("*", "").lower()
            for name in names
        )

        if expected_match:
            assert person in result, (
                f"Person should be included: filter={filter_str!r}, "
                f"givens={[n.given for n in names]}"
            )
        else:
            assert person not in result, (
                f"Person should NOT be included: filter={filter_str!r}, "
                f"givens={[n.given for n in names]}"
            )


class TestPropertyMultiNameSurnameFilter:
    """Property 7: Multi-name surname filter.

    # Feature: personlista-enhancements, Property 7: Multi-name surname filter

    For any person with one or more Name records and a non-empty surname filter
    string, the person SHALL be included in the filtered results if and only if
    at least one of the person's Name records has a surname field that contains
    the filter string as a case-insensitive substring.

    **Validates: Requirements 6.2, 6.3, 6.4**
    """

    @given(
        names=st.lists(_name_st, min_size=1, max_size=5),
        filter_str=_non_empty_filter_text,
    )
    @settings(max_examples=100)
    def test_surname_filter_if_and_only_if(
        self,
        names: list[Name],
        filter_str: str,
    ) -> None:
        """Person included iff any Name.surname contains filter as case-insensitive substring.

        # Feature: personlista-enhancements, Property 7: Multi-name surname filter
        """
        person = _make_person("p1", names)
        all_persons_names = {"p1": names}
        criteria = FilterCriteria(surname=filter_str)

        result = filter_persons([person], criteria, all_persons_names=all_persons_names)

        filter_lower = filter_str.strip().lower()
        expected_match = any(
            filter_lower in name.surname.lower()
            for name in names
        )

        if expected_match:
            assert person in result, (
                f"Person should be included: filter={filter_str!r}, "
                f"surnames={[n.surname for n in names]}"
            )
        else:
            assert person not in result, (
                f"Person should NOT be included: filter={filter_str!r}, "
                f"surnames={[n.surname for n in names]}"
            )


class TestPropertyCombinedGivenSurnameFilter:
    """Property 8: Combined given and surname filter independence.

    # Feature: personlista-enhancements, Property 8: Combined given and surname filter independence

    For any person with multiple Name records and both a non-empty given name
    filter and a non-empty surname filter active, the person SHALL be included
    if and only if (any Name record satisfies the given name filter) AND (any
    Name record satisfies the surname filter) — evaluated independently across
    all name records.

    **Validates: Requirements 6.5**
    """

    @given(
        names=st.lists(_name_st, min_size=2, max_size=5),
        given_filter=_non_empty_filter_text,
        surname_filter=_non_empty_filter_text,
    )
    @settings(max_examples=100)
    def test_combined_filter_independence(
        self,
        names: list[Name],
        given_filter: str,
        surname_filter: str,
    ) -> None:
        """Person included iff (any Name matches given) AND (any Name matches surname) independently.

        # Feature: personlista-enhancements, Property 8: Combined given and surname filter independence
        """
        person = _make_person("p1", names)
        all_persons_names = {"p1": names}
        criteria = FilterCriteria(given=given_filter, surname=surname_filter)

        result = filter_persons([person], criteria, all_persons_names=all_persons_names)

        given_lower = given_filter.strip().lower()
        surname_lower = surname_filter.strip().lower()

        given_match = any(
            given_lower in name.given.replace("*", "").lower()
            for name in names
        )
        surname_match = any(
            surname_lower in name.surname.lower()
            for name in names
        )
        expected_match = given_match and surname_match

        if expected_match:
            assert person in result, (
                f"Person should be included: given_filter={given_filter!r}, "
                f"surname_filter={surname_filter!r}, names={[(n.given, n.surname) for n in names]}"
            )
        else:
            assert person not in result, (
                f"Person should NOT be included: given_filter={given_filter!r}, "
                f"surname_filter={surname_filter!r}, names={[(n.given, n.surname) for n in names]}"
            )


class TestPropertyClusterFilterAndLogic:
    """Property 9: Cluster filter AND logic.

    # Feature: personlista-enhancements, Property 9: Cluster filter AND logic

    For any set of persons with cluster memberships and a non-empty cluster
    filter string, filter_persons SHALL return exactly those persons who have
    at least one cluster whose name contains the filter string as a
    case-insensitive substring, intersected with persons matching all other
    active criteria.

    **Validates: Requirements 5.2, 5.3**
    """

    @given(
        cluster_sets=st.lists(
            st.frozensets(
                st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "N"))).map(str.lower),
                min_size=0,
                max_size=4,
            ),
            min_size=1,
            max_size=8,
        ),
        filter_str=_non_empty_filter_text,
    )
    @settings(max_examples=100)
    def test_cluster_filter_returns_matching_persons(
        self,
        cluster_sets: list[frozenset[str]],
        filter_str: str,
    ) -> None:
        """filter_persons returns exactly persons with a cluster name containing filter substring.

        # Feature: personlista-enhancements, Property 9: Cluster filter AND logic
        """
        # Create persons with different cluster memberships
        persons = []
        for i, clusters in enumerate(cluster_sets):
            p = PersonDisplayInfo(
                person_id=f"p{i}",
                given="Test",
                surname="Person",
                title="",
                birth_year="",
                death_year="",
                marriage_year="",
                event_types=set(),
                parish_names=set(),
                cluster_names=set(clusters),
            )
            persons.append(p)

        criteria = FilterCriteria(cluster=filter_str)
        result = filter_persons(persons, criteria)

        filter_lower = filter_str.strip().lower()

        for person, clusters in zip(persons, cluster_sets):
            should_match = any(filter_lower in cn for cn in clusters)
            if should_match:
                assert person in result, (
                    f"Person {person.person_id} should be included: "
                    f"filter={filter_str!r}, clusters={clusters}"
                )
            else:
                assert person not in result, (
                    f"Person {person.person_id} should NOT be included: "
                    f"filter={filter_str!r}, clusters={clusters}"
                )



# ---------------------------------------------------------------------------
# Property test 11: Multiple names tooltip format
# ---------------------------------------------------------------------------

from slaktbusken.ui.person_list_panel import format_names_tooltip


# Strategy: name type strings (may be empty)
_name_type_st = st.text(min_size=0, max_size=15, alphabet=st.characters(categories=("L", "N")))
# Strategy: given/surname components (may be empty)
_tooltip_given_st = st.text(min_size=0, max_size=20, alphabet=st.characters(categories=("L", "N", "Z")))
_tooltip_surname_st = st.text(min_size=0, max_size=20, alphabet=st.characters(categories=("L", "N", "Z")))

# Strategy: a name tuple (type, given, surname)
_name_tuple_st = st.tuples(_name_type_st, _tooltip_given_st, _tooltip_surname_st)


class TestPropertyMultipleNamesTooltipFormat:
    """Property 11: Multiple names tooltip format.

    # Feature: personlista-enhancements, Property 11: Multiple names tooltip format

    For any person with more than one Name record, the tooltip text SHALL
    contain one line per Name in format "type: given surname" (omitting empty
    components), with lines in stored order.

    **Validates: Requirements 7.2**
    """

    @given(
        all_names=st.lists(_name_tuple_st, min_size=2, max_size=8),
    )
    @settings(max_examples=100)
    def test_tooltip_line_count_matches_names(
        self,
        all_names: list[tuple[str, str, str]],
    ) -> None:
        """Tooltip produces exactly N lines, one per name tuple.

        # Feature: personlista-enhancements, Property 11: Multiple names tooltip format
        """
        result = format_names_tooltip(all_names)
        lines = result.split("\n")
        assert len(lines) == len(all_names), (
            f"Expected {len(all_names)} lines, got {len(lines)}. "
            f"Input: {all_names}, Output: {result!r}"
        )

    @given(
        all_names=st.lists(_name_tuple_st, min_size=2, max_size=8),
    )
    @settings(max_examples=100)
    def test_tooltip_line_format_and_order(
        self,
        all_names: list[tuple[str, str, str]],
    ) -> None:
        """Each line matches expected format and lines are in input order.

        # Feature: personlista-enhancements, Property 11: Multiple names tooltip format
        """
        result = format_names_tooltip(all_names)
        lines = result.split("\n")

        for i, (name_type, given, surname) in enumerate(all_names):
            line = lines[i]

            # Build expected name portion (omitting empty components)
            name_parts: list[str] = []
            if given:
                name_parts.append(given)
            if surname:
                name_parts.append(surname)
            name_str = " ".join(name_parts)

            if name_type:
                expected = f"{name_type}: {name_str}"
            else:
                expected = name_str

            assert line == expected, (
                f"Line {i} mismatch: expected {expected!r}, got {line!r}. "
                f"Input tuple: ({name_type!r}, {given!r}, {surname!r})"
            )
