"""Unit tests for the Worked Example: Both Endpoints Open (Requirement 15).

Brita at Place C with start.latest=1840 (no earliest) and end.earliest=1846
(no latest). Observations cover every year from 1840 to 1846. This verifies:

- Zero errors and zero warning-level findings (15.1)
- Two open-endpoint research suggestions (15.2)
- The rendered interval "senast 1840–tidigast 1846" (15.3, 15.4)
- "säker"/"möjlig" query labelling (15.5, 15.6)
- The derived Certain_Core (1840–1846) and unbounded Possible_Span (15.7)
- Zero coverage gaps when observations are complete (15.8)
- No lifespan clamping for unbounded spans (15.9)

Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8, 15.9
"""

from datetime import date

from slaktbusken.model.event import SourceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import (
    Endpoint,
    EndpointKind,
    Observation,
    ResidenceFact,
    certain_core,
    classify_endpoint,
    possible_span,
)
from slaktbusken.model.source import Source, StructuredReference
from slaktbusken.model.validators import validate_residence
from slaktbusken.services.residence_coverage import (
    coverage_gaps,
    open_endpoint_suggestions,
)
from slaktbusken.services.residence_query import (
    LABEL_CERTAIN,
    LABEL_POSSIBLE,
    residents_of_place,
)
from slaktbusken.services.residence_validation import residence_findings
from slaktbusken.ui.swedish_locale import format_residence_interval


# ---------------------------------------------------------------------------
# Fixture: Brita at Place C
# ---------------------------------------------------------------------------


def _brita():
    return Person(
        id="person_brita",
        sex="F",
        names=[Name(type="birth", given="Brita", surname="Persdotter")],
    )


def _place_c():
    return Place(id="place_c", type="farm", name="Norrgården")


def _source(source_id):
    return Source(
        id=source_id,
        provider="Riksarkivet",
        source_type="church_book",
        title=f"AI:{source_id[-1]}",
        structured_reference=StructuredReference(fields={}),
    )


def _observation(source_id, observed_from, observed_to):
    return Observation(
        source_ref=SourceRef(source_id=source_id, quality="primary", note=""),
        observed_from=observed_from,
        observed_to=observed_to,
        page_note="",
    )


def _place_c_fact(observations=None):
    """Brita at Place C: start.latest=1840, end.earliest=1846, both open."""
    return ResidenceFact(
        id="residence_c",
        person_id="person_brita",
        place_id="place_c",
        start=Endpoint(latest="1840"),           # no earliest → open
        end=Endpoint(earliest="1846"),           # no latest → open
        role_in_household="",
        observations=observations or [],
        notes="",
    )


def _full_observations():
    """Observations covering every year from 1840 to 1846."""
    sources = [_source(f"source_{i}") for i in range(1, 3)]
    return [
        _observation("source_1", "1840", "1843"),
        _observation("source_2", "1844", "1846"),
    ], sources


def _project_with_brita(fact=None):
    observations, sources = _full_observations()
    if fact is None:
        fact = _place_c_fact(observations)
    return ProjectData(
        persons=[_brita()],
        places=[_place_c()],
        sources=sources,
        residences=[fact],
    )


# ===========================================================================
# Requirement 15.1: Zero errors and zero warnings
# ===========================================================================


class TestValidation:
    """Requirement 15.1: The fact validates clean."""

    def test_zero_errors(self):
        """validate_residence returns an empty list for the Place C fact."""
        fact = _place_c_fact()
        errors = validate_residence(
            fact,
            valid_person_ids={"person_brita"},
            valid_place_ids={"place_c"},
            valid_source_ids=set(),
            valid_event_ids=set(),
        )
        assert errors == []

    def test_zero_warnings(self):
        """residence_findings returns no warning-level findings."""
        data = _project_with_brita()
        findings = residence_findings(data.residences[0], data)
        assert findings == []

    def test_both_endpoints_classified_as_open(self):
        """Both endpoints are classified as open under Requirement 2."""
        fact = _place_c_fact()
        assert classify_endpoint(fact.start) == EndpointKind.OPEN_LATEST
        assert classify_endpoint(fact.end) == EndpointKind.OPEN_EARLIEST


