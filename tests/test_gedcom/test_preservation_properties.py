"""Preservation property tests for GEDCOM import behavior.

These tests capture the EXISTING correct behavior of the GEDCOM importer
on the unfixed code. They MUST PASS on both unfixed and fixed code — any
failure after fixes are applied indicates a regression.

Observation-first methodology: each test observes what the code actually
does for non-buggy inputs and asserts that behavior is preserved.

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from slaktbusken.gedcom.importer import GEDCOMImporter, ImportResult
from slaktbusken.model.project import ProjectData, ProjectMetadata


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_project() -> ProjectData:
    """An empty project data container."""
    return ProjectData(
        project=ProjectMetadata(title="Test Project"),
    )


@pytest.fixture
def translation_dir(tmp_path: Path) -> Path:
    """A temporary directory for translation files."""
    d = tmp_path / "translation"
    d.mkdir()
    return d


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to the GEDCOM test fixtures directory."""
    return Path(__file__).parent.parent / "fixtures" / "gedcom"


# ---------------------------------------------------------------------------
# Property: Full initial import creates all entities correctly (Req 3.1)
# ---------------------------------------------------------------------------


class TestPreservationFullInitialImport:
    """**Validates: Requirements 3.1**

    For any GEDCOM file imported as initial import, all persons, families,
    events, and places are created correctly.

    Observed on UNFIXED code:
    - Test-1.ged: 3 persons, 1 family, 3 events (birth per person), 6 places
    - Each person has exactly 1 birth event with correct date and place
    - Family has correct partners and children
    - Places form correct parent-child hierarchies (parish → county)
    """

    def test_initial_import_creates_correct_persons(
        self, empty_project: ProjectData, translation_dir: Path, fixtures_dir: Path
    ) -> None:
        """Initial import of Test-1.ged creates exactly 3 persons with correct names."""
        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(fixtures_dir / "Test-1.ged")

        assert result.persons_added == 3
        assert len(empty_project.persons) == 3

        # Verify person names
        names = sorted(
            (p.names[0].given, p.names[0].surname) for p in empty_project.persons
        )
        assert names == [
            ("Anders", "Persson"),
            ("Bettan", "Persson"),
            ("Stina", "Jansson"),
        ]

    def test_initial_import_creates_correct_family(
        self, empty_project: ProjectData, translation_dir: Path, fixtures_dir: Path
    ) -> None:
        """Initial import of Test-1.ged creates 1 family with correct structure."""
        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(fixtures_dir / "Test-1.ged")

        assert len(empty_project.families) == 1
        family = empty_project.families[0]

        # Family has 2 partners (husband + wife) and 1 child
        assert len(family.partners) == 2
        assert len(family.children) == 1

        # Verify partner roles
        roles = {p.role for p in family.partners}
        assert roles == {"husband", "wife"}

    def test_initial_import_creates_correct_events(
        self, empty_project: ProjectData, translation_dir: Path, fixtures_dir: Path
    ) -> None:
        """Initial import creates 1 birth event per person with correct data."""
        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(fixtures_dir / "Test-1.ged")

        assert len(empty_project.events) == 3

        # All events are birth events
        assert all(e.type == "birth" for e in empty_project.events)

        # Each event has exactly 1 participant with role "subject"
        for event in empty_project.events:
            assert len(event.participants) == 1
            assert event.participants[0].role == "subject"

        # Each event has a date and place
        for event in empty_project.events:
            assert event.date is not None
            assert event.place is not None
            assert event.place.place_id is not None

    def test_initial_import_creates_place_hierarchy(
        self, empty_project: ProjectData, translation_dir: Path, fixtures_dir: Path
    ) -> None:
        """Initial import creates places with correct parent-child hierarchy."""
        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(fixtures_dir / "Test-1.ged")

        # 6 places: 3 parishes + 3 counties
        assert len(empty_project.places) == 6

        parishes = [p for p in empty_project.places if p.type == "parish"]
        counties = [p for p in empty_project.places if p.type == "county"]
        assert len(parishes) == 3
        assert len(counties) == 3

        # Each parish has a county as parent
        for parish in parishes:
            assert parish.parent_place_id is not None
            parent = next(
                (p for p in empty_project.places if p.id == parish.parent_place_id),
                None,
            )
            assert parent is not None
            assert parent.type == "county"

    @given(
        title=st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=1,
            max_size=50,
        )
    )
    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_initial_import_stable_across_project_titles(
        self, title: str, fixtures_dir: Path, tmp_path: Path
    ) -> None:
        """For any project title, initial import of Test-1.ged produces same entity counts.

        Property: entity counts are independent of project metadata.
        """
        project = ProjectData(project=ProjectMetadata(title=title))
        td = tmp_path / f"trans_{hash(title)}"
        td.mkdir(exist_ok=True)
        importer = GEDCOMImporter(project, td)
        result = importer.import_file(fixtures_dir / "Test-1.ged")

        assert result.persons_added == 3
        assert result.events_added == 3
        assert result.families_added == 1
        assert result.places_added == 6


