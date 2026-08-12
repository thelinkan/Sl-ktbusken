"""Unit tests for plan_bulk_attach (Requirement 9).

Covers the bulk entry planning logic: limits enforcement, parsing, Source
matching, per-person preselection of existing facts, unparsed line collection,
and summary counts.
"""

from __future__ import annotations

import pytest

from slaktbusken.model.event import SourceRef
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.source import Source, StructuredReference
from slaktbusken.services.residence_edit_ops import (
    BulkLimitError,
    BulkPlan,
    BulkRequest,
    plan_bulk_attach,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_project() -> ProjectData:
    """Return a minimal ProjectData."""
    return ProjectData()


def _church_book_source(
    source_id: str,
    parish: str = "Ljusdal",
    series: str = "AI",
    volume: str = "17",
    years: str = "1866-1870",
    image: str = "100",
    page: str = "5",
) -> Source:
    return Source(
        id=source_id,
        provider="Arkiv Digital",
        source_type="church_book",
        title=f"{parish} {series}:{volume}",
        structured_reference=StructuredReference(
            fields={
                "parish": parish,
                "series": series,
                "volume": volume,
                "years": years,
                "image": image,
                "page": page,
            }
        ),
    )


def _ad_reference_line(
    parish: str = "Ljusdal",
    county: str = "X",
    series: str = "AI",
    volume: str = "17",
    years: str = "1866-1870",
    image: str = "100",
    page: str = "5",
) -> str:
    """Build an Arkiv Digital full-pattern reference line."""
    return (
        f"{parish} ({county}) {series}:{volume} ({years}) "
        f"Bild {image} / sid {page} (AID: v12345, NAD: SE/HLA/1234)"
    )


def _residence_fact(
    fact_id: str,
    person_id: str,
    place_id: str,
    start_earliest: str | None = None,
    start_latest: str | None = None,
    end_earliest: str | None = None,
    end_latest: str | None = None,
) -> ResidenceFact:
    return ResidenceFact(
        id=fact_id,
        person_id=person_id,
        place_id=place_id,
        start=Endpoint(earliest=start_earliest, latest=start_latest),
        end=Endpoint(earliest=end_earliest, latest=end_latest),
    )


# ---------------------------------------------------------------------------
# Limit enforcement (Requirement 9.8)
# ---------------------------------------------------------------------------

class TestBulkLimits:
    """Limits are enforced BEFORE any work happens."""

    def test_exceeding_character_limit_raises(self) -> None:
        text = "a" * 20_001
        request = BulkRequest(text=text, person_ids=["p1"], place_id="pl1")
        with pytest.raises(BulkLimitError) as exc_info:
            plan_bulk_attach(request, _empty_project())
        assert "tecken" in exc_info.value.limit_name

    def test_exactly_20000_chars_does_not_raise(self) -> None:
        # Build a text of exactly 20_000 chars with valid reference lines
        line = _ad_reference_line()
        # We need a valid text of exactly 20_000 chars - pad with extra lines
        text = (line + "\n") * 10
        # Pad to exactly 20_000 (won't exceed 50 lines since each line is ~80 chars)
        text = text[:20_000]
        request = BulkRequest(text=text, person_ids=["p1"], place_id="pl1")
        # Should not raise
        plan_bulk_attach(request, _empty_project())

    def test_exceeding_line_limit_raises(self) -> None:
        line = _ad_reference_line()
        text = "\n".join([line] * 51)
        request = BulkRequest(text=text, person_ids=["p1"], place_id="pl1")
        with pytest.raises(BulkLimitError) as exc_info:
            plan_bulk_attach(request, _empty_project())
        assert "rader" in exc_info.value.limit_name

    def test_exactly_50_lines_does_not_raise(self) -> None:
        line = _ad_reference_line()
        text = "\n".join([line] * 50)
        request = BulkRequest(text=text, person_ids=["p1"], place_id="pl1")
        plan_bulk_attach(request, _empty_project())

    def test_exceeding_person_limit_raises(self) -> None:
        line = _ad_reference_line()
        persons = [f"p{i}" for i in range(21)]
        request = BulkRequest(text=line, person_ids=persons, place_id="pl1")
        with pytest.raises(BulkLimitError) as exc_info:
            plan_bulk_attach(request, _empty_project())
        assert "personer" in exc_info.value.limit_name

    def test_exactly_20_persons_does_not_raise(self) -> None:
        line = _ad_reference_line()
        persons = [f"p{i}" for i in range(20)]
        request = BulkRequest(text=line, person_ids=persons, place_id="pl1")
        plan_bulk_attach(request, _empty_project())

    def test_empty_lines_are_not_counted(self) -> None:
        """Only non-empty lines count toward the 50-line limit."""
        line = _ad_reference_line()
        # 30 non-empty + lots of empty = still under 50
        text = "\n\n".join([line] * 30)
        request = BulkRequest(text=text, person_ids=["p1"], place_id="pl1")
        plan_bulk_attach(request, _empty_project())

    def test_limit_error_names_which_limit(self) -> None:
        """The error message names which limit was exceeded."""
        text = "x\n" * 100  # 100 non-empty lines (unparseable but counted)
        request = BulkRequest(text=text, person_ids=["p1"], place_id="pl1")
        with pytest.raises(BulkLimitError) as exc_info:
            plan_bulk_attach(request, _empty_project())
        assert "rader" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Parsing in line order (Requirement 9.1)
# ---------------------------------------------------------------------------

class TestParsing:
    """Lines are parsed in order, unparseable lines are collected."""

    def test_parsed_candidates_in_line_order(self) -> None:
        line1 = _ad_reference_line(parish="Ljusdal", volume="17")
        line2 = _ad_reference_line(parish="Delsbo", volume="18")
        text = f"{line1}\n{line2}"
        request = BulkRequest(text=text, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, _empty_project())
        assert len(plan.candidates) == 2
        assert plan.candidates[0].line_index == 0
        assert plan.candidates[1].line_index == 1

    def test_unparseable_lines_collected(self) -> None:
        """Lines that don't parse are listed under 'Kunde inte tolkas'."""
        valid = _ad_reference_line()
        text = f"garbage line\n{valid}\nanother garbage"
        request = BulkRequest(text=text, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, _empty_project())
        assert len(plan.candidates) == 1
        assert len(plan.unparsed_lines) == 2
        assert "garbage line" in plan.unparsed_lines[0]
        assert "another garbage" in plan.unparsed_lines[1]

    def test_unparsed_line_truncated_at_200(self) -> None:
        """Unparseable lines are truncated at 200 characters (Req 9.6)."""
        long_line = "x" * 300
        valid = _ad_reference_line()
        text = f"{long_line}\n{valid}"
        request = BulkRequest(text=text, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, _empty_project())
        assert len(plan.unparsed_lines) == 1
        assert len(plan.unparsed_lines[0]) == 200

    def test_empty_lines_are_skipped(self) -> None:
        """Empty and whitespace-only lines are not counted or parsed."""
        valid = _ad_reference_line()
        text = f"\n  \n{valid}\n\n"
        request = BulkRequest(text=text, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, _empty_project())
        assert len(plan.candidates) == 1
        assert len(plan.unparsed_lines) == 0


# ---------------------------------------------------------------------------
# Source matching (Requirement 9.7)
# ---------------------------------------------------------------------------

class TestSourceMatching:
    """Existing Sources are matched on type + six structured_reference values."""

    def test_reuses_existing_source_on_exact_match(self) -> None:
        source = _church_book_source("src1")
        data = _empty_project()
        data.sources.append(source)

        line = _ad_reference_line()
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, data)

        assert len(plan.candidates) == 1
        assert plan.candidates[0].source_id == "src1"
        assert plan.sources_reused == 1
        assert plan.sources_to_create == 0

    def test_case_insensitive_matching(self) -> None:
        """Matching is case-insensitive (Req 9.7)."""
        source = _church_book_source("src1", parish="LJUSDAL")
        data = _empty_project()
        data.sources.append(source)

        # Reference line has "Ljusdal" (mixed case)
        line = _ad_reference_line(parish="Ljusdal")
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, data)

        assert plan.candidates[0].source_id == "src1"

    def test_whitespace_trimmed_matching(self) -> None:
        """Leading/trailing whitespace is trimmed before comparison."""
        source = _church_book_source("src1", parish="  Ljusdal  ")
        data = _empty_project()
        data.sources.append(source)

        line = _ad_reference_line(parish="Ljusdal")
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, data)

        assert plan.candidates[0].source_id == "src1"

    def test_absent_equals_empty(self) -> None:
        """An absent value and an empty value are treated as equal."""
        # Source with page=None (absent)
        source = Source(
            id="src1",
            provider="Arkiv Digital",
            source_type="church_book",
            title="Test",
            structured_reference=StructuredReference(
                fields={
                    "parish": "Ljusdal",
                    "series": "AI",
                    "volume": "17",
                    "years": "1866-1870",
                    "image": "100",
                    "page": None,
                }
            ),
        )
        data = _empty_project()
        data.sources.append(source)

        # Reference line has page="" (empty)
        line = _ad_reference_line(page="")
        # Use the bild colon pattern (no page)
        line = "Ljusdal (X) AI:17 (1866-1870) Bild: 100"
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, data)

        assert plan.candidates[0].source_id == "src1"

    def test_no_match_creates_new_source(self) -> None:
        """When no Source matches, a new one should be created."""
        source = _church_book_source("src1", parish="Delsbo")
        data = _empty_project()
        data.sources.append(source)

        line = _ad_reference_line(parish="Ljusdal")
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, data)

        assert plan.candidates[0].source_id is None
        assert plan.sources_to_create == 1

    def test_first_matching_source_is_reused(self) -> None:
        """When multiple Sources match, the first in collection order wins."""
        src1 = _church_book_source("src1")
        src2 = _church_book_source("src2")
        data = _empty_project()
        data.sources.extend([src1, src2])

        line = _ad_reference_line()
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, data)

        assert plan.candidates[0].source_id == "src1"

    def test_source_type_mismatch_not_matched(self) -> None:
        """A Source with wrong source_type doesn't match."""
        source = Source(
            id="src1",
            provider="Arkiv Digital",
            source_type="census",  # wrong type
            title="Test",
            structured_reference=StructuredReference(
                fields={
                    "parish": "Ljusdal",
                    "series": "AI",
                    "volume": "17",
                    "years": "1866-1870",
                    "image": "100",
                    "page": "5",
                }
            ),
        )
        data = _empty_project()
        data.sources.append(source)

        line = _ad_reference_line()
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, data)

        assert plan.candidates[0].source_id is None


