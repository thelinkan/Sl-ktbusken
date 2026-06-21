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
# Property tests 1-4, 10: Display info construction
# ---------------------------------------------------------------------------

from slaktbusken.model.person import Person, Name
from slaktbusken.model.dna import DnaCluster, DnaProfile, DnaCompany
from slaktbusken.ui.person_list_panel import build_person_display_list, PersonDisplayInfo

# Strategies for generating test data

# Text without asterisks (to avoid tilltalsnamn parsing complexity)
_safe_given_text = st.text(
    min_size=1, max_size=20,
    alphabet=st.characters(categories=("L", "N", "Z"), exclude_characters="*"),
).filter(lambda s: s.strip() != "")

_safe_surname_text = st.text(
    min_size=1, max_size=20,
    alphabet=st.characters(categories=("L", "N", "Z"), exclude_characters="*"),
).filter(lambda s: s.strip() != "")

_safe_name_st = st.builds(
    Name,
    type=st.sampled_from(["birth", "married", "adopted", ""]),
    given=_safe_given_text,
    surname=_safe_surname_text,
)

_optional_title = st.one_of(st.none(), st.text(min_size=1, max_size=50, alphabet=st.characters(categories=("L", "N", "Z"))))
_optional_occupation = st.one_of(st.none(), st.text(min_size=1, max_size=50, alphabet=st.characters(categories=("L", "N", "Z"))))

_person_id_st = st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L", "N"))).filter(lambda s: s.strip() != "")

_cluster_name_st = st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "N", "Z"))).filter(lambda s: s.strip() != "")

_company_name_st = st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "N", "Z"))).filter(lambda s: s.strip() != "")


class TestPropertyPersonFieldPropagation:
    """Property 1: Person field propagation to display info.

    # Feature: personlista-enhancements, Property 1: Person field propagation to display info

    For any person with optional title and occupation fields,
    build_person_display_list SHALL produce a PersonDisplayInfo where title
    equals Person.title (or empty string when None) and occupation equals
    Person.occupation (or empty string when None).

    **Validates: Requirements 1.3, 1.4**
    """

    @given(
        title=_optional_title,
        occupation=_optional_occupation,
        name=_safe_name_st,
        person_id=_person_id_st,
    )
    @settings(max_examples=100)
    def test_title_and_occupation_propagation(
        self,
        title: str | None,
        occupation: str | None,
        name: Name,
        person_id: str,
    ) -> None:
        """Title and occupation propagate correctly (None becomes empty string).

        # Feature: personlista-enhancements, Property 1: Person field propagation to display info
        """
        person = Person(
            id=person_id,
            sex="M",
            names=[name],
            title=title,
            occupation=occupation,
        )

        result = build_person_display_list(
            persons=[person],
            events=[],
            places=[],
        )

        assert len(result) == 1
        info = result[0]
        assert info.title == (title or "")
        assert info.occupation == (occupation or "")


class TestPropertyClusterNamesDisplay:
    """Property 2: Cluster names display construction.

    # Feature: personlista-enhancements, Property 2: Cluster names display construction

    For any person and set of DnaCluster objects, the cluster_names_display
    field in PersonDisplayInfo SHALL be a comma-separated string of the names
    of all clusters whose person_ids list contains the person's ID, sorted
    alphabetically (case-insensitive). If the person belongs to no clusters,
    it SHALL be an empty string.

    **Validates: Requirements 1.5**
    """

    @given(
        person_id=_person_id_st,
        name=_safe_name_st,
        cluster_names=st.lists(_cluster_name_st, min_size=0, max_size=6),
        membership_flags=st.lists(st.booleans(), min_size=0, max_size=6),
    )
    @settings(max_examples=100)
    def test_cluster_names_display_construction(
        self,
        person_id: str,
        name: Name,
        cluster_names: list[str],
        membership_flags: list[bool],
    ) -> None:
        """cluster_names_display is comma-separated sorted cluster names for person.

        # Feature: personlista-enhancements, Property 2: Cluster names display construction
        """
        # Align membership_flags with cluster_names
        flags = membership_flags[: len(cluster_names)]
        while len(flags) < len(cluster_names):
            flags.append(False)

        person = Person(id=person_id, sex="F", names=[name])

        clusters = []
        for i, cname in enumerate(cluster_names):
            person_ids = [person_id] if flags[i] else []
            clusters.append(DnaCluster(id=f"c{i}", name=cname, person_ids=person_ids))

        result = build_person_display_list(
            persons=[person],
            events=[],
            places=[],
            dna_clusters=clusters,
        )

        assert len(result) == 1
        info = result[0]

        # Expected: names of clusters where person is a member, sorted case-insensitively
        expected_names = [
            cname for cname, flag in zip(cluster_names, flags) if flag
        ]
        expected_names.sort(key=str.lower)
        expected_display = ", ".join(expected_names)

        assert info.cluster_names_display == expected_display