# ---------------------------------------------------------------------------
# Property: Multi-word PLAC values resolve correctly (Req 3.3)
# ---------------------------------------------------------------------------


class TestPreservationMultiWordPlaces:
    """**Validates: Requirements 3.3**

    For any multi-word PLAC value, place is normalized and stored correctly.

    Observed on UNFIXED code:
    - "Falun, Kopparbergs län" → parish "Falun" with parent county "Kopparbergs län"
    - "Enköping, Uppsala län, Sverige" → parish "Enköping" → county "Uppsala län" → country "Sverige"
    - Two-level places create parish + county
    - Three-level places create parish + county + country
    """

    def test_two_level_place_creates_parish_and_county(
        self, empty_project: ProjectData, translation_dir: Path, fixtures_dir: Path
    ) -> None:
        """Two-level PLAC like 'Falun, Kopparbergs län' creates parish under county."""
        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(fixtures_dir / "Test-1.ged")

        # Find "Falun" place
        falun = next(
            (p for p in empty_project.places if p.name == "Falun"), None
        )
        assert falun is not None
        assert falun.type == "parish"
        assert falun.parent_place_id is not None

        # Parent must be "Kopparbergs län"
        parent = next(
            (p for p in empty_project.places if p.id == falun.parent_place_id),
            None,
        )
        assert parent is not None
        assert parent.name == "Kopparbergs län"
        assert parent.type == "county"

    def test_three_level_place_creates_full_hierarchy(
        self, empty_project: ProjectData, translation_dir: Path, fixtures_dir: Path
    ) -> None:
        """Three-level PLAC like 'Enköping, Uppsala län, Sverige' creates full hierarchy."""
        # Test-2 has "Enköping, Uppsala län, Sverige" on the MARR event
        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(fixtures_dir / "Test-2.ged")

        # Find "Enköping" place
        enkoping = next(
            (p for p in empty_project.places if p.name == "Enköping"), None
        )
        assert enkoping is not None
        assert enkoping.type == "parish"
        assert enkoping.parent_place_id is not None

        # Parent is "Uppsala län" (county)
        parent = next(
            (p for p in empty_project.places if p.id == enkoping.parent_place_id),
            None,
        )
        assert parent is not None
        assert parent.name == "Uppsala län"
        assert parent.type == "county"
        assert parent.parent_place_id is not None

        # Grandparent is "Sverige" (country)
        grandparent = next(
            (p for p in empty_project.places if p.id == parent.parent_place_id),
            None,
        )
        assert grandparent is not None
        assert grandparent.name == "Sverige"
        assert grandparent.type == "country"

    @given(
        place_parts=st.lists(
            st.text(
                alphabet=st.characters(categories=("L",)),
                min_size=2,
                max_size=15,
            ),
            min_size=2,
            max_size=3,
        )
    )
    @settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_multi_word_place_always_has_place_ref(
        self, place_parts: list[str], tmp_path: Path
    ) -> None:
        """For any multi-word PLAC value, the event gets a non-None place reference.

        Property: multi-word PLAC values always resolve to a place_id.
        """
        place_string = ", ".join(place_parts)
        gedcom = (
            "0 HEAD\n1 SOUR Test\n1 CHAR UTF-8\n"
            "0 @I1@ INDI\n1 NAME Test /Person/\n1 SEX M\n"
            f"1 BIRT\n2 DATE 1 JAN 2000\n2 PLAC {place_string}\n"
            "0 TRLR\n"
        )
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(gedcom, encoding="utf-8")

        project = ProjectData(project=ProjectMetadata(title="Test"))
        td = tmp_path / "translation"
        td.mkdir(exist_ok=True)
        importer = GEDCOMImporter(project, td)
        importer.import_file(gedcom_file)

        # The birth event must have a non-None place reference
        assert len(project.events) == 1
        birth_event = project.events[0]
        assert birth_event.place is not None, (
            f"Multi-word PLAC '{place_string}' should resolve to a place, "
            f"but place reference is None"
        )
        assert birth_event.place.place_id is not None


# ---------------------------------------------------------------------------
# Property: Unchanged events remain unmodified during update import (Req 3.4)
# ---------------------------------------------------------------------------


