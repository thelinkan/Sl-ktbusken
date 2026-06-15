"""Unit tests and property-based tests for the GEDCOM exporter module.

Tests verify GEDCOM 5.5.1 compliant output structure, deterministic ID
generation, place hierarchy resolution, source citation handling, and
omission tracking.

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 22.4, 24.4
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from slaktbusken.gedcom.exporter import ExportResult, GEDCOMExporter
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.source import Source, StructuredReference

from tests.conftest import (
    person_strategy,
    family_strategy,
    place_strategy,
    source_strategy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_project_data(
    persons: list[Person] | None = None,
    families: list[Family] | None = None,
    sources: list[Source] | None = None,
    events: list[Event] | None = None,
    places: list[Place] | None = None,
) -> ProjectData:
    """Create a minimal ProjectData for testing."""
    return ProjectData(
        format="släktbuske-file",
        version="0.1",
        project=ProjectMetadata(title="Test"),
        persons=persons or [],
        families=families or [],
        events=events or [],
        places=places or [],
        sources=sources or [],
    )


# ---------------------------------------------------------------------------
# Unit tests: GEDCOM output structure (HEAD, TRLR, INDI, FAM, SOUR)
# ---------------------------------------------------------------------------


class TestGEDCOMOutputStructure:
    """Tests for valid GEDCOM 5.5.1 output structure."""

    def test_empty_export_has_head_and_trlr(self, tmp_path: Path) -> None:
        """An export of empty data produces HEAD and TRLR records."""
        exporter = GEDCOMExporter()
        data = _minimal_project_data()
        output = tmp_path / "test.ged"

        exporter.export(data, output)

        content = output.read_text(encoding="utf-8")
        lines = content.strip().split("\n")

        assert lines[0] == "0 HEAD"
        assert lines[-1] == "0 TRLR"

    def test_head_contains_required_fields(self, tmp_path: Path) -> None:
        """HEAD record contains SOUR, GEDC, VERS, FORM, CHAR."""
        exporter = GEDCOMExporter()
        data = _minimal_project_data()
        output = tmp_path / "test.ged"

        exporter.export(data, output)

        content = output.read_text(encoding="utf-8")
        assert "1 SOUR Släktbusken" in content
        assert "2 VERS 5.5.1" in content
        assert "2 FORM LINEAGE-LINKED" in content
        assert "1 CHAR UTF-8" in content

    def test_person_creates_indi_record(self, tmp_path: Path) -> None:
        """A person produces an INDI record with NAME and SEX."""
        person = Person(
            id="person_1",
            sex="M",
            names=[Name(type="birth", given="Johan", surname="Andersson")],
        )
        exporter = GEDCOMExporter()
        data = _minimal_project_data(persons=[person])
        output = tmp_path / "test.ged"

        exporter.export(data, output)

        content = output.read_text(encoding="utf-8")
        assert "0 @I1@ INDI" in content
        assert "1 NAME Johan /Andersson/" in content
        assert "1 SEX M" in content

    def test_family_creates_fam_record(self, tmp_path: Path) -> None:
        """A family produces a FAM record with HUSB, WIFE, CHIL."""
        family = Family(
            id="family_1",
            partners=[
                FamilyPartner(person_id="person_1", role="husband"),
                FamilyPartner(person_id="person_2", role="wife"),
            ],
            children=["person_3"],
        )
        exporter = GEDCOMExporter()
        data = _minimal_project_data(families=[family])
        output = tmp_path / "test.ged"

        exporter.export(data, output)

        content = output.read_text(encoding="utf-8")
        assert "0 @F1@ FAM" in content
        assert "1 HUSB @I1@" in content
        assert "1 WIFE @I2@" in content
        assert "1 CHIL @I3@" in content

    def test_source_creates_sour_record(self, tmp_path: Path) -> None:
        """A source produces a SOUR record with TITL and TEXT."""
        source = Source(
            id="source_1",
            provider="Riksarkivet",
            source_type="church_book",
            title="Ljusdal husförhör",
            reference_text="Ljusdal (X) AI:23d",
        )
        exporter = GEDCOMExporter()
        data = _minimal_project_data(sources=[source])
        output = tmp_path / "test.ged"

        exporter.export(data, output)

        content = output.read_text(encoding="utf-8")
        assert "0 @S1@ SOUR" in content
        assert "1 TITL Ljusdal husförhör" in content
        assert "1 TEXT" in content

    def test_file_is_utf8(self, tmp_path: Path) -> None:
        """The output file is encoded in UTF-8."""
        person = Person(
            id="person_1",
            sex="F",
            names=[Name(type="birth", given="Ångström", surname="Öberg")],
        )
        exporter = GEDCOMExporter()
        data = _minimal_project_data(persons=[person])
        output = tmp_path / "test.ged"

        exporter.export(data, output)

        # Read as bytes and verify UTF-8 decoding works
        raw = output.read_bytes()
        content = raw.decode("utf-8")
        assert "Ångström" in content
        assert "Öberg" in content


# ---------------------------------------------------------------------------
# Unit tests: Deterministic ID generation
# ---------------------------------------------------------------------------


class TestDeterministicIDs:
    """Tests for deterministic GEDCOM ID generation from App_JSON IDs."""

    def test_person_id_mapping(self) -> None:
        """person_1 maps to @I1@."""
        exporter = GEDCOMExporter()
        assert exporter._to_gedcom_id("person_1") == "@I1@"

    def test_family_id_mapping(self) -> None:
        """family_42 maps to @F42@."""
        exporter = GEDCOMExporter()
        assert exporter._to_gedcom_id("family_42") == "@F42@"

    def test_source_id_mapping(self) -> None:
        """source_3 maps to @S3@."""
        exporter = GEDCOMExporter()
        assert exporter._to_gedcom_id("source_3") == "@S3@"

    def test_same_input_same_output(self) -> None:
        """Same input always produces the same output."""
        exporter = GEDCOMExporter()
        result1 = exporter._to_gedcom_id("person_99")
        result2 = exporter._to_gedcom_id("person_99")
        assert result1 == result2

    def test_different_inputs_different_outputs(self) -> None:
        """Different inputs produce different outputs."""
        exporter = GEDCOMExporter()
        ids = {
            exporter._to_gedcom_id("person_1"),
            exporter._to_gedcom_id("person_2"),
            exporter._to_gedcom_id("family_1"),
            exporter._to_gedcom_id("source_1"),
        }
        assert len(ids) == 4


# ---------------------------------------------------------------------------
# Unit tests: Place hierarchy resolution
# ---------------------------------------------------------------------------


class TestPlaceHierarchy:
    """Tests for place hierarchy resolution."""

    def test_single_place(self, tmp_path: Path) -> None:
        """A single place with no parent returns just its name."""
        exporter = GEDCOMExporter()
        exporter._places = {
            "place_1": Place(id="place_1", type="country", name="Sverige"),
        }
        assert exporter._resolve_place_hierarchy("place_1") == "Sverige"

    def test_full_hierarchy(self, tmp_path: Path) -> None:
        """Full hierarchy from church to country."""
        exporter = GEDCOMExporter()
        exporter._places = {
            "place_1": Place(
                id="place_1", type="church", name="Ljusdals kyrka",
                parent_place_id="place_2",
            ),
            "place_2": Place(
                id="place_2", type="parish", name="Ljusdal",
                parent_place_id="place_3",
            ),
            "place_3": Place(
                id="place_3", type="county", name="Gävleborgs län",
                parent_place_id="place_4",
            ),
            "place_4": Place(
                id="place_4", type="country", name="Sverige",
            ),
        }
        result = exporter._resolve_place_hierarchy("place_1")
        assert result == "Ljusdals kyrka, Ljusdal, Gävleborgs län, Sverige"

    def test_unknown_place_returns_empty(self) -> None:
        """An unknown place ID returns an empty string."""
        exporter = GEDCOMExporter()
        exporter._places = {}
        assert exporter._resolve_place_hierarchy("place_999") == ""

    def test_circular_reference_does_not_loop(self) -> None:
        """Circular parent references do not cause infinite loops."""
        exporter = GEDCOMExporter()
        exporter._places = {
            "place_1": Place(
                id="place_1", type="parish", name="A",
                parent_place_id="place_2",
            ),
            "place_2": Place(
                id="place_2", type="county", name="B",
                parent_place_id="place_1",
            ),
        }
        result = exporter._resolve_place_hierarchy("place_1")
        assert result == "A, B"


# ---------------------------------------------------------------------------
# Unit tests: Date formatting
# ---------------------------------------------------------------------------


class TestDateFormatting:
    """Tests for ISO to GEDCOM date format conversion."""

    def test_full_date(self) -> None:
        """ISO full date converts to GEDCOM format."""
        exporter = GEDCOMExporter()
        date = DateValue(value="1900-01-15", precision="day")
        assert exporter._format_date(date) == "15 JAN 1900"

    def test_month_year(self) -> None:
        """ISO month-year converts to GEDCOM format."""
        exporter = GEDCOMExporter()
        date = DateValue(value="1900-03", precision="month")
        assert exporter._format_date(date) == "MAR 1900"

    def test_year_only(self) -> None:
        """ISO year-only stays as year."""
        exporter = GEDCOMExporter()
        date = DateValue(value="1900", precision="year")
        assert exporter._format_date(date) == "1900"

    def test_approximate_date(self) -> None:
        """Approximate precision adds ABT prefix."""
        exporter = GEDCOMExporter()
        date = DateValue(value="1900", precision="approximate")
        assert exporter._format_date(date) == "ABT 1900"

    def test_approximate_full_date(self) -> None:
        """Approximate precision on full date adds ABT prefix."""
        exporter = GEDCOMExporter()
        date = DateValue(value="1900-06-15", precision="approximate")
        assert exporter._format_date(date) == "ABT 15 JUN 1900"


# ---------------------------------------------------------------------------
# Unit tests: Omission tracking
# ---------------------------------------------------------------------------


class TestOmissionTracking:
    """Tests for omission tracking of non-GEDCOM data."""

    def test_no_omissions_for_minimal_data(self) -> None:
        """Minimal data with no DNA/media/notes has no omissions."""
        exporter = GEDCOMExporter()
        data = _minimal_project_data()
        omitted = exporter._collect_omissions(data)
        assert omitted == {}

    def test_dna_data_tracked(self) -> None:
        """DNA-related entities are tracked as omissions."""
        from slaktbusken.model.dna import DnaCompany, DnaProfile

        exporter = GEDCOMExporter()
        data = _minimal_project_data()
        data.dna_companies = [
            DnaCompany(id="dnacompany_1", name="TestCo"),
        ]
        data.dna_profiles = [
            DnaProfile(
                id="dnaprofile_1",
                person_id="person_1",
                company_id="dnacompany_1",
                test_type="autosomal",
            ),
        ]

        omitted = exporter._collect_omissions(data)
        assert "DNA-företag" in omitted
        assert omitted["DNA-företag"] == 1
        assert "DNA-profiler" in omitted
        assert omitted["DNA-profiler"] == 1

    def test_research_notes_tracked(self) -> None:
        """Research notes are tracked as omissions."""
        from slaktbusken.model.research_note import ResearchNote

        exporter = GEDCOMExporter()
        data = _minimal_project_data()
        data.research_notes = [
            ResearchNote(id="note_1", title="Test", text="Content"),
        ]

        omitted = exporter._collect_omissions(data)
        assert "Forskningsanteckningar" in omitted
        assert omitted["Forskningsanteckningar"] == 1

    def test_media_items_tracked(self) -> None:
        """Media items are tracked as omissions."""
        from slaktbusken.model.media import MediaItem

        exporter = GEDCOMExporter()
        data = _minimal_project_data()
        data.media = [
            MediaItem(id="media_1", type="photo", file="photo.jpg", title="Test"),
        ]

        omitted = exporter._collect_omissions(data)
        assert "Medieobjekt" in omitted
        assert omitted["Medieobjekt"] == 1


# ---------------------------------------------------------------------------
# Unit tests: Source citation resolution
# ---------------------------------------------------------------------------


class TestSourceCitationResolution:
    """Tests for source citation resolution in GEDCOM export."""

    def test_reference_text_used_as_citation(self, tmp_path: Path) -> None:
        """Source with reference_text produces TEXT line in GEDCOM."""
        source = Source(
            id="source_1",
            provider="Riksarkivet",
            source_type="other",
            title="Husförhör",
            reference_text="Ljusdal AI:23d (1883-1887)",
        )
        exporter = GEDCOMExporter()
        data = _minimal_project_data(sources=[source])
        output = tmp_path / "test.ged"

        exporter.export(data, output)

        content = output.read_text(encoding="utf-8")
        assert "1 TEXT Ljusdal AI:23d (1883-1887)" in content

    def test_structured_reference_used_when_no_reference_text(
        self, tmp_path: Path
    ) -> None:
        """Source with structured_reference fields produces citation text."""
        source = Source(
            id="source_1",
            provider="Riksarkivet",
            source_type="church_book",
            title="Ljusdal husförhör",
            reference_text="",
            structured_reference=StructuredReference(
                fields={
                    "parish": "Ljusdal",
                    "county_code": "X",
                    "series": "AI",
                    "volume": "23d",
                    "years": "1883-1887",
                    "image": 23,
                    "page": 915,
                }
            ),
        )
        exporter = GEDCOMExporter()
        data = _minimal_project_data(sources=[source])
        output = tmp_path / "test.ged"

        exporter.export(data, output)

        content = output.read_text(encoding="utf-8")
        assert "1 TEXT Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915" in content


# ---------------------------------------------------------------------------
# Unit tests: Export result
# ---------------------------------------------------------------------------


class TestExportResult:
    """Tests for ExportResult correctness."""

    def test_counts_match_input(self, tmp_path: Path) -> None:
        """ExportResult counts match the number of entities exported."""
        persons = [
            Person(id="person_1", sex="M", names=[Name(type="birth", given="A", surname="B")]),
            Person(id="person_2", sex="F", names=[Name(type="birth", given="C", surname="D")]),
        ]
        families = [
            Family(id="family_1", partners=[], children=[]),
        ]
        sources = [
            Source(id="source_1", provider="P", source_type="other", title="T"),
            Source(id="source_2", provider="P", source_type="other", title="T2"),
            Source(id="source_3", provider="P", source_type="other", title="T3"),
        ]

        exporter = GEDCOMExporter()
        data = _minimal_project_data(persons=persons, families=families, sources=sources)
        output = tmp_path / "test.ged"

        result = exporter.export(data, output)

        assert result.persons_exported == 2
        assert result.families_exported == 1
        assert result.sources_exported == 3


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------


class TestPropertyDeterministicIDs:
    """Property 4: Deterministic GEDCOM ID generation.

    **Validates: Requirements 5.2, 24.4**
    """

    @given(n=st.integers(min_value=1, max_value=9999))
    @settings(max_examples=200)
    def test_same_input_produces_same_output(self, n: int) -> None:
        """Same App_JSON ID always produces the same GEDCOM ID (deterministic).

        **Validates: Requirements 5.2**
        """
        exporter = GEDCOMExporter()
        app_id = f"person_{n}"
        result1 = exporter._to_gedcom_id(app_id)
        result2 = exporter._to_gedcom_id(app_id)
        assert result1 == result2

    @given(
        n1=st.integers(min_value=1, max_value=9999),
        n2=st.integers(min_value=1, max_value=9999),
    )
    @settings(max_examples=200)
    def test_different_inputs_produce_different_outputs(
        self, n1: int, n2: int
    ) -> None:
        """Different App_JSON IDs map to different GEDCOM IDs (injective).

        **Validates: Requirements 5.2**
        """
        assume(n1 != n2)
        exporter = GEDCOMExporter()
        id1 = exporter._to_gedcom_id(f"person_{n1}")
        id2 = exporter._to_gedcom_id(f"person_{n2}")
        assert id1 != id2

    @given(
        prefix=st.sampled_from(["person", "family", "source"]),
        n=st.integers(min_value=1, max_value=9999),
    )
    @settings(max_examples=200)
    def test_different_prefixes_produce_different_ids(
        self, prefix: str, n: int
    ) -> None:
        """Same numeric suffix with different prefixes produces different IDs.

        **Validates: Requirements 5.2**
        """
        exporter = GEDCOMExporter()
        ids = set()
        for pfx in ["person", "family", "source"]:
            ids.add(exporter._to_gedcom_id(f"{pfx}_{n}"))
        # All three should be different
        assert len(ids) == 3


class TestPropertyPlaceHierarchy:
    """Property 5: Place hierarchy resolution.

    **Validates: Requirements 5.3**
    """

    @given(
        names=st.lists(
            st.text(
                alphabet=st.characters(categories=("L", "N")),
                min_size=1,
                max_size=50,
            ),
            min_size=1,
            max_size=6,
        )
    )
    @settings(max_examples=200)
    def test_hierarchy_produces_correct_comma_separated_string(
        self, names: list[str]
    ) -> None:
        """For any valid hierarchy, resolution produces comma-separated names
        from most specific to least specific, containing exactly all names.

        **Validates: Requirements 5.3**
        """
        # Names must not contain the separator to allow clean splitting
        assume(all(", " not in name for name in names))

        # Build a hierarchy chain: names[0] is most specific, names[-1] is root
        exporter = GEDCOMExporter()
        places: dict[str, Place] = {}

        for i, name in enumerate(names):
            place_id = f"place_{i + 1}"
            parent_id = f"place_{i + 2}" if i < len(names) - 1 else None
            places[place_id] = Place(
                id=place_id,
                type="parish",
                name=name,
                parent_place_id=parent_id,
            )

        exporter._places = places

        result = exporter._resolve_place_hierarchy("place_1")

        # Verify: result is comma-separated names in order
        parts = result.split(", ")
        assert parts == names

    @given(
        names=st.lists(
            st.text(
                alphabet=st.characters(categories=("L", "N")),
                min_size=1,
                max_size=50,
            ),
            min_size=2,
            max_size=6,
        )
    )
    @settings(max_examples=200)
    def test_hierarchy_contains_all_places(self, names: list[str]) -> None:
        """Resolution contains exactly the names of all places in the chain.

        **Validates: Requirements 5.3**
        """
        exporter = GEDCOMExporter()
        places: dict[str, Place] = {}

        for i, name in enumerate(names):
            place_id = f"place_{i + 1}"
            parent_id = f"place_{i + 2}" if i < len(names) - 1 else None
            places[place_id] = Place(
                id=place_id,
                type="parish",
                name=name,
                parent_place_id=parent_id,
            )

        exporter._places = places
        result = exporter._resolve_place_hierarchy("place_1")

        # Verify all names are present
        for name in names:
            assert name in result