# ===========================================================================
# Requirement 15.2: Two open-endpoint research suggestions
# ===========================================================================


class TestOpenEndpointSuggestions:
    """Requirement 15.2: Exactly two open-endpoint suggestions."""

    def test_two_suggestions_reported(self):
        """One for start (missing earliest) and one for end (missing latest)."""
        fact = _place_c_fact()
        suggestions = open_endpoint_suggestions(fact)
        assert len(suggestions) == 2

    def test_start_suggestion_names_borjan(self):
        """The start suggestion names 'början'."""
        fact = _place_c_fact()
        suggestions = open_endpoint_suggestions(fact)
        start_suggestions = [s for s in suggestions if s.side == "start"]
        assert len(start_suggestions) == 1
        assert "början" in start_suggestions[0].suggestion

    def test_end_suggestion_names_slutet(self):
        """The end suggestion names 'slutet'."""
        fact = _place_c_fact()
        suggestions = open_endpoint_suggestions(fact)
        end_suggestions = [s for s in suggestions if s.side == "end"]
        assert len(end_suggestions) == 1
        assert "slutet" in end_suggestions[0].suggestion

    def test_fact_is_left_unchanged(self):
        """The fact is not mutated by the analysis."""
        fact = _place_c_fact()
        start_before = fact.start
        end_before = fact.end
        open_endpoint_suggestions(fact)
        assert fact.start is start_before
        assert fact.end is end_before


# ===========================================================================
# Requirements 15.3, 15.4: Rendered interval
# ===========================================================================


class TestRenderedInterval:
    """Requirements 15.3, 15.4: The interval renders as the open-endpoint form."""

    def test_renders_as_senast_1840_tidigast_1846(self):
        """The interval is 'senast 1840–tidigast 1846' (en dash, no spaces)."""
        fact = _place_c_fact()
        rendered = format_residence_interval(fact.start, fact.end)
        assert rendered == "senast 1840\u2013tidigast 1846"

    def test_differs_from_exact_interval(self):
        """Requirement 15.4: differs from the exact '1840–1846' rendering."""
        exact_start = Endpoint(earliest="1840", latest="1840")
        exact_end = Endpoint(earliest="1846", latest="1846")
        exact_rendered = format_residence_interval(exact_start, exact_end)
        open_rendered = format_residence_interval(
            Endpoint(latest="1840"), Endpoint(earliest="1846")
        )
        assert exact_rendered == "1840\u20131846"
        assert open_rendered == "senast 1840\u2013tidigast 1846"
        assert exact_rendered != open_rendered


# ===========================================================================
# Requirements 15.5, 15.6: Query labelling ("säker" / "möjlig")
# ===========================================================================


class TestQueryLabelling:
    """Requirements 15.5, 15.6: years inside core are 'säker', outside 'möjlig'."""

    def test_year_1840_is_certain(self):
        """1840 overlaps the Certain_Core → 'säker'."""
        data = _project_with_brita()
        entries = residents_of_place(data, "place_c", 1840)
        assert len(entries) == 1
        assert entries[0].label == LABEL_CERTAIN

    def test_year_1843_is_certain(self):
        """1843 is inside the Certain_Core → 'säker'."""
        data = _project_with_brita()
        entries = residents_of_place(data, "place_c", 1843)
        assert len(entries) == 1
        assert entries[0].label == LABEL_CERTAIN

    def test_year_1846_is_certain(self):
        """1846 overlaps the Certain_Core → 'säker'."""
        data = _project_with_brita()
        entries = residents_of_place(data, "place_c", 1846)
        assert len(entries) == 1
        assert entries[0].label == LABEL_CERTAIN

    def test_year_1850_is_possible(self):
        """Requirement 15.5: 1850 lies inside the Possible_Span, outside the core."""
        data = _project_with_brita()
        entries = residents_of_place(data, "place_c", 1850)
        assert len(entries) == 1
        assert entries[0].label == LABEL_POSSIBLE