class TestPreservationUnchangedEvents:
    """**Validates: Requirements 3.4**

    For any update import with unchanged events, those events remain unmodified.

    Observed on UNFIXED code:
    - After Test-2 update import, events from Test-1 (event_1, event_2, event_3)
      still exist with identical type, date, place, and participants
    - The original event objects are not mutated
    - Note: Bug 2 creates ADDITIONAL duplicate events, but originals are untouched
    """

    def test_original_events_unchanged_after_update(
        self, empty_project: ProjectData, translation_dir: Path, fixtures_dir: Path
    ) -> None:
        """Original events from Test-1 are unchanged after Test-2 update import."""
        # Initial import
        importer1 = GEDCOMImporter(empty_project, translation_dir)
        importer1.import_file(fixtures_dir / "Test-1.ged")

        # Snapshot initial events
        initial_event_data = []
        for e in empty_project.events:
            initial_event_data.append({
                "id": e.id,
                "type": e.type,
                "participants": [(p.person_id, p.role) for p in e.participants],
                "date_value": e.date.value if e.date else None,
                "place_id": e.place.place_id if e.place else None,
            })

        assert len(initial_event_data) == 3

        # Update import
        importer2 = GEDCOMImporter(empty_project, translation_dir)
        importer2.import_file(fixtures_dir / "Test-2.ged")

        # Verify each original event is still present and unchanged
        for snapshot in initial_event_data:
            event = next(
                (e for e in empty_project.events if e.id == snapshot["id"]),
                None,
            )
            assert event is not None, (
                f"Original event {snapshot['id']} was removed during update"
            )
            assert event.type == snapshot["type"]
            actual_participants = [
                (p.person_id, p.role) for p in event.participants
            ]
            assert actual_participants == snapshot["participants"]
            actual_date = event.date.value if event.date else None
            assert actual_date == snapshot["date_value"]
            actual_place = event.place.place_id if event.place else None
            assert actual_place == snapshot["place_id"]

    def test_original_places_unchanged_after_update(
        self, empty_project: ProjectData, translation_dir: Path, fixtures_dir: Path
    ) -> None:
        """Original places from Test-1 are unchanged after Test-2 update import."""
        # Initial import
        importer1 = GEDCOMImporter(empty_project, translation_dir)
        importer1.import_file(fixtures_dir / "Test-1.ged")

        # Snapshot initial places
        initial_place_data = []
        for p in empty_project.places:
            initial_place_data.append({
                "id": p.id,
                "name": p.name,
                "type": p.type,
                "parent_place_id": p.parent_place_id,
            })

        assert len(initial_place_data) == 6

        # Update import
        importer2 = GEDCOMImporter(empty_project, translation_dir)
        importer2.import_file(fixtures_dir / "Test-2.ged")

        # Verify each original place is still present and unchanged
        for snapshot in initial_place_data:
            place = next(
                (p for p in empty_project.places if p.id == snapshot["id"]),
                None,
            )
            assert place is not None, (
                f"Original place {snapshot['id']} was removed during update"
            )
            assert place.name == snapshot["name"]
            assert place.type == snapshot["type"]
            assert place.parent_place_id == snapshot["parent_place_id"]


# ---------------------------------------------------------------------------
# Property: New persons in update import get events correctly (Req 3.2)
# ---------------------------------------------------------------------------


