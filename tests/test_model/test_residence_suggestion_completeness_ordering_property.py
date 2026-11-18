# Feature: residence-periods, Property 14: Open-endpoint, timeline-gap and person-check reporting is complete and ordered
"""Property-based test for suggestion completeness and ordering.

Feature: residence-periods, Property 14: Open-endpoint, timeline-gap and person-check reporting is complete and ordered

For any consistent project, open-endpoint suggestions report one per open bound
(absent start.earliest → "beginning", absent end.latest → "end"), at most two
per fact; timeline gaps are the maximal runs of years in no Possible_Span with
birth/death excluded; findings from the check engine are ordered by first year
ascending with open-endpoint findings last.

**Validates: Requirements 5.7, 5.8, 5.9, 5.15**
"""

from __future__ import annotations

from hypothesis import given, settings

from slaktbusken.model.residence import (
    EndpointKind,
    classify_endpoint,
    possible_span,
)
from slaktbusken.persistence.settings_io import PersonCheckConfig
from slaktbusken.services.checks.residence_checks import check_residence
from slaktbusken.services.person_check_engine import CheckContext
from slaktbusken.services.residence_coverage import (
    open_endpoint_suggestions,
    timeline_gaps,
)
from tests.test_model.residence_strategies import consistent_projects


class TestSuggestionCompletenessAndOrdering:
    """Feature: residence-periods, Property 14: Open-endpoint, timeline-gap and person-check reporting is complete and ordered

    **Validates: Requirements 5.7, 5.8, 5.9, 5.15**
    """

    @given(
        data=consistent_projects(
            min_persons=1,
            max_persons=2,
            min_residences=1,
            max_residences=4,
            max_events=4,
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_open_endpoint_suggestions_completeness_and_ordering(self, data) -> None:
        """Property 14: Open-endpoint suggestions report one per open bound,
        naming "beginning" for absent start.earliest and "end" for absent
        end.latest, at most two per fact; timeline gaps are the maximal runs of
        years in no Possible_Span with birth/death excluded; and check engine
        findings are ordered by first year ascending with open-endpoint findings
        last.

        **Validates: Requirements 5.7, 5.8, 5.9, 5.15**
        """
        for fact in data.residences:
            suggestions = open_endpoint_suggestions(fact)

            # --- At most two suggestions per fact (Req 5.7) ---
            assert len(suggestions) <= 2, (
                f"Expected at most 2 open-endpoint suggestions for fact "
                f"{fact.id}, got {len(suggestions)}"
            )

            # --- One suggestion per open bound ---
            start_kind = classify_endpoint(fact.start)
            end_kind = classify_endpoint(fact.end)

            # start.earliest absent means OPEN_LATEST or UNKNOWN
            start_open = start_kind in (EndpointKind.OPEN_LATEST, EndpointKind.UNKNOWN)
            # end.latest absent means OPEN_EARLIEST or UNKNOWN
            end_open = end_kind in (EndpointKind.OPEN_EARLIEST, EndpointKind.UNKNOWN)

            start_suggestions = [s for s in suggestions if s.side == "start"]
            end_suggestions = [s for s in suggestions if s.side == "end"]

            if start_open:
                assert len(start_suggestions) == 1, (
                    f"Expected 1 start suggestion for open start on fact "
                    f"{fact.id}, got {len(start_suggestions)}"
                )
                # The suggestion should name "början"
                assert "början" in start_suggestions[0].suggestion, (
                    f"Start suggestion should name 'början', "
                    f"got: {start_suggestions[0].suggestion!r}"
                )
            else:
                assert len(start_suggestions) == 0, (
                    f"Expected 0 start suggestions for non-open start on fact "
                    f"{fact.id}, got {len(start_suggestions)}"
                )

            if end_open:
                assert len(end_suggestions) == 1, (
                    f"Expected 1 end suggestion for open end on fact "
                    f"{fact.id}, got {len(end_suggestions)}"
                )
                # The suggestion should name "slutet"
                assert "slutet" in end_suggestions[0].suggestion, (
                    f"End suggestion should name 'slutet', "
                    f"got: {end_suggestions[0].suggestion!r}"
                )
            else:
                assert len(end_suggestions) == 0, (
                    f"Expected 0 end suggestions for non-open end on fact "
                    f"{fact.id}, got {len(end_suggestions)}"
                )

            # Each suggestion references the correct fact
            for s in suggestions:
                assert s.residence_id == fact.id

        # --- Timeline gaps: maximal runs of years in no Possible_Span (Req 5.8, 5.15) ---
        for person in data.persons:
            person_facts = [
                f for f in data.residences if f.person_id == person.id
            ]
            if len(person_facts) < 2:
                # A single fact or no facts yields no timeline gap
                gaps = timeline_gaps(person.id, data)
                assert gaps == [], (
                    f"Expected no timeline gaps for person {person.id} with "
                    f"{len(person_facts)} fact(s), got {len(gaps)}"
                )
                continue

            gaps = timeline_gaps(person.id, data)

            # All gaps belong to this person
            for gap in gaps:
                assert gap.person_id == person.id

            # Gaps are ordered by first_year ascending
            for i in range(1, len(gaps)):
                assert gaps[i].first_year > gaps[i - 1].last_year, (
                    f"Timeline gaps not ordered for person {person.id}: "
                    f"gap {i-1} ends at {gaps[i-1].last_year}, "
                    f"gap {i} starts at {gaps[i].first_year}"
                )

            # Each gap is a maximal run: every year in a gap is in no Possible_Span
            spans = [possible_span(f) for f in person_facts]
            for gap in gaps:
                for year in range(gap.first_year, gap.last_year + 1):
                    covered = any(s.overlaps_year(year) for s in spans)
                    assert not covered, (
                        f"Year {year} in timeline gap "
                        f"({gap.first_year}–{gap.last_year}) is covered by "
                        f"a Possible_Span for person {person.id}"
                    )

            # The years immediately adjacent to each gap should be covered
            # (or outside the bounded range or excluded by birth/death)
            # This verifies maximality: the gap cannot be extended
            bounded_years = []
            for s in spans:
                if s.first is not None:
                    bounded_years.append(s.first.year)
                if s.last is not None:
                    bounded_years.append(s.last.year)

            if bounded_years:
                lowest = min(bounded_years)
                highest = max(bounded_years)

                # Get birth/death exclusion bounds
                birth_year = None
                death_year = None
                for event in data.events:
                    is_participant = any(
                        p.person_id == person.id for p in event.participants
                    )
                    if not is_participant or event.date is None:
                        continue
                    from slaktbusken.model.date_span import year_of
                    event_year = year_of(event.date.value)
                    if event_year is None:
                        continue
                    if event.type == "birth":
                        if birth_year is None or event_year < birth_year:
                            birth_year = event_year
                    elif event.type == "death":
                        if death_year is None or event_year > death_year:
                            death_year = event_year

                effective_start = lowest
                effective_end = highest
                if birth_year is not None:
                    effective_start = max(effective_start, birth_year)
                if death_year is not None:
                    effective_end = min(effective_end, death_year)

                for gap in gaps:
                    # Year before gap should be covered or outside range
                    before = gap.first_year - 1
                    if before >= effective_start:
                        covered_before = any(
                            s.overlaps_year(before) for s in spans
                        )
                        assert covered_before, (
                            f"Year {before} before gap "
                            f"({gap.first_year}–{gap.last_year}) should be "
                            f"covered (maximality) for person {person.id}"
                        )

                    # Year after gap should be covered or outside range
                    after = gap.last_year + 1
                    if after <= effective_end:
                        covered_after = any(
                            s.overlaps_year(after) for s in spans
                        )
                        assert covered_after, (
                            f"Year {after} after gap "
                            f"({gap.first_year}–{gap.last_year}) should be "
                            f"covered (maximality) for person {person.id}"
                        )

        # --- Check engine ordering (Req 5.9) ---
        # The check_residence function should order findings by first year
        # ascending, with open-endpoint findings last.
        config = PersonCheckConfig()
        for person in data.persons:
            context = CheckContext(project_data=data)
            findings = check_residence(person, [], [], config, context)

            # Identify which findings are open-endpoint (they sort last)
            # Open-endpoint suggestions have characteristic phrasing
            open_endpoint_msgs = set()
            person_facts = [
                f for f in data.residences if f.person_id == person.id
            ]
            for fact in person_facts:
                for s in open_endpoint_suggestions(fact):
                    open_endpoint_msgs.add(s.suggestion)

            # Separate findings into year-based and open-endpoint-based
            year_findings = []
            open_findings = []
            for f in findings:
                if f.message in open_endpoint_msgs:
                    open_findings.append(f)
                else:
                    year_findings.append(f)

            # Year-based findings must come before open-endpoint findings
            if year_findings and open_findings:
                last_year_idx = findings.index(year_findings[-1])
                first_open_idx = findings.index(open_findings[0])
                assert last_year_idx < first_open_idx, (
                    f"Year-based findings should precede open-endpoint findings "
                    f"for person {person.id}"
                )

            # Year-based findings should be ordered (non-strictly) ascending
            # by the year they reference. We can't directly extract the year
            # from the message, but we verify the overall ordering is stable:
            # the findings list should be the same as sorting by our expected key.
            # Since check_residence uses (first_year, is_open) as sort key,
            # we just verify the open-endpoint findings come last.
            # The remaining findings (gaps and timeline gaps) should be in
            # ascending order by extracting years from their messages.
            import re
            year_values = []
            for f in year_findings:
                # Try to extract a year from the message
                m = re.search(r"(\d{4})", f.message)
                if m:
                    year_values.append(int(m.group(1)))

            # The extracted years should be in non-decreasing order
            for i in range(1, len(year_values)):
                assert year_values[i] >= year_values[i - 1], (
                    f"Findings not in ascending year order for person "
                    f"{person.id}: year {year_values[i]} follows "
                    f"{year_values[i-1]} at positions {i-1}, {i}"
                )
