# Feature: residence-periods, Property 13: Gap suggestions are phrased and sourced as specified
"""Property-based test for gap suggestion phrasing.

Feature: residence-periods, Property 13: Gap suggestions are phrased and sourced as specified

For any Residence_Fact with coverage gaps, the suggestion text uses the multi-year
form "period X\u2013Y saknar källa" when the gap spans two or more years and the
single-year form "år X saknar källa" when exactly one year is uncovered. The parish
and series values come from the church_book fields of the Source referenced by the
Observation whose covered years end immediately before the gap. An absent parish or
series value is omitted together with its separating space. At most five candidate
Sources are appended as "kontrollera {series}:{volume}", ordered by first year
ascending.

**Validates: Requirements 5.5, 5.6, 5.14**
"""

from __future__ import annotations

import re

from hypothesis import given, settings

from slaktbusken.model.residence import (
    observation_span_years,
)
from slaktbusken.services.residence_coverage import coverage_gaps
from tests.test_model.residence_strategies import (
    consistent_projects,
)


class TestGapSuggestionPhrasing:
    """Feature: residence-periods, Property 13: Gap suggestions are phrased and sourced as specified

    **Validates: Requirements 5.5, 5.6, 5.14**
    """

    @given(
        data=consistent_projects(
            min_residences=1,
            max_residences=4,
            max_sources=6,
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_gap_suggestion_phrasing_and_sourcing(self, data) -> None:
        """Property 13: Gap suggestions are phrased and sourced as specified.

        Multi-year gaps use "period X\u2013Y saknar källa", single-year gaps use
        "år X saknar källa", parish/series come from the preceding observation's
        source (church_book type), absent fields omitted with their space, at most
        5 candidates appended as "kontrollera {series}:{volume}".

        **Validates: Requirements 5.5, 5.6, 5.14**
        """
        for fact in data.residences:
            gaps = coverage_gaps(fact, data)

            for gap in gaps:
                suggestion = gap.suggestion

                # --- Multi-year vs single-year phrasing (Req 5.5, 5.14) ---
                if gap.first_year == gap.last_year:
                    # Single-year form
                    assert f"år {gap.first_year} saknar källa" in suggestion, (
                        f"Single-year gap {gap.first_year} should use "
                        f"'år {gap.first_year} saknar källa', got: {suggestion!r}"
                    )
                    assert "period" not in suggestion, (
                        f"Single-year gap should not contain 'period': {suggestion!r}"
                    )
                else:
                    # Multi-year form with en dash
                    expected_period = (
                        f"period {gap.first_year}\u2013{gap.last_year} saknar källa"
                    )
                    assert expected_period in suggestion, (
                        f"Multi-year gap {gap.first_year}-{gap.last_year} should use "
                        f"'{expected_period}', got: {suggestion!r}"
                    )
                    assert f"år {gap.first_year}" not in suggestion, (
                        f"Multi-year gap should not use 'år' form: {suggestion!r}"
                    )

                # --- Parish/series from the preceding Observation (Req 5.5) ---
                # Find the preceding observation: the one whose span ends at
                # gap.first_year - 1
                target_year = gap.first_year - 1
                preceding_obs = None
                for obs in fact.observations:
                    span = observation_span_years(obs)
                    if span is None:
                        continue
                    _, span_last = span
                    if span_last == target_year:
                        preceding_obs = obs
                        break

                parish = None
                series = None
                if preceding_obs is not None:
                    source_id = preceding_obs.source_ref.source_id
                    for source in data.sources:
                        if source.id == source_id:
                            if source.source_type == "church_book":
                                fields = source.structured_reference.fields
                                p = fields.get("parish")
                                s = fields.get("series")
                                if isinstance(p, str) and p.strip():
                                    parish = p.strip()
                                if isinstance(s, str) and s.strip():
                                    series = s.strip()
                            break

                # Verify the prefix: parish and series with absent values
                # omitted together with their separating space
                if parish and series:
                    assert suggestion.startswith(f"{parish} {series}: "), (
                        f"Expected prefix '{parish} {series}: ' in: {suggestion!r}"
                    )
                elif parish and not series:
                    assert suggestion.startswith(f"{parish}: "), (
                        f"Expected prefix '{parish}: ' in: {suggestion!r}"
                    )
                elif series and not parish:
                    assert suggestion.startswith(f"{series}: "), (
                        f"Expected prefix '{series}: ' in: {suggestion!r}"
                    )
                else:
                    # No parish, no series: suggestion starts directly with
                    # the period/year clause
                    assert (
                        suggestion.startswith("period ") or
                        suggestion.startswith("år ")
                    ), (
                        f"With no parish/series, suggestion should start with "
                        f"'period ' or 'år ', got: {suggestion!r}"
                    )

                # --- At most 5 candidates appended (Req 5.6) ---
                # Candidates are appended after " – kontrollera "
                kontrollera_marker = " \u2013 kontrollera "
                if kontrollera_marker in suggestion:
                    candidate_part = suggestion.split(kontrollera_marker, 1)[1]
                    # Candidates are comma-separated "{series}:{volume}" labels
                    candidate_labels = [
                        c.strip() for c in candidate_part.split(",")
                    ]
                    assert len(candidate_labels) <= 5, (
                        f"At most 5 candidates expected, got "
                        f"{len(candidate_labels)}: {candidate_labels}"
                    )
                    # Each candidate should be non-empty
                    for label in candidate_labels:
                        assert label, (
                            f"Empty candidate label in: {suggestion!r}"
                        )

                # --- Candidate volumes use "{series}:{volume}" form (Req 5.6) ---
                if kontrollera_marker in suggestion:
                    candidate_part = suggestion.split(kontrollera_marker, 1)[1]
                    candidate_labels = [
                        c.strip() for c in candidate_part.split(",")
                    ]
                    # Verify candidates match sources with correct parish/series
                    # whose years cover uncovered years
                    uncovered_years = set(
                        range(gap.first_year, gap.last_year + 1)
                    )
                    matching_sources = []
                    for source in data.sources:
                        if source.source_type != "church_book":
                            continue
                        fields = source.structured_reference.fields
                        src_parish = fields.get("parish")
                        src_series_val = fields.get("series")
                        if isinstance(src_parish, str):
                            src_parish = src_parish.strip() or None
                        else:
                            src_parish = None
                        if isinstance(src_series_val, str):
                            src_series_val = src_series_val.strip() or None
                        else:
                            src_series_val = None
                        if src_parish != parish or src_series_val != series:
                            continue
                        # Check if the source's years contain any uncovered year
                        years_field = fields.get("years")
                        if not years_field or not isinstance(years_field, str):
                            continue
                        years_str = years_field.strip()
                        # Parse years value
                        m = re.match(
                            r"^\s*(\d{4})\s*[-\u2013]\s*(\d{4})\s*$", years_str
                        )
                        if m:
                            first_y = int(m.group(1))
                            last_y = int(m.group(2))
                            if first_y <= last_y:
                                source_years = set(range(first_y, last_y + 1))
                                if source_years & uncovered_years:
                                    matching_sources.append(source)
                                continue
                        m_single = re.match(r"^\s*(\d{4})\s*$", years_str)
                        if m_single:
                            y = int(m_single.group(1))
                            if y in uncovered_years:
                                matching_sources.append(source)

                    # The number of candidates shown should not exceed the
                    # number of matching sources (capped at 5)
                    assert len(candidate_labels) <= min(5, len(matching_sources)), (
                        f"More candidates shown ({len(candidate_labels)}) than "
                        f"matching sources ({len(matching_sources)}) for gap "
                        f"{gap.first_year}-{gap.last_year}"
                    )