class TestPreservationNewPersonsOnUpdate:
    """**Validates: Requirements 3.2**

    For any update import adding entirely new persons with valid records,
    persons and events are created correctly.

    Observed on UNFIXED code:
    - Test-2 adds Sune Persson (@I4@) with birth event (1952-03-04, Gävle)
    - Sune gets exactly 1 birth event with correct date and place
    - Sune has title "Major"
    - Family F2 is created with Sune as husband, Anders as child
    """

    def test_new_person_created_with_correct_data(
        self, empty_project: ProjectData, translation_dir: Path, fixtures_dir: Path
    ) -> None:
        """Sune is created correctly when Test-2 is imported after Test-1."""
        # Base import
        importer1 = GEDCOMImporter(empty_project, translation_dir)
        importer1.import_file(fixtures_dir / "Test-1.ged")

        # Update import
        importer2 = GEDCOMImporter(empty_project, translation_dir)
        result2 = importer2.import_file(fixtures_dir / "Test-2.ged")

        assert result2.persons_added >= 1

        # Find Sune
        sune = next(
            (p for p in empty_project.persons
             if any(n.given == "Sune" and n.surname == "Persson" for n in p.names)),
            None,
        )
        assert sune is not None, "Sune Persson should be created"
        assert sune.sex == "M"
        assert sune.title == "Major"

    def test_new_person_gets_birth_event(
        self, empty_project: ProjectData, translation_dir: Path, fixtures_dir: Path
    ) -> None:
        """Sune gets a birth event with correct date and place."""
        # Base + update import
        importer1 = GEDCOMImporter(empty_project, translation_dir)
        importer1.import_file(fixtures_dir / "Test-1.ged")
        importer2 = GEDCOMImporter(empty_project, translation_dir)
        importer2.import_file(fixtures_dir / "Test-2.ged")

        # Find Sune's person_id
        sune = next(
            p for p in empty_project.persons
            if any(n.given == "Sune" for n in p.names)
        )

        # Find Sune's birth event
        sune_births = [
            e for e in empty_project.events
            if e.type == "birth"
            and any(p.person_id == sune.id for p in e.participants)
        ]
        assert len(sune_births) >= 1, "Sune should have at least 1 birth event"

        birth = sune_births[0]
        assert birth.date is not None
        assert birth.date.value == "1952-03-04"
        assert birth.place is not None
        assert birth.place.place_id is not None

        # Place should resolve to "Gävle"
        place = next(
            (p for p in empty_project.places if p.id == birth.place.place_id),
            None,
        )
        assert place is not None
        assert place.name == "Gävle"

    def test_new_family_created_on_update(
        self, empty_project: ProjectData, translation_dir: Path, fixtures_dir: Path
    ) -> None:
        """Family F2 is created with Sune as husband during update."""
        # Base + update import
        importer1 = GEDCOMImporter(empty_project, translation_dir)
        importer1.import_file(fixtures_dir / "Test-1.ged")
        importer2 = GEDCOMImporter(empty_project, translation_dir)
        result2 = importer2.import_file(fixtures_dir / "Test-2.ged")

        assert result2.families_added >= 1
        assert len(empty_project.families) == 2

        # Find Sune
        sune = next(
            p for p in empty_project.persons
            if any(n.given == "Sune" for n in p.names)
        )

        # Find family with Sune as partner
        sune_family = next(
            (f for f in empty_project.families
             if any(p.person_id == sune.id for p in f.partners)),
            None,
        )
        assert sune_family is not None, "Family with Sune should exist"
        assert any(
            p.role == "husband" and p.person_id == sune.id
            for p in sune_family.partners
        )

    def test_marriage_event_added_to_existing_family(
        self, empty_project: ProjectData, translation_dir: Path, fixtures_dir: Path
    ) -> None:
        """Marriage event on F1 is created during Test-2 update import."""
        # Base + update import
        importer1 = GEDCOMImporter(empty_project, translation_dir)
        importer1.import_file(fixtures_dir / "Test-1.ged")
        importer2 = GEDCOMImporter(empty_project, translation_dir)
        importer2.import_file(fixtures_dir / "Test-2.ged")

        # Find marriage events
        marriage_events = [
            e for e in empty_project.events if e.type == "marriage"
        ]
        assert len(marriage_events) >= 1, "Marriage event should be created"

        marriage = marriage_events[0]
        assert marriage.date is not None
        assert marriage.date.value == "1998-06-23"
        assert marriage.place is not None

        # Place should be "Enköping"
        place = next(
            (p for p in empty_project.places if p.id == marriage.place.place_id),
            None,
        )
        assert place is not None
        assert place.name == "Enköping"

    @given(
        person_name=st.text(
            alphabet=st.characters(categories=("L",)),
            min_size=2,
            max_size=15,
        )
    )
    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_new_person_in_update_always_gets_events_attached(
        self, person_name: str, tmp_path: Path
    ) -> None:
        """For any new person added during update, birth events are attached correctly.

        Property: new persons added during update import always have their
        events attached to the correct person_id.
        """
        # Base GEDCOM with one person
        base_gedcom = (
            "0 HEAD\n1 SOUR Test\n1 CHAR UTF-8\n"
            "0 @I1@ INDI\n1 NAME Base /Person/\n1 SEX M\n"
            "1 BIRT\n2 DATE 1 JAN 1970\n2 PLAC Stockholm, Stockholms län\n"
            "0 TRLR\n"
        )
        base_file = tmp_path / "base.ged"
        base_file.write_text(base_gedcom, encoding="utf-8")

        # Update GEDCOM adds same person + new person
        update_gedcom = (
            "0 HEAD\n1 SOUR Test\n1 CHAR UTF-8\n"
            "0 @I1@ INDI\n1 NAME Base /Person/\n1 SEX M\n"
            "1 BIRT\n2 DATE 1 JAN 1970\n2 PLAC Stockholm, Stockholms län\n"
            f"0 @I2@ INDI\n1 NAME {person_name} /Testsson/\n1 SEX M\n"
            "1 BIRT\n2 DATE 5 MAR 1990\n2 PLAC Malmö, Skåne län\n"
            "0 TRLR\n"
        )
        update_file = tmp_path / "update.ged"
        update_file.write_text(update_gedcom, encoding="utf-8")

        project = ProjectData(project=ProjectMetadata(title="Test"))
        td = tmp_path / "translation"
        td.mkdir(exist_ok=True)

        # Base import
        importer1 = GEDCOMImporter(project, td)
        importer1.import_file(base_file)

        # Update import
        importer2 = GEDCOMImporter(project, td)
        importer2.import_file(update_file)

        # Find the new person
        new_person = next(
            (p for p in project.persons
             if any(n.given == person_name for n in p.names)),
            None,
        )
        assert new_person is not None, f"Person '{person_name}' should be created"

        # New person's birth event should have correct participant
        new_births = [
            e for e in project.events
            if e.type == "birth"
            and any(p.person_id == new_person.id for p in e.participants)
        ]
        assert len(new_births) >= 1, (
            f"New person '{person_name}' should have a birth event"
        )
        # The participant on the birth event must be the new person
        for birth in new_births:
            assert any(
                p.person_id == new_person.id for p in birth.participants
            )