# ===========================================================================
# Requirement 15.7: Derived Certain_Core and unbounded Possible_Span
# ===========================================================================


class TestDerivedIntervals:
    """Requirement 15.7: Core is 1840–1846, Possible_Span is unbounded both."""

    def test_certain_core_is_1840_through_1846(self):
        """The core runs from last day of 1840 through first day of 1846."""
        fact = _place_c_fact()
        core = certain_core(fact)
        assert core is not None
        # start.latest="1840" expands to last day 1840-12-31
        # end.earliest="1846" expands to first day 1846-01-01
        assert core.first == date(1840, 12, 31)
        assert core.last == date(1846, 1, 1)

    def test_certain_core_is_non_empty(self):
        """The core is non-empty even though both endpoints are open."""
        fact = _place_c_fact()
        core = certain_core(fact)
        assert core is not None
        assert core.first <= core.last

    def test_possible_span_is_unbounded_both_directions(self):
        """The Possible_Span has None on both sides (start.earliest and end.latest absent)."""
        fact = _place_c_fact()
        span = possible_span(fact)
        assert span.first is None
        assert span.last is None
        assert span.is_unbounded_both()

    def test_possible_span_contains_any_year(self):
        """An unbounded span overlaps every queried year."""
        fact = _place_c_fact()
        span = possible_span(fact)
        assert span.overlaps_year(1750)
        assert span.overlaps_year(1840)
        assert span.overlaps_year(1846)
        assert span.overlaps_year(1980)
        assert span.overlaps_year(2100)


# ===========================================================================
# Requirement 15.8: Zero coverage gaps
# ===========================================================================


class TestCoverageGaps:
    """Requirement 15.8: Zero coverage gaps when observations cover 1840–1846."""

    def test_zero_gaps_with_full_coverage(self):
        """Observations covering 1840–1846 yield no gap."""
        data = _project_with_brita()
        gaps = coverage_gaps(data.residences[0], data)
        assert gaps == []

    def test_open_endpoint_suggestions_are_independent_of_gaps(self):
        """The two open-endpoint suggestions exist independently of zero gaps."""
        data = _project_with_brita()
        gaps = coverage_gaps(data.residences[0], data)
        suggestions = open_endpoint_suggestions(data.residences[0])
        assert gaps == []
        assert len(suggestions) == 2


# ===========================================================================
# Requirement 15.9: No lifespan clamping
# ===========================================================================


class TestNoLifespanClamping:
    """Requirement 15.9: The unbounded span matches even extreme years."""

    def test_year_1750_returns_possible_with_undated(self):
        """1750 matches with 'möjlig' and undated=True, no clamping."""
        data = _project_with_brita()
        entries = residents_of_place(data, "place_c", 1750)
        assert len(entries) == 1
        assert entries[0].label == LABEL_POSSIBLE
        assert entries[0].undated is True

    def test_year_1980_returns_possible_with_undated(self):
        """1980 matches with 'möjlig' and undated=True, no clamping."""
        data = _project_with_brita()
        entries = residents_of_place(data, "place_c", 1980)
        assert len(entries) == 1
        assert entries[0].label == LABEL_POSSIBLE
        assert entries[0].undated is True

    def test_undated_flag_is_true_for_unbounded_span(self):
        """The entry carries undated=True for a both-sides-unbounded span."""
        data = _project_with_brita()
        entries = residents_of_place(data, "place_c", 1850)
        assert entries[0].undated is True

    def test_interval_display_is_correct_in_query_result(self):
        """The query entry renders the interval through the formatter."""
        data = _project_with_brita()
        entries = residents_of_place(data, "place_c", 1850)
        assert entries[0].interval_display == "senast 1840\u2013tidigast 1846"
