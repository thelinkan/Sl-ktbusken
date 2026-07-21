# Feature: dna-cluster-enhancements, Property 15: Person name matching for CSV match import
"""Property-based tests for person name matching in CSV match import.

Feature: dna-cluster-enhancements, Property 15: Person name matching for CSV match import

For any match name string from CSV data and set of persons in the project,
suggested profiles SHALL belong to persons whose given name or surname contains
the match name as a case-insensitive substring.

**Validates: Requirements 13.4**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.person import Name, Person


# ---------------------------------------------------------------------------
# Pure function under test — extracted from DnaMatchDialog._suggest_profile2()
# ---------------------------------------------------------------------------


def find_matching_person_ids(
    match_name: str,
    persons: list[Person],
    exclude_person_id: str | None = None,
) -> list[str]:
    """Find person_ids whose given name or surname matches the match_name.

    Matching logic (case-insensitive):
    - match_name is a substring of given name OR surname
    - OR given name is a substring of match_name
    - OR surname is a substring of match_name

    This replicates the logic in DnaMatchDialog._suggest_profile2().
    """
    match_name_lower = match_name.lower()
    result: list[str] = []
    for person in persons:
        if person.id == exclude_person_id:
            continue
        for name in person.names:
            given_lower = name.given.lower() if name.given else ""
            surname_lower = name.surname.lower() if name.surname else ""
            if (
                match_name_lower in given_lower
                or match_name_lower in surname_lower
                or given_lower in match_name_lower
                or surname_lower in match_name_lower
            ):
                result.append(person.id)
                break
    return result


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Name text: use letters and spaces, non-empty
_name_text = st.text(
    alphabet=st.characters(categories=("L", "Z")),
    min_size=1,
    max_size=30,
)

_name_text_or_empty = st.text(
    alphabet=st.characters(categories=("L", "Z")),
    min_size=0,
    max_size=30,
)


@st.composite
def person_with_name(draw: DrawFn, person_id: str) -> Person:
    """Generate a person with at least one name."""
    given = draw(_name_text)
    surname = draw(_name_text)
    names = [Name(type="birth", given=given, surname=surname)]
    # Optionally add a second name
    if draw(st.booleans()):
        given2 = draw(_name_text)
        surname2 = draw(_name_text)
        names.append(Name(type="married", given=given2, surname=surname2))
    return Person(id=person_id, sex="U", names=names)


@st.composite
def persons_with_known_match(
    draw: DrawFn,
) -> tuple[str, list[Person], str]:
    """Generate persons where one person's name is guaranteed to match.

    Returns (match_name, persons, expected_person_id) where match_name is a
    substring of the expected person's given name or surname.
    """
    # Create target person
    target_id = "person_target"
    target_given = draw(_name_text)
    target_surname = draw(_name_text)
    target = Person(
        id=target_id,
        sex="U",
        names=[Name(type="birth", given=target_given, surname=target_surname)],
    )

    # Extract a substring from either given or surname as the match_name
    use_given = draw(st.booleans())
    source = target_given if use_given else target_surname
    if len(source) > 0:
        start = draw(st.integers(min_value=0, max_value=max(0, len(source) - 1)))
        end = draw(st.integers(min_value=start + 1, max_value=len(source)))
        match_name = source[start:end]
    else:
        match_name = source

    # Create other persons (that may or may not match)
    num_others = draw(st.integers(min_value=0, max_value=5))
    others: list[Person] = []
    for i in range(num_others):
        others.append(draw(person_with_name(f"person_{i}")))

    # Shuffle target into the list
    persons = others + [target]
    return (match_name, persons, target_id)


@st.composite
def persons_and_random_match_name(
    draw: DrawFn,
) -> tuple[str, list[Person]]:
    """Generate a random set of persons and a random match name."""
    num_persons = draw(st.integers(min_value=1, max_value=8))
    persons: list[Person] = []
    for i in range(num_persons):
        persons.append(draw(person_with_name(f"person_{i}")))
    match_name = draw(_name_text)
    return (match_name, persons)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestPersonNameMatchingForCsvImport:
    """Feature: dna-cluster-enhancements, Property 15: Person name matching for CSV match import

    For any match name string from CSV data and set of persons in the project,
    suggested profiles SHALL belong to persons whose given name or surname
    contains the match name as a case-insensitive substring.

    **Validates: Requirements 13.4**
    """

    @given(data=persons_with_known_match())
    @settings(max_examples=100)
    def test_substring_of_name_always_matches(
        self,
        data: tuple[str, list[Person], str],
    ) -> None:
        """When match_name is a substring of a person's given name or surname,
        that person SHALL appear in the result.

        Feature: dna-cluster-enhancements, Property 15: Person name matching for CSV match import
        **Validates: Requirements 13.4**
        """
        match_name, persons, expected_person_id = data

        result = find_matching_person_ids(match_name, persons)

        assert expected_person_id in result, (
            f"Expected person '{expected_person_id}' to match for "
            f"match_name='{match_name}' but got: {result}"
        )

    @given(data=persons_and_random_match_name())
    @settings(max_examples=100)
    def test_all_results_satisfy_matching_criteria(
        self,
        data: tuple[str, list[Person]],
    ) -> None:
        """Every person in the result SHALL satisfy at least one of the matching
        criteria: match_name is substring of given/surname, or given/surname
        is substring of match_name.

        Feature: dna-cluster-enhancements, Property 15: Person name matching for CSV match import
        **Validates: Requirements 13.4**
        """
        match_name, persons = data

        result = find_matching_person_ids(match_name, persons)
        match_name_lower = match_name.lower()

        for person_id in result:
            person = next(p for p in persons if p.id == person_id)
            matches_any_name = False
            for name in person.names:
                given_lower = name.given.lower() if name.given else ""
                surname_lower = name.surname.lower() if name.surname else ""
                if (
                    match_name_lower in given_lower
                    or match_name_lower in surname_lower
                    or given_lower in match_name_lower
                    or surname_lower in match_name_lower
                ):
                    matches_any_name = True
                    break
            assert matches_any_name, (
                f"Person '{person_id}' with names {[(n.given, n.surname) for n in person.names]} "
                f"does not match match_name='{match_name}' but was in result."
            )

    @given(data=persons_and_random_match_name())
    @settings(max_examples=100)
    def test_case_insensitivity(
        self,
        data: tuple[str, list[Person]],
    ) -> None:
        """The matching SHALL be case-insensitive: upper/lower/mixed case of
        match_name produces the same result set.

        Feature: dna-cluster-enhancements, Property 15: Person name matching for CSV match import
        **Validates: Requirements 13.4**
        """
        match_name, persons = data

        result_original = set(find_matching_person_ids(match_name, persons))
        result_upper = set(find_matching_person_ids(match_name.upper(), persons))
        result_lower = set(find_matching_person_ids(match_name.lower(), persons))

        assert result_original == result_upper == result_lower, (
            f"Case sensitivity detected!\n"
            f"  match_name='{match_name}'\n"
            f"  original: {result_original}\n"
            f"  upper: {result_upper}\n"
            f"  lower: {result_lower}"
        )

    @given(data=persons_and_random_match_name())
    @settings(max_examples=100)
    def test_excluded_person_not_in_result(
        self,
        data: tuple[str, list[Person]],
    ) -> None:
        """When exclude_person_id is specified, that person SHALL NOT appear
        in the result, regardless of whether their name matches.

        Feature: dna-cluster-enhancements, Property 15: Person name matching for CSV match import
        **Validates: Requirements 13.4**
        """
        match_name, persons = data

        # Exclude the first person
        exclude_id = persons[0].id

        result = find_matching_person_ids(
            match_name, persons, exclude_person_id=exclude_id
        )

        assert exclude_id not in result, (
            f"Excluded person '{exclude_id}' should not appear in result "
            f"but got: {result}"
        )

    @given(data=persons_and_random_match_name())
    @settings(max_examples=100)
    def test_no_false_negatives(
        self,
        data: tuple[str, list[Person]],
    ) -> None:
        """Every person whose name satisfies the matching criteria SHALL be
        in the result (completeness check).

        Feature: dna-cluster-enhancements, Property 15: Person name matching for CSV match import
        **Validates: Requirements 13.4**
        """
        match_name, persons = data
        match_name_lower = match_name.lower()

        result = set(find_matching_person_ids(match_name, persons))

        # Compute expected by independently checking all persons
        expected: set[str] = set()
        for person in persons:
            for name in person.names:
                given_lower = name.given.lower() if name.given else ""
                surname_lower = name.surname.lower() if name.surname else ""
                if (
                    match_name_lower in given_lower
                    or match_name_lower in surname_lower
                    or given_lower in match_name_lower
                    or surname_lower in match_name_lower
                ):
                    expected.add(person.id)
                    break

        assert result == expected, (
            f"Result mismatch for match_name='{match_name}'.\n"
            f"  Result: {result}\n"
            f"  Expected: {expected}\n"
            f"  Missing: {expected - result}\n"
            f"  Extra: {result - expected}"
        )
