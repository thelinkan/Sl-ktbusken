# Feature: residence-periods, Property 21: Bulk entry applies wholly or not at all
"""Property-based test for bulk entry.

Feature: residence-periods, Property 21: Bulk entry applies wholly or not at all

For any pasted text and person/place selection, the bulk planner either raises
BulkLimitError naming the exceeded limit before any work (text > 20000 chars,
> 50 non-empty lines, > 20 persons), or returns a BulkPlan where: every
successfully parsed line yields a candidate in line order; Source matching is
case-insensitive and whitespace-trimmed with absent equal to empty; the plan is
a pure data structure (project unchanged); and summary counts are consistent
(observations = candidates × persons).

**Validates: Requirements 9.1, 9.3, 9.4, 9.6, 9.7, 9.8, 9.9, 9.10**
"""

from __future__ import annotations

import copy
import string

from hypothesis import assume, given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.event import SourceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import (
    Endpoint,
    Observation,
    ResidenceFact,
)
from slaktbusken.model.source import Source, StructuredReference
from slaktbusken.services.residence_edit_ops import (
    BulkCandidate,
    BulkLimitError,
    BulkPlan,
    BulkRequest,
    plan_bulk_attach,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A well-known Arkiv Digital reference format that parse_reference accepts.
_AD_TEMPLATE = "{parish} ({county}) {series}:{volume} ({years}) Bild {image} (AID: v{aid}, NAD: {nad})"


def _make_ad_line(
    parish: str = "Ljusdal",
    county: str = "X",
    series: str = "AI",
    volume: str = "5",
    years: str = "1866-1870",
    image: str = "10",
    aid: str = "100",
    nad: str = "90",
) -> str:
    """Build a parsable Arkiv Digital reference line."""
    return _AD_TEMPLATE.format(
        parish=parish,
        county=county,
        series=series,
        volume=volume,
        years=years,
        image=image,
        aid=aid,
        nad=nad,
    )


def _make_source(
    source_id: str,
    parish: str = "Ljusdal",
    series: str = "AI",
    volume: str = "5",
    years: str = "1866-1870",
    image: str = "10",
) -> Source:
    """Create a church_book Source that matches an Arkiv Digital reference."""
    return Source(
        id=source_id,
        provider="Arkiv Digital",
        source_type="church_book",
        title=f"{parish} {series}:{volume} ({years})",
        structured_reference=StructuredReference(
            fields={
                "parish": parish,
                "series": series,
                "volume": volume,
                "years": years,
                "image": image,
                "page": None,
            }
        ),
    )


def _make_project(
    persons: list[Person] | None = None,
    places: list[Place] | None = None,
    sources: list[Source] | None = None,
    residences: list[ResidenceFact] | None = None,
) -> ProjectData:
    """Build a minimal ProjectData."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=persons or [Person(id="person_1", sex="M", names=[Name(type="birth", given="Anders", surname="Svensson")])],
        places=places or [Place(id="place_1", type="farm", name="Gården")],
        sources=sources or [],
        events=[],
        residences=residences or [],
    )


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

#: Valid parishes for generating references.
_PARISHES = ["Ljusdal", "Hudiksvall", "Bollnäs", "Söderhamn", "Delsbo"]
_SERIES = ["AI", "AII", "AIIa", "CI", "FI", "BI"]
_COUNTIES = ["X", "S", "Y", "AB", "W"]


@st.composite
def _parsable_lines(draw: DrawFn, *, min_lines: int = 1, max_lines: int = 10) -> list[str]:
    """Generate a list of parsable Arkiv Digital reference lines."""
    count = draw(st.integers(min_value=min_lines, max_value=max_lines))
    lines = []
    for i in range(count):
        parish = draw(st.sampled_from(_PARISHES))
        county = draw(st.sampled_from(_COUNTIES))
        series = draw(st.sampled_from(_SERIES))
        volume = str(draw(st.integers(min_value=1, max_value=40)))
        first_year = draw(st.integers(min_value=1700, max_value=1900))
        last_year = first_year + draw(st.integers(min_value=1, max_value=10))
        years = f"{first_year}-{last_year}"
        image = str(draw(st.integers(min_value=1, max_value=500)))
        aid = str(draw(st.integers(min_value=1, max_value=99999)))
        nad = str(draw(st.integers(min_value=1, max_value=99999)))
        lines.append(_make_ad_line(parish, county, series, volume, years, image, aid, nad))
    return lines


@st.composite
def _mixed_lines(draw: DrawFn) -> tuple[list[str], int, int]:
    """Generate a mix of parsable and unparsable lines.

    Returns (lines, expected_parsable_count, expected_unparsable_count).
    """
    parsable = draw(_parsable_lines(min_lines=1, max_lines=8))
    unparsable_count = draw(st.integers(min_value=0, max_value=5))
    unparsable = [
        draw(st.text(alphabet=string.ascii_letters + " ", min_size=5, max_size=50))
        for _ in range(unparsable_count)
    ]
    # Interleave them, keeping order
    all_lines = []
    parsable_iter = iter(parsable)
    unparsable_iter = iter(unparsable)
    # Alternate randomly
    p_remaining = len(parsable)
    u_remaining = unparsable_count
    for _ in range(p_remaining + u_remaining):
        if p_remaining == 0:
            all_lines.append(next(unparsable_iter))
            u_remaining -= 1
        elif u_remaining == 0:
            all_lines.append(next(parsable_iter))
            p_remaining -= 1
        elif draw(st.booleans()):
            all_lines.append(next(parsable_iter))
            p_remaining -= 1
        else:
            all_lines.append(next(unparsable_iter))
            u_remaining -= 1

    return all_lines, len(parsable), unparsable_count


@st.composite
def _person_ids(draw: DrawFn, *, min_count: int = 1, max_count: int = 5) -> list[str]:
    """Generate a list of person ids within the 20-person limit."""
    count = draw(st.integers(min_value=min_count, max_value=max_count))
    return [f"person_{i + 1}" for i in range(count)]


@st.composite
def _over_limit_text(draw: DrawFn) -> tuple[str, str]:
    """Generate text that exceeds one of the three limits.

    Returns (text, expected_limit_name).
    """
    kind = draw(st.sampled_from(["chars", "lines"]))
    if kind == "chars":
        # Exceed 20000 characters
        base_line = _make_ad_line()
        # Repeat a line enough times to exceed 20000 chars, padding with spaces
        lines_needed = 20001 // (len(base_line) + 1) + 1
        text = "\n".join([base_line] * min(lines_needed, 50))
        if len(text) <= 20000:
            # Pad to exceed
            text += " " * (20001 - len(text))
        return text, "tecken"
    else:
        # Exceed 50 non-empty lines
        base_line = _make_ad_line(years="1800-1805")
        lines = [base_line] * 51
        return "\n".join(lines), "rader"


# ---------------------------------------------------------------------------
# Property test class
# ---------------------------------------------------------------------------


class TestBulkEntryProperty:
    """Property 21: Bulk entry applies wholly or not at all.

    Limits are enforced before any work (exceeding raises BulkLimitError naming
    the limit); every successfully parsed line yields a candidate in line order;
    Source matching is case-insensitive and whitespace-trimmed with absent==empty;
    the plan is a pure data structure (project unchanged); and summary counts are
    consistent (observations = candidates × persons).

    **Validates: Requirements 9.1, 9.3, 9.4, 9.6, 9.7, 9.8, 9.9, 9.10**
    """

    @given(data=_over_limit_text())
    @settings(max_examples=100, deadline=None)
    def test_limits_enforced_before_any_work(
        self, data: tuple[str, str]
    ) -> None:
        """Exceeding a limit raises BulkLimitError naming the limit before any work.

        Feature: residence-periods, Property 21: Bulk entry applies wholly or not at all

        **Validates: Requirements 9.8**
        """
        text, expected_limit = data
        project = _make_project()
        request = BulkRequest(
            text=text,
            person_ids=["person_1"],
            place_id="place_1",
        )
        project_before = copy.deepcopy(project)
        try:
            plan_bulk_attach(request, project)
            # If we got here, the limit wasn't exceeded (possible for edge cases)
            # — check that limit conditions actually hold
            non_empty = [l for l in text.splitlines() if l.strip()]
            assert len(text) <= 20000 and len(non_empty) <= 50
        except BulkLimitError as exc:
            # The error names the exceeded limit
            assert expected_limit in exc.limit_name
            # Project is unchanged
            assert project.residences == project_before.residences
            assert project.sources == project_before.sources

    @given(person_ids=st.lists(
        st.text(alphabet=string.ascii_lowercase, min_size=3, max_size=8),
        min_size=21,
        max_size=25,
        unique=True,
    ))
    @settings(max_examples=100, deadline=None)
    def test_person_limit_enforced(self, person_ids: list[str]) -> None:
        """Exceeding the 20-person limit raises BulkLimitError naming 'personer'.

        Feature: residence-periods, Property 21: Bulk entry applies wholly or not at all

        **Validates: Requirements 9.8**
        """
        text = _make_ad_line()
        project = _make_project()
        request = BulkRequest(
            text=text,
            person_ids=person_ids,
            place_id="place_1",
        )
        try:
            plan_bulk_attach(request, project)
            assert False, "Should have raised BulkLimitError"
        except BulkLimitError as exc:
            assert "personer" in exc.limit_name

    @given(data=_mixed_lines(), person_ids=_person_ids())
    @settings(max_examples=100, deadline=None)
    def test_parsed_lines_yield_candidates_in_line_order(
        self, data: tuple[list[str], int, int], person_ids: list[str]
    ) -> None:
        """Every successfully parsed line yields a candidate in line order.

        Feature: residence-periods, Property 21: Bulk entry applies wholly or not at all

        **Validates: Requirements 9.1, 9.6**
        """
        lines, expected_parsable, expected_unparsable = data
        text = "\n".join(lines)
        assume(len(text) <= 20000)
        assume(len(lines) <= 50)
        assume(len(person_ids) <= 20)

        persons = [
            Person(id=pid, sex="M", names=[Name(type="birth", given="Test", surname="Person")])
            for pid in person_ids
        ]
        project = _make_project(persons=persons)
        request = BulkRequest(
            text=text,
            person_ids=person_ids,
            place_id="place_1",
        )
        plan = plan_bulk_attach(request, project)

        # Candidate count matches parsed lines
        assert len(plan.candidates) == expected_parsable
        # Unparsed count matches
        assert len(plan.unparsed_lines) == expected_unparsable
        # Candidates are in ascending line_index order
        indices = [c.line_index for c in plan.candidates]
        assert indices == sorted(indices)
        # All indices are distinct
        assert len(set(indices)) == len(indices)

    @given(data=_parsable_lines(min_lines=1, max_lines=10), person_ids=_person_ids())
    @settings(max_examples=100, deadline=None)
    def test_source_matching_case_insensitive_whitespace_trimmed(
        self, data: list[str], person_ids: list[str]
    ) -> None:
        """Source matching is case-insensitive and whitespace-trimmed with absent==empty.

        Feature: residence-periods, Property 21: Bulk entry applies wholly or not at all

        **Validates: Requirements 9.7**
        """
        assume(len(person_ids) <= 20)
        assume(len(data) <= 50)

        text = "\n".join(data)
        assume(len(text) <= 20000)

        # Create a source that matches the first line but with case/whitespace variations
        # Use Ljusdal AI:5 (1866-1870) as a known matchable source
        first_line = _make_ad_line(
            parish="Ljusdal", county="X", series="AI", volume="5",
            years="1866-1870", image="10", aid="100", nad="90"
        )
        text_with_match = first_line + "\n" + text

        # Source with different casing and whitespace padding
        matching_source = _make_source(
            "source_match",
            parish="  LJUSDAL  ",  # whitespace + upper case
            series="  ai  ",       # whitespace + lower case
            volume="  5  ",        # whitespace
            years="  1866-1870  ", # whitespace
            image="  10  ",        # whitespace
        )

        persons = [
            Person(id=pid, sex="M", names=[Name(type="birth", given="Test", surname="Person")])
            for pid in person_ids
        ]
        project = _make_project(persons=persons, sources=[matching_source])

        request = BulkRequest(
            text=text_with_match,
            person_ids=person_ids,
            place_id="place_1",
        )

        non_empty = [l for l in text_with_match.splitlines() if l.strip()]
        assume(len(non_empty) <= 50)
        assume(len(text_with_match) <= 20000)

        plan = plan_bulk_attach(request, project)

        # The first candidate should have matched the source
        assert len(plan.candidates) >= 1
        assert plan.candidates[0].source_id == "source_match"
        assert plan.sources_reused >= 1

    @given(data=_parsable_lines(min_lines=1, max_lines=10), person_ids=_person_ids())
    @settings(max_examples=100, deadline=None)
    def test_plan_is_pure_project_unchanged(
        self, data: list[str], person_ids: list[str]
    ) -> None:
        """The plan is a pure data structure (project unchanged).

        Feature: residence-periods, Property 21: Bulk entry applies wholly or not at all

        **Validates: Requirements 9.9**
        """
        assume(len(person_ids) <= 20)
        assume(len(data) <= 50)
        text = "\n".join(data)
        assume(len(text) <= 20000)

        persons = [
            Person(id=pid, sex="M", names=[Name(type="birth", given="Test", surname="Person")])
            for pid in person_ids
        ]
        sources = [_make_source("source_1")]
        residences = [
            ResidenceFact(
                id="residence_1",
                person_id=person_ids[0],
                place_id="place_1",
                start=Endpoint(earliest="1860", latest="1866"),
                end=Endpoint(earliest="1870", latest="1880"),
                observations=[],
            )
        ]
        project = _make_project(persons=persons, sources=sources, residences=residences)
        project_before = copy.deepcopy(project)

        request = BulkRequest(
            text=text,
            person_ids=person_ids,
            place_id="place_1",
        )
        plan_bulk_attach(request, project)

        # Project must be identical to its deep copy before the call
        assert project.residences == project_before.residences
        assert project.sources == project_before.sources
        assert project.persons == project_before.persons
        assert project.places == project_before.places
        assert project.events == project_before.events

    @given(data=_parsable_lines(min_lines=1, max_lines=10), person_ids=_person_ids(min_count=1, max_count=10))
    @settings(max_examples=100, deadline=None)
    def test_summary_counts_consistent(
        self, data: list[str], person_ids: list[str]
    ) -> None:
        """Summary counts are consistent: observations = candidates × persons.

        Feature: residence-periods, Property 21: Bulk entry applies wholly or not at all

        **Validates: Requirements 9.3, 9.10**
        """
        assume(len(person_ids) <= 20)
        assume(len(data) <= 50)
        text = "\n".join(data)
        assume(len(text) <= 20000)

        persons = [
            Person(id=pid, sex="M", names=[Name(type="birth", given="Test", surname="Person")])
            for pid in person_ids
        ]
        project = _make_project(persons=persons)

        request = BulkRequest(
            text=text,
            person_ids=person_ids,
            place_id="place_1",
        )
        plan = plan_bulk_attach(request, project)

        # observations = candidates × persons (Req 9.3, 9.10)
        assert plan.observations_to_attach == len(plan.candidates) * len(person_ids)
        # sources_reused + sources_to_create == total candidates
        assert plan.sources_reused + plan.sources_to_create == len(plan.candidates)
        # facts_to_create + facts_to_extend == number of persons
        assert plan.facts_to_create + plan.facts_to_extend == len(person_ids)
        # person_plans has one entry per person
        assert len(plan.person_plans) == len(person_ids)