# ---------------------------------------------------------------------------
# Property: Clean GEDCOM import produces no spurious warnings (Req 3.5)
# ---------------------------------------------------------------------------


class TestPreservationNoSpuriousWarnings:
    """**Validates: Requirements 3.5**

    For any clean GEDCOM import, report contains no spurious warnings.

    Observed on UNFIXED code:
    - GEDCOMImporter.import_file() with well-formed GEDCOM data returns
      result.warnings == [] (empty list)
    - Only validation warnings from ImportService.run() show English text
      (Bug 1), but the importer itself doesn't generate spurious warnings
    """

    def test_clean_initial_import_no_warnings(
        self, empty_project: ProjectData, translation_dir: Path, fixtures_dir: Path
    ) -> None:
        """Clean initial import of Test-1.ged produces no warnings."""
        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(fixtures_dir / "Test-1.ged")

        assert result.warnings == [], (
            f"Clean import should produce no warnings, got: {result.warnings}"
        )

    def test_clean_update_import_no_warnings(
        self, empty_project: ProjectData, translation_dir: Path, fixtures_dir: Path
    ) -> None:
        """Clean update import of Test-2.ged (after Test-1) produces no warnings."""
        # Base import
        importer1 = GEDCOMImporter(empty_project, translation_dir)
        importer1.import_file(fixtures_dir / "Test-1.ged")

        # Update import
        importer2 = GEDCOMImporter(empty_project, translation_dir)
        result2 = importer2.import_file(fixtures_dir / "Test-2.ged")

        assert result2.warnings == [], (
            f"Clean update import should produce no warnings, got: {result2.warnings}"
        )

    @given(
        place_parts=st.lists(
            st.text(
                alphabet=st.characters(categories=("L",)),
                min_size=2,
                max_size=15,
            ),
            min_size=2,
            max_size=3,
        ),
        person_given=st.text(
            alphabet=st.characters(categories=("L",)),
            min_size=2,
            max_size=15,
        ),
        person_surname=st.text(
            alphabet=st.characters(categories=("L",)),
            min_size=2,
            max_size=15,
        ),
    )
    @settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_well_formed_gedcom_produces_no_warnings(
        self,
        place_parts: list[str],
        person_given: str,
        person_surname: str,
        tmp_path: Path,
    ) -> None:
        """For any well-formed GEDCOM with multi-word places, no warnings are generated.

        Property: clean GEDCOM data (valid tags, multi-word places) never
        produces spurious warnings from the importer.
        """
        place_string = ", ".join(place_parts)
        gedcom = (
            "0 HEAD\n1 SOUR Test\n1 CHAR UTF-8\n"
            f"0 @I1@ INDI\n1 NAME {person_given} /{person_surname}/\n1 SEX M\n"
            f"1 BIRT\n2 DATE 1 JAN 2000\n2 PLAC {place_string}\n"
            "0 TRLR\n"
        )
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(gedcom, encoding="utf-8")

        project = ProjectData(project=ProjectMetadata(title="Test"))
        td = tmp_path / "translation"
        td.mkdir(exist_ok=True)
        importer = GEDCOMImporter(project, td)
        result = importer.import_file(gedcom_file)

        assert result.warnings == [], (
            f"Well-formed GEDCOM should produce no warnings, got: {result.warnings}"
        )