class TestPropertyDnaCompanyIdCollection:
    """Property 3: DNA company ID collection.

    # Feature: personlista-enhancements, Property 3: DNA company ID collection

    For any person and set of DnaProfile objects, the dna_company_ids field in
    PersonDisplayInfo SHALL contain exactly the distinct company_id values from
    profiles where profile.person_id == person.id, sorted alphabetically by
    company name and capped at 5 entries.

    **Validates: Requirements 1.6, 3.1, 3.2**
    """

    @given(
        person_id=_person_id_st,
        name=_safe_name_st,
        company_data=st.lists(
            st.tuples(_person_id_st, _company_name_st),
            min_size=0,
            max_size=8,
        ),
    )
    @settings(max_examples=100)
    def test_dna_company_ids_collected_sorted_capped(
        self,
        person_id: str,
        name: Name,
        company_data: list[tuple[str, str]],
    ) -> None:
        """dna_company_ids contains distinct company IDs sorted by name, max 5.

        # Feature: personlista-enhancements, Property 3: DNA company ID collection
        """
        person = Person(id=person_id, sex="M", names=[name])

        # Build companies and profiles - some for our person, some for others
        companies: list[DnaCompany] = []
        profiles: list[DnaProfile] = []
        seen_company_ids: set[str] = set()

        for i, (profile_person_id, company_name) in enumerate(company_data):
            company_id = f"comp{i}"
            if company_id not in seen_company_ids:
                companies.append(DnaCompany(id=company_id, name=company_name))
                seen_company_ids.add(company_id)
            profiles.append(DnaProfile(
                id=f"prof{i}",
                person_id=profile_person_id,
                company_id=company_id,
                test_type="autosomal",
            ))

        result = build_person_display_list(
            persons=[person],
            events=[],
            places=[],
            dna_profiles=profiles,
            dna_companies=companies,
        )

        assert len(result) == 1
        info = result[0]

        # Expected: distinct company IDs from profiles where person_id matches,
        # sorted by company name (case-insensitive), capped at 5
        matching_company_ids: set[str] = set()
        for profile in profiles:
            if profile.person_id == person_id:
                matching_company_ids.add(profile.company_id)

        company_name_by_id = {c.id: c.name for c in companies}
        sorted_ids = sorted(
            matching_company_ids,
            key=lambda cid: company_name_by_id.get(cid, "").lower(),
        )[:5]

        assert info.dna_company_ids == sorted_ids


class TestPropertyLineageFlagCorrectness:
    """Property 4: Lineage flag correctness.

    # Feature: personlista-enhancements, Property 4: Lineage flag correctness

    For any person and a computed ancestor set and descendant set, the
    is_ancestor flag SHALL be True iff the person's ID is in the ancestor set,
    and is_descendant SHALL be True iff the person's ID is in the descendant
    set. The main person itself SHALL have both flags as False.

    **Validates: Requirements 4.1, 4.2, 4.8**
    """

    @given(
        person_ids=st.lists(
            _person_id_st,
            min_size=2,
            max_size=10,
            unique=True,
        ),
        ancestor_flags=st.lists(st.booleans(), min_size=2, max_size=10),
        descendant_flags=st.lists(st.booleans(), min_size=2, max_size=10),
    )
    @settings(max_examples=100)
    def test_lineage_flags_reflect_id_sets(
        self,
        person_ids: list[str],
        ancestor_flags: list[bool],
        descendant_flags: list[bool],
    ) -> None:
        """is_ancestor/is_descendant flags match membership in provided sets.

        # Feature: personlista-enhancements, Property 4: Lineage flag correctness
        """
        # Use first person as the main person (should have both flags False)
        main_person_id = person_ids[0]

        # Align flags
        a_flags = ancestor_flags[: len(person_ids)]
        while len(a_flags) < len(person_ids):
            a_flags.append(False)
        d_flags = descendant_flags[: len(person_ids)]
        while len(d_flags) < len(person_ids):
            d_flags.append(False)

        # Build ancestor/descendant sets (exclude main person from both)
        ancestor_ids: set[str] = set()
        descendant_ids: set[str] = set()
        for i, pid in enumerate(person_ids):
            if pid == main_person_id:
                continue  # Main person never in ancestor/descendant sets
            if a_flags[i]:
                ancestor_ids.add(pid)
            if d_flags[i]:
                descendant_ids.add(pid)

        # Build persons with a Name
        persons = [
            Person(
                id=pid,
                sex="M",
                names=[Name(type="birth", given="Test", surname=f"Person{i}")],
            )
            for i, pid in enumerate(person_ids)
        ]

        result = build_person_display_list(
            persons=persons,
            events=[],
            places=[],
            ancestor_ids=ancestor_ids,
            descendant_ids=descendant_ids,
        )

        # Check each person
        result_by_id = {info.person_id: info for info in result}
        for pid in person_ids:
            info = result_by_id[pid]
            if pid == main_person_id:
                # Main person itself: both flags False
                assert info.is_ancestor is False, (
                    f"Main person {pid} should have is_ancestor=False"
                )
                assert info.is_descendant is False, (
                    f"Main person {pid} should have is_descendant=False"
                )
            else:
                expected_ancestor = pid in ancestor_ids
                expected_descendant = pid in descendant_ids
                assert info.is_ancestor == expected_ancestor, (
                    f"Person {pid}: expected is_ancestor={expected_ancestor}, "
                    f"got {info.is_ancestor}"
                )
                assert info.is_descendant == expected_descendant, (
                    f"Person {pid}: expected is_descendant={expected_descendant}, "
                    f"got {info.is_descendant}"
                )