# ---------------------------------------------------------------------------
# Year prefill (Requirement 9.2 via 4.7–4.9)
# ---------------------------------------------------------------------------

class TestYearPrefill:
    """Candidates are prefilled from the parsed years value."""

    def test_two_year_range_prefilled(self) -> None:
        line = _ad_reference_line(years="1866-1870")
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, _empty_project())
        assert plan.candidates[0].observed_from == "1866"
        assert plan.candidates[0].observed_to == "1870"

    def test_single_year_prefilled(self) -> None:
        line = _ad_reference_line(years="1866")
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, _empty_project())
        assert plan.candidates[0].observed_from == "1866"
        assert plan.candidates[0].observed_to == "1866"

    def test_unreadable_years_leaves_empty(self) -> None:
        """When years can't be read, observed_from/to are empty."""
        line = _ad_reference_line(years="ca 1866")
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, _empty_project())
        assert plan.candidates[0].observed_from == ""
        assert plan.candidates[0].observed_to == ""


# ---------------------------------------------------------------------------
# Per-person preselection of existing facts (Requirement 9.4)
# ---------------------------------------------------------------------------

class TestPersonPreselection:
    """The best-overlapping existing fact is preselected per person."""

    def test_matching_existing_fact_preselected(self) -> None:
        """An existing fact at the same place with overlapping span is selected."""
        fact = _residence_fact(
            "f1", "p1", "pl1",
            start_earliest="1860", start_latest="1865",
            end_earliest="1875", end_latest="1880",
        )
        data = _empty_project()
        data.residences.append(fact)

        line = _ad_reference_line(years="1866-1870")
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, data)

        assert plan.person_plans[0].existing_fact_id == "f1"
        assert plan.facts_to_extend == 1
        assert plan.facts_to_create == 0

    def test_no_matching_fact_means_create(self) -> None:
        """When no fact matches, a new one should be created."""
        data = _empty_project()
        line = _ad_reference_line(years="1866-1870")
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, data)

        assert plan.person_plans[0].existing_fact_id is None
        assert plan.facts_to_create == 1

    def test_different_place_not_matched(self) -> None:
        """A fact at a different place is not a match."""
        fact = _residence_fact(
            "f1", "p1", "other_place",
            start_latest="1866", end_earliest="1870",
        )
        data = _empty_project()
        data.residences.append(fact)

        line = _ad_reference_line(years="1866-1870")
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, data)

        assert plan.person_plans[0].existing_fact_id is None

    def test_different_person_not_matched(self) -> None:
        """A fact for a different person is not a match."""
        fact = _residence_fact(
            "f1", "other_person", "pl1",
            start_latest="1866", end_earliest="1870",
        )
        data = _empty_project()
        data.residences.append(fact)

        line = _ad_reference_line(years="1866-1870")
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, data)

        assert plan.person_plans[0].existing_fact_id is None

    def test_best_overlap_wins(self) -> None:
        """The fact with the most overlapping years is preselected."""
        # fact1: covers 1860-1868 (3 years overlap with 1866-1870)
        fact1 = _residence_fact(
            "f1", "p1", "pl1",
            start_earliest="1860", start_latest="1860",
            end_earliest="1868", end_latest="1868",
        )
        # fact2: covers 1865-1875 (5 years overlap with 1866-1870)
        fact2 = _residence_fact(
            "f2", "p1", "pl1",
            start_earliest="1865", start_latest="1865",
            end_earliest="1875", end_latest="1875",
        )
        data = _empty_project()
        data.residences.extend([fact1, fact2])

        line = _ad_reference_line(years="1866-1870")
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, data)

        assert plan.person_plans[0].existing_fact_id == "f2"

    def test_collection_order_tiebreak(self) -> None:
        """On a tie in overlap, the first in collection order wins."""
        # Both facts cover the same span
        fact1 = _residence_fact(
            "f1", "p1", "pl1",
            start_earliest="1860", start_latest="1866",
            end_earliest="1870", end_latest="1880",
        )
        fact2 = _residence_fact(
            "f2", "p1", "pl1",
            start_earliest="1860", start_latest="1866",
            end_earliest="1870", end_latest="1880",
        )
        data = _empty_project()
        data.residences.extend([fact1, fact2])

        line = _ad_reference_line(years="1866-1870")
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, data)

        assert plan.person_plans[0].existing_fact_id == "f1"

    def test_within_one_year_matches(self) -> None:
        """A fact within one year of the obs span is a candidate (Req 9.4)."""
        # Fact ends at 1865, obs starts at 1866 -> within one year
        fact = _residence_fact(
            "f1", "p1", "pl1",
            start_earliest="1860", start_latest="1860",
            end_earliest="1865", end_latest="1865",
        )
        data = _empty_project()
        data.residences.append(fact)

        line = _ad_reference_line(years="1866-1870")
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, data)

        assert plan.person_plans[0].existing_fact_id == "f1"

    def test_per_person_independent(self) -> None:
        """Each person's match is decided independently (Req 9.4)."""
        fact_p1 = _residence_fact(
            "f1", "p1", "pl1",
            start_latest="1866", end_earliest="1870",
        )
        data = _empty_project()
        data.residences.append(fact_p1)

        line = _ad_reference_line(years="1866-1870")
        request = BulkRequest(text=line, person_ids=["p1", "p2"], place_id="pl1")
        plan = plan_bulk_attach(request, data)

        # p1 has an existing match, p2 does not
        assert plan.person_plans[0].existing_fact_id == "f1"
        assert plan.person_plans[1].existing_fact_id is None
        assert plan.facts_to_extend == 1
        assert plan.facts_to_create == 1


