# Feature: residence-periods, Property 26: GEDCOM import maps every DATE line form to the specified Endpoints
"""Property-based test for GEDCOM import of RESI and Flytt structures.

Feature: residence-periods, Property 26: GEDCOM import maps every DATE line form
to the specified Endpoints.

For any RESI DATE line form importable by the GEDCOM importer:
- FROM/TO sets the core bounds (start.latest, end.earliest)
- BET/AND yields a start window (start.earliest, start.latest) with unknown end
- A plain DATE sets both core bounds to the same value
- Missing/uninterpretable DATE yields two unknown Endpoints while keeping place
  and observations
- EVEN TYPE Flytt becomes a flytt Event with resolved place and absent from_place

Uses a parametrized approach generating GEDCOM text fragments and verifying the
parsed results match the expected Endpoint shapes.

**Validates: Requirements 12.7, 12.8, 12.12, 12.13, 18.16**
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Optional

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from slaktbusken.gedcom.importer import GEDCOMImporter, _parse_resi_date
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Endpoint, ResidenceFact


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_MONTHS = [
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
]

_MONTH_TO_NUM = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}


@st.composite
def gedcom_years(draw: st.DrawFn) -> str:
    """Generate a GEDCOM year string (4-digit year)."""
    return str(draw(st.integers(min_value=1500, max_value=2100)))


@st.composite
def gedcom_month_years(draw: st.DrawFn) -> str:
    """Generate a GEDCOM month-year string like 'JAN 1850'."""
    month = draw(st.sampled_from(_MONTHS))
    year = draw(st.integers(min_value=1500, max_value=2100))
    return f"{month} {year}"


@st.composite
def gedcom_full_dates(draw: st.DrawFn) -> str:
    """Generate a GEDCOM full date string like '15 MAY 1875'."""
    day = draw(st.integers(min_value=1, max_value=28))
    month = draw(st.sampled_from(_MONTHS))
    year = draw(st.integers(min_value=1500, max_value=2100))
    return f"{day} {month} {year}"


@st.composite
def gedcom_dates(draw: st.DrawFn) -> str:
    """Generate any valid GEDCOM date (year, month-year, or full date)."""
    return draw(st.one_of(gedcom_years(), gedcom_month_years(), gedcom_full_dates()))


@st.composite
def gedcom_dates_with_optional_prefix(draw: st.DrawFn) -> str:
    """Generate a GEDCOM date optionally prefixed with ABT."""
    date = draw(gedcom_dates())
    use_prefix = draw(st.booleans())
    if use_prefix:
        return f"ABT {date}"
    return date


@st.composite
def place_names(draw: st.DrawFn) -> str:
    """Generate a simple GEDCOM place name string."""
    parts = draw(st.lists(
        st.text(
            alphabet=st.characters(categories=("L",), max_codepoint=255),
            min_size=2, max_size=12,
        ),
        min_size=1, max_size=3,
    ))
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gedcom_date_to_iso(raw: str) -> tuple[Optional[str], Optional[str]]:
    """Convert a GEDCOM date string to (ISO value, precision) for verification."""
    stripped = raw.strip()
    approx_match = re.match(r"^(ABT|BEF|AFT|EST|CAL)\s+(.+)$", stripped, re.IGNORECASE)
    is_approximate = approx_match is not None
    date_part = approx_match.group(2).strip() if approx_match else stripped

    full_match = re.match(r"^(\d{1,2})\s+([A-Z]{3})\s+(\d{4})$", date_part, re.IGNORECASE)
    if full_match:
        day = int(full_match.group(1))
        month_abbr = full_match.group(2).upper()
        year = full_match.group(3)
        month = _MONTH_TO_NUM.get(month_abbr)
        if month:
            return f"{year}-{month}-{day:02d}", "approximate" if is_approximate else "day"

    my_match = re.match(r"^([A-Z]{3})\s+(\d{4})$", date_part, re.IGNORECASE)
    if my_match:
        month_abbr = my_match.group(1).upper()
        year = my_match.group(2)
        month = _MONTH_TO_NUM.get(month_abbr)
        if month:
            return f"{year}-{month}", "approximate" if is_approximate else "month"

    year_match = re.match(r"^(\d{4})$", date_part)
    if year_match:
        return year_match.group(1), "approximate" if is_approximate else "year"

    return None, None


def _build_gedcom(
    *,
    resi_date: Optional[str] = None,
    resi_plac: Optional[str] = None,
    source_xref: Optional[str] = None,
) -> str:
    """Build a minimal GEDCOM file with one INDI and a RESI structure."""
    lines = [
        "0 HEAD",
        "1 SOUR Test",
        "1 GEDC",
        "2 VERS 5.5.1",
        "1 CHAR UTF-8",
    ]
    if source_xref:
        lines.append(f"0 {source_xref} SOUR")
        lines.append("1 TITL Test Source")
    lines.append("0 @I1@ INDI")
    lines.append("1 NAME Johan /Andersson/")
    lines.append("1 SEX M")
    lines.append("1 RESI")
    if resi_date is not None:
        lines.append(f"2 DATE {resi_date}")
    if resi_plac is not None:
        lines.append(f"2 PLAC {resi_plac}")
    if source_xref:
        lines.append(f"2 SOUR {source_xref}")
    lines.append("0 TRLR")
    return "\n".join(lines)


def _do_import(gedcom_text: str, tmp_dir: Path) -> ProjectData:
    """Run the GEDCOM importer on the given text and return project data."""
    project = ProjectData(project=ProjectMetadata(title="Test"))
    gedcom_file = tmp_dir / "test.ged"
    gedcom_file.write_text(gedcom_text, encoding="utf-8")
    translation_dir = tmp_dir / "translations"
    translation_dir.mkdir(exist_ok=True)
    importer = GEDCOMImporter(project, translation_dir)
    importer.import_file(gedcom_file)
    return project


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestGedcomImportDateMapping:
    """Property 26: GEDCOM import maps every DATE line form to the specified Endpoints.

    **Validates: Requirements 12.7, 12.8, 12.12, 12.13, 18.16**
    """

    @given(
        from_date=gedcom_dates_with_optional_prefix(),
        to_date=gedcom_dates_with_optional_prefix(),
        place=place_names(),
    )
    @settings(max_examples=100, deadline=None)
    def test_from_to_sets_core_bounds(
        self, from_date: str, to_date: str, place: str,
    ) -> None:
        """FROM/TO sets the core bounds (start.latest and end.earliest).

        **Validates: Requirements 12.7**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            date_line = f"FROM {from_date} TO {to_date}"
            gedcom_text = _build_gedcom(resi_date=date_line, resi_plac=place)
            project = _do_import(gedcom_text, Path(tmp_dir))

            assert len(project.residences) == 1
            fact = project.residences[0]
            from_iso, from_prec = _gedcom_date_to_iso(from_date)
            to_iso, to_prec = _gedcom_date_to_iso(to_date)

            assert fact.start.latest == from_iso
            assert fact.end.earliest == to_iso
            assert fact.start.earliest is None
            assert fact.end.latest is None
            assert fact.start.precision == from_prec
            assert fact.end.precision == to_prec

    @given(
        bet_date=gedcom_dates_with_optional_prefix(),
        and_date=gedcom_dates_with_optional_prefix(),
        place=place_names(),
    )
    @settings(max_examples=100, deadline=None)
    def test_bet_and_yields_start_window_with_unknown_end(
        self, bet_date: str, and_date: str, place: str,
    ) -> None:
        """BET/AND yields a start window with unknown end.

        **Validates: Requirements 12.8**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            date_line = f"BET {bet_date} AND {and_date}"
            gedcom_text = _build_gedcom(resi_date=date_line, resi_plac=place)
            project = _do_import(gedcom_text, Path(tmp_dir))

            assert len(project.residences) == 1
            fact = project.residences[0]
            bet_iso, _ = _gedcom_date_to_iso(bet_date)
            and_iso, and_prec = _gedcom_date_to_iso(and_date)

            assert fact.start.earliest == bet_iso
            assert fact.start.latest == and_iso
            assert fact.end.earliest is None
            assert fact.end.latest is None
            assert fact.start.precision == and_prec

    @given(
        plain_date=gedcom_dates_with_optional_prefix(),
        place=place_names(),
    )
    @settings(max_examples=100, deadline=None)
    def test_plain_date_sets_both_core_bounds(
        self, plain_date: str, place: str,
    ) -> None:
        """A plain DATE sets both core bounds to the same value.

        **Validates: Requirements 12.12**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            gedcom_text = _build_gedcom(resi_date=plain_date, resi_plac=place)
            project = _do_import(gedcom_text, Path(tmp_dir))

            assert len(project.residences) == 1
            fact = project.residences[0]
            expected_iso, expected_prec = _gedcom_date_to_iso(plain_date)

            assert fact.start.latest == expected_iso
            assert fact.end.earliest == expected_iso
            assert fact.start.earliest is None
            assert fact.end.latest is None

    @given(
        place=place_names(),
        use_bad_date=st.booleans(),
        bad_date=st.text(
            alphabet=st.characters(categories=("L", "N", "P")),
            min_size=1, max_size=20,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_missing_or_uninterpretable_date_yields_unknown_endpoints(
        self, place: str, use_bad_date: bool, bad_date: str,
    ) -> None:
        """Missing/uninterpretable DATE yields two unknown Endpoints.

        **Validates: Requirements 12.13**
        """
        if use_bad_date:
            result = _parse_resi_date(bad_date)
            assume(not result.interpretable)
            resi_date: Optional[str] = bad_date
        else:
            resi_date = None

        with tempfile.TemporaryDirectory() as tmp_dir:
            gedcom_text = _build_gedcom(
                resi_date=resi_date, resi_plac=place, source_xref="@S1@",
            )
            project = _do_import(gedcom_text, Path(tmp_dir))

            assert len(project.residences) == 1
            fact = project.residences[0]

            assert fact.start.earliest is None
            assert fact.start.latest is None
            assert fact.end.earliest is None
            assert fact.end.latest is None

            # Observations from SOUR are retained when sources exist
            if project.sources:
                assert len(fact.observations) >= 1

    @given(
        flytt_date=st.one_of(st.none(), gedcom_dates_with_optional_prefix()),
        place=st.one_of(st.none(), place_names()),
        type_case=st.sampled_from(["Flytt", "flytt", "FLYTT", "FLytt"]),
    )
    @settings(max_examples=100, deadline=None)
    def test_even_type_flytt_becomes_flytt_event(
        self, flytt_date: Optional[str], place: Optional[str], type_case: str,
    ) -> None:
        """EVEN TYPE Flytt becomes a flytt Event with absent from_place.

        **Validates: Requirements 18.16**
        """
        lines = [
            "0 HEAD",
            "1 SOUR Test",
            "1 GEDC",
            "2 VERS 5.5.1",
            "1 CHAR UTF-8",
            "0 @I1@ INDI",
            "1 NAME Johan /Andersson/",
            "1 SEX M",
            "1 EVEN",
            f"2 TYPE {type_case}",
        ]
        if flytt_date is not None:
            lines.append(f"2 DATE {flytt_date}")
        if place is not None:
            lines.append(f"2 PLAC {place}")
        lines.append("0 TRLR")
        gedcom_text = "\n".join(lines)

        with tempfile.TemporaryDirectory() as tmp_dir:
            project = _do_import(gedcom_text, Path(tmp_dir))

            flytt_events = [e for e in project.events if e.type == "flytt"]
            custom_events = [
                e for e in project.events if e.type == "custom_individual_event"
            ]

            assert len(flytt_events) == 1
            assert len(custom_events) == 0

            flytt_event = flytt_events[0]
            assert flytt_event.from_place is None

            if flytt_date is not None:
                expected_iso, _ = _gedcom_date_to_iso(flytt_date)
                if expected_iso is not None:
                    assert flytt_event.date is not None
                    assert flytt_event.date.value == expected_iso
            else:
                assert flytt_event.date is None

            assert len(project.residences) == 0