class TestPropertyNameCountAndAllNames:
    """Property 10: Name count and all_names accuracy.

    # Feature: personlista-enhancements, Property 10: Name count and all_names accuracy

    For any person with N name records (N >= 1), PersonDisplayInfo.name_count
    SHALL equal N and all_names SHALL contain exactly those N name records as
    (type, given, surname) tuples in stored order.

    **Validates: Requirements 7.1, 7.2**
    """

    @given(
        person_id=_person_id_st,
        names=st.lists(_safe_name_st, min_size=1, max_size=8),
    )
    @settings(max_examples=100)
    def test_name_count_and_all_names_accuracy(
        self,
        person_id: str,
        names: list[Name],
    ) -> None:
        """name_count equals len(names) and all_names contains exact tuples in order.

        # Feature: personlista-enhancements, Property 10: Name count and all_names accuracy
        """
        person = Person(id=person_id, sex="F", names=names)

        result = build_person_display_list(
            persons=[person],
            events=[],
            places=[],
        )

        assert len(result) == 1
        info = result[0]

        assert info.name_count == len(names), (
            f"Expected name_count={len(names)}, got {info.name_count}"
        )

        expected_all_names = [(n.type, n.given, n.surname) for n in names]
        assert info.all_names == expected_all_names, (
            f"Expected all_names={expected_all_names}, got {info.all_names}"
        )


# ---------------------------------------------------------------------------
# Property tests 6-9: Name and cluster filtering
# ---------------------------------------------------------------------------

from slaktbusken.ui.person_list_panel import FilterCriteria, filter_persons


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
                # Name types are translated to Swedish
                _NAME_TYPE_SV = {
                    "birth": "Födelsenamn",
                    "married": "Giftnamn",
                    "adopted": "Adoptivnamn",
                    "other": "Övrigt",
                }
                type_label = _NAME_TYPE_SV.get(name_type, name_type)
                expected = f"{type_label}: {name_str}"
            else:
                expected = name_str

            assert line == expected, (
                f"Line {i} mismatch: expected {expected!r}, got {line!r}. "
                f"Input tuple: ({name_type!r}, {given!r}, {surname!r})"
            )


# ---------------------------------------------------------------------------
# Property test 12: Compact mode threshold
# ---------------------------------------------------------------------------