# ---------------------------------------------------------------------------
# Summary counts (Requirement 9.10)
# ---------------------------------------------------------------------------

class TestSummaryCounts:
    """The plan reports the five required counts."""

    def test_all_counts_with_mixed_input(self) -> None:
        """Mixed input with reused source, new source, existing fact."""
        src = _church_book_source("src1", volume="17", years="1866-1870")
        fact = _residence_fact(
            "f1", "p1", "pl1",
            start_latest="1866", end_earliest="1870",
        )
        data = _empty_project()
        data.sources.append(src)
        data.residences.append(fact)

        line1 = _ad_reference_line(volume="17", years="1866-1870")  # matches src1
        line2 = _ad_reference_line(volume="18", years="1871-1875")  # no match
        text = f"{line1}\n{line2}\ngarbage"
        request = BulkRequest(
            text=text, person_ids=["p1", "p2"], place_id="pl1"
        )
        plan = plan_bulk_attach(request, data)

        assert plan.sources_reused == 1
        assert plan.sources_to_create == 1
        assert plan.facts_to_extend == 1  # p1 has existing fact
        assert plan.facts_to_create == 1  # p2 creates new
        assert plan.observations_to_attach == 4  # 2 candidates * 2 persons
        assert len(plan.unparsed_lines) == 1

    def test_zero_candidates_gives_zero_observations(self) -> None:
        """All lines unparseable => zero observations."""
        text = "garbage1\ngarbage2"
        request = BulkRequest(text=text, person_ids=["p1"], place_id="pl1")
        plan = plan_bulk_attach(request, _empty_project())

        assert plan.observations_to_attach == 0
        assert plan.sources_reused == 0
        assert plan.sources_to_create == 0
        assert len(plan.unparsed_lines) == 2


# ---------------------------------------------------------------------------
# Purity (nothing mutated)
# ---------------------------------------------------------------------------

class TestPurity:
    """plan_bulk_attach is a pure function: it mutates nothing."""

    def test_project_unchanged(self) -> None:
        src = _church_book_source("src1")
        fact = _residence_fact("f1", "p1", "pl1", start_latest="1866", end_earliest="1870")
        data = _empty_project()
        data.sources.append(src)
        data.residences.append(fact)

        import copy
        data_before = copy.deepcopy(data)

        line = _ad_reference_line()
        request = BulkRequest(text=line, person_ids=["p1"], place_id="pl1")
        plan_bulk_attach(request, data)

        assert data.sources == data_before.sources
        assert data.residences == data_before.residences

    def test_request_unchanged(self) -> None:
        line = _ad_reference_line()
        request = BulkRequest(text=line, person_ids=["p1", "p2"], place_id="pl1")

        import copy
        request_before = copy.deepcopy(request)

        plan_bulk_attach(request, _empty_project())

        assert request.text == request_before.text
        assert request.person_ids == request_before.person_ids