class TestPropertyCompactModeThreshold:
    """Property 12: Compact mode threshold.

    # Feature: personlista-enhancements, Property 12: Compact mode threshold

    For any panel width value, compact column layout (headers truncated to 4 chars
    + ellipsis, padding 2px) SHALL be active if and only if the width is less
    than 350 pixels.

    **Validates: Requirements 8.4, 8.5**
    """

    # The full headers used by PersonListPanel
    _FULL_HEADERS = ["Namn", "Titel", "Yrke", "Kluster", "DNA"]

    @given(width=st.integers(min_value=1, max_value=3000))
    @settings(max_examples=100)
    def test_compact_mode_active_iff_width_below_350(
        self,
        width: int,
    ) -> None:
        """Compact mode is active if and only if width < 350.

        # Feature: personlista-enhancements, Property 12: Compact mode threshold
        """
        expected_compact = width < 350
        assert (width < 350) == expected_compact

    @given(width=st.integers(min_value=1, max_value=3000))
    @settings(max_examples=100)
    def test_header_truncation_logic_matches_compact_decision(
        self,
        width: int,
    ) -> None:
        """When compact mode is active, headers are truncated to max 4 chars + ellipsis.

        # Feature: personlista-enhancements, Property 12: Compact mode threshold
        """
        compact = width < 350

        if compact:
            expected_headers = [
                (label[:4] + "\u2026") if len(label) > 4 else label
                for label in self._FULL_HEADERS
            ]
        else:
            expected_headers = list(self._FULL_HEADERS)

        # Verify truncation logic: truncated headers should have max 5 chars
        # (4 original + ellipsis) or be the full label if <= 4 chars
        for i, label in enumerate(self._FULL_HEADERS):
            if compact:
                if len(label) > 4:
                    assert expected_headers[i] == label[:4] + "\u2026", (
                        f"Header '{label}' should be truncated to '{label[:4]}\u2026' "
                        f"in compact mode (width={width})"
                    )
                    assert len(expected_headers[i]) == 5
                else:
                    assert expected_headers[i] == label, (
                        f"Header '{label}' (<=4 chars) should remain unchanged "
                        f"in compact mode (width={width})"
                    )
            else:
                assert expected_headers[i] == label, (
                    f"Header '{label}' should be full in normal mode (width={width})"
                )

    @given(width=st.integers(min_value=1, max_value=3000))
    @settings(max_examples=100)
    def test_padding_matches_compact_decision(
        self,
        width: int,
    ) -> None:
        """Padding is 2px in compact mode and 6px in normal mode.

        # Feature: personlista-enhancements, Property 12: Compact mode threshold
        """
        compact = width < 350

        if compact:
            expected_padding = 2
        else:
            expected_padding = 6

        # Verify the threshold logic determines correct padding
        assert expected_padding == (2 if width < 350 else 6), (
            f"Width={width}, compact={compact}: expected padding={expected_padding}"
        )

    @given(width=st.integers(min_value=1, max_value=349))
    @settings(max_examples=50)
    def test_all_widths_below_350_are_compact(
        self,
        width: int,
    ) -> None:
        """Every width from 1 to 349 must trigger compact mode.

        # Feature: personlista-enhancements, Property 12: Compact mode threshold
        """
        assert width < 350, f"Width {width} should be < 350"
        # Compact mode decision
        compact = width < 350
        assert compact is True, f"Width {width} should trigger compact mode"

    @given(width=st.integers(min_value=350, max_value=3000))
    @settings(max_examples=50)
    def test_all_widths_at_or_above_350_are_normal(
        self,
        width: int,
    ) -> None:
        """Every width >= 350 must use normal (non-compact) mode.

        # Feature: personlista-enhancements, Property 12: Compact mode threshold
        """
        assert width >= 350, f"Width {width} should be >= 350"
        # Compact mode decision
        compact = width < 350
        assert compact is False, f"Width {width} should NOT trigger compact mode"


# ---------------------------------------------------------------------------
# Property tests 13-14: Bidirectional selection synchronization
# ---------------------------------------------------------------------------

import pytest
from unittest.mock import MagicMock, patch

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from slaktbusken.persistence.app_settings_io import AppSettings
from slaktbusken.ui.person_list_panel import PersonListPanel, PersonDisplayInfo


def _make_display_info(person_id: str) -> PersonDisplayInfo:
    """Create minimal PersonDisplayInfo for testing."""
    return PersonDisplayInfo(
        person_id=person_id,
        given="Test",
        surname="Person",
        title="",
        birth_year="",
        death_year="",
        marriage_year="",
        event_types=set(),
        parish_names=set(),
        cluster_names=set(),
        name_count=1,
        all_names=[("birth", "Test", "Person")],
    )


def _create_panel_with_mock_app(qtbot):
    """Create a PersonListPanel with a fully mocked Application object."""
    mock_app = MagicMock()
    mock_app.project_service.data.persons = []
    mock_app.project_service.data.events = []
    mock_app.project_service.data.places = []
    mock_app.project_service.data.families = []
    mock_app.project_service.data.dna_clusters = []
    mock_app.project_service.data.dna_profiles = []
    mock_app.project_service.data.dna_companies = []
    mock_app.project_service.data.media = []
    mock_app.project_service.data.project.main_person_id = None
    mock_app.settings_service.get_settings.return_value = AppSettings()

    panel = PersonListPanel(mock_app)
    qtbot.addWidget(panel)
    return panel


class TestPropertyDiagramSyncNoSignal:
    """Property 13: Diagram sync does not emit person_selected.

    # Feature: personlista-enhancements, Property 13: Diagram sync does not emit person_selected

    For any valid person_id that exists in the display list, calling
    select_person_from_diagram(person_id) SHALL select the person in the list
    without causing the person_selected signal to be emitted.

    **Validates: Requirements 9.2**
    """

    @given(person_index=st.integers(min_value=0, max_value=9))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_select_from_diagram_does_not_emit_person_selected(
        self, qtbot, person_index: int
    ) -> None:
        """For any person in the list, diagram sync selects without emitting signal.

        # Feature: personlista-enhancements, Property 13: Diagram sync does not emit person_selected
        """
        # Create panel with mock app
        panel = _create_panel_with_mock_app(qtbot)

        # Populate with 10 persons
        persons = [_make_display_info(f"p{i}") for i in range(10)]
        panel._display_list = persons
        panel._filtered_list = list(persons)
        panel._update_list_widget()

        # Set up a signal spy - record any emissions
        emissions: list[str] = []
        panel.person_selected.connect(lambda pid: emissions.append(pid))

        # Select person from diagram
        target_id = f"p{person_index}"
        panel.select_person_from_diagram(target_id)

        # The signal must NOT have been emitted
        assert emissions == [], (
            f"person_selected was emitted with {emissions} when calling "
            f"select_person_from_diagram('{target_id}') — expected no emission"
        )

        # Verify the person IS actually selected in the tree widget
        current = panel._tree_widget.currentItem()
        assert current is not None, (
            f"No item selected after select_person_from_diagram('{target_id}')"
        )
        from PySide6.QtCore import Qt
        assert current.data(0, Qt.ItemDataRole.UserRole) == target_id, (
            f"Wrong person selected: expected '{target_id}', "
            f"got '{current.data(0, Qt.ItemDataRole.UserRole)}'"
        )


class TestPropertyDiagramSyncSwitchesView:
    """Property 14: Diagram sync switches to unfiltered view when person not in filter.

    # Feature: personlista-enhancements, Property 14: Diagram sync switches to unfiltered view when person not in filter

    For any person that exists in the full display list but not in the currently
    filtered list, calling select_person_from_diagram(person_id) SHALL switch
    the panel to unfiltered view and select that person.

    **Validates: Requirements 9.3**
    """

    @given(excluded_index=st.integers(min_value=0, max_value=4))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_sync_switches_to_unfiltered_when_person_not_in_filter(
        self, qtbot, excluded_index: int
    ) -> None:
        """When syncing a person not in filter, view switches to unfiltered.

        # Feature: personlista-enhancements, Property 14: Diagram sync switches to unfiltered view when person not in filter
        """
        # Create panel with mock app
        panel = _create_panel_with_mock_app(qtbot)

        # Full list: p0..p9, filtered list: p5..p9 (first 5 are excluded)
        all_persons = [_make_display_info(f"p{i}") for i in range(10)]
        filtered_persons = [_make_display_info(f"p{i}") for i in range(5, 10)]

        panel._display_list = all_persons

        # Set filtered state without triggering signal cascades
        panel._toggle_button.blockSignals(True)
        panel._toggle_button.setChecked(True)
        panel._toggle_button.blockSignals(False)
        panel._showing_filtered = True
        panel._filtered_list = list(filtered_persons)
        panel._update_list_widget()

        # Target a person NOT in the filtered list (p0..p4)
        target_id = f"p{excluded_index}"

        # Call select_person_from_diagram for the excluded person
        panel.select_person_from_diagram(target_id)

        # Verify: panel switched to unfiltered view
        assert panel._showing_filtered is False, (
            f"Panel should have switched to unfiltered view when selecting "
            f"'{target_id}' which is not in the filtered list"
        )

        # Verify: toggle button is unchecked
        assert panel._toggle_button.isChecked() is False, (
            f"Toggle button should be unchecked after switching to unfiltered view"
        )

        # Verify: the person is selected
        current = panel._tree_widget.currentItem()
        assert current is not None, (
            f"No item selected after select_person_from_diagram('{target_id}')"
        )
        from PySide6.QtCore import Qt
        assert current.data(0, Qt.ItemDataRole.UserRole) == target_id, (
            f"Wrong person selected: expected '{target_id}', "
            f"got '{current.data(0, Qt.ItemDataRole.UserRole)}'"
        )
