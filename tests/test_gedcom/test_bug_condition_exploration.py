"""Bug condition exploration tests for GEDCOM update import fixes.

These tests MUST FAIL on unfixed code — failure confirms the bugs exist.
Each test explores one of the 5 bugs identified in the bugfix spec:

1. Mixed English/Swedish text in completion dialog
2. Duplicate events created instead of updating existing ones
3. Events attached to wrong persons (event-to-person mapping leaks between INDI records)
4. Single-word PLAC values silently dropped
5. Insufficient detail in import report (warnings lack structured information)

DO NOT modify these tests to make them pass. Failures are the expected outcome
on unfixed code. These same tests will validate the fixes once implemented.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from slaktbusken.gedcom.importer import GEDCOMImporter, ImportResult
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.import_service import ImportService
from slaktbusken.services.report_service import ReportService
from slaktbusken.services.validation_service import ValidationService


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
# Test 1a: Swedish-only validation warnings (Bug 1)
# ---------------------------------------------------------------------------


class TestBug1SwedishOnlyValidationWarnings:
    """Bug 1: Validation warnings must not contain English place type names.

    When a GEDCOM import triggers place hierarchy validation warnings,
    the messages shown in the import dialog must use Swedish place type
    names (län, land, församling, etc.) instead of English identifiers
    (county, country, parish, etc.).

    Bug Condition: validationWarningContainsEnglishPlaceType(warning)
    Expected Behavior: all_text_is_swedish(validation_warnings)
    """

    # English place type identifiers that should NOT appear in user-facing messages
    ENGLISH_PLACE_TYPES = [
        "county",
        "country",
        "parish",
        "church",
        "cemetery",
        "village",
        "farm",
        "school",
    ]

    def test_validation_warnings_use_swedish_place_types(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Validation warnings for place hierarchy must use Swedish type names.

        Imports a GEDCOM with a two-level place (e.g., "Falun, Kopparbergs län")
        which creates a county without a country parent. The validation warning
        must say "län" and "land" — not "county" and "country".

        This WILL FAIL because _validate_place_hierarchy in validators.py
        uses place.type and expected_parent_type (English identifiers) directly
        in Swedish error messages.
        """
        # Import Test-1.ged which has two-level places like
        # "Falun, Kopparbergs län" — county without country parent
        gedcom_content = """\
0 HEAD
1 SOUR Test
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Anders /Persson/
1 SEX M
1 BIRT
2 DATE 15 JAN 1975
2 PLAC Falun, Kopparbergs län
0 TRLR
"""
        gedcom_file = tmp_path / "test_place_validation.ged"
        gedcom_file.write_text(gedcom_content, encoding="utf-8")

        # Use ImportService.run() which triggers validation after import
        import_service = ImportService(
            validation_service=ValidationService(),
            report_service=ReportService(),
        )

        project_path = tmp_path / "project"
        project_path.mkdir()
        translation_subdir = project_path / "translation"
        translation_subdir.mkdir()

        result = import_service.run(
            empty_project, gedcom_file, project_path
        )

        # We expect validation warnings because county has no country parent
        validation_warnings = [
            w for w in result.warnings
            if "Valideringsvarning" in w
        ]
        assert len(validation_warnings) > 0, (
            "Expected validation warnings for county without country parent"
        )

        # The warnings must NOT contain English place type identifiers
        for warning in validation_warnings:
            for eng_type in self.ENGLISH_PLACE_TYPES:
                # Check for English type used as a word (not part of another word)
                # Use word boundary check: space/quote before/after
                if f" {eng_type}" in warning.lower() or f"'{eng_type}'" in warning.lower():
                    assert False, (
                        f"English place type '{eng_type}' found in validation "
                        f"warning: {warning!r}\n"
                        f"Expected Swedish equivalent (e.g., 'län' for 'county', "
                        f"'land' for 'country')"
                    )


# ---------------------------------------------------------------------------
# Test 1b: Event deduplication (Bug 2)
# ---------------------------------------------------------------------------


class TestBug2EventDeduplication:
    """Bug 2: Reimporting the same GEDCOM should NOT create duplicate events.

    When a GEDCOM file is imported as update into a project that already
    contains events for a person, the system must detect existing events
    and not create duplicates.

    Bug Condition: existingPersonHasMatchingEvents AND duplicatesCreated
    Expected Behavior: count_events_for_person(person_id) == expected_count
    """

    def test_reimport_does_not_duplicate_events(
        self,
        empty_project: ProjectData,
        translation_dir: Path,
        fixtures_dir: Path,
    ) -> None:
        """Reimporting Test-1.ged should not increase event count per person.

        1. Import Test-1.ged as initial import (creates persons with events)
        2. Record event counts per person
        3. Reimport the same file (update)
        4. Assert event count for each person has NOT increased

        This WILL FAIL because _update_person calls _create_person_events
        without deduplication (comment in code: "For simplicity, we add
        new events").
        """
        gedcom_file = fixtures_dir / "Test-1.ged"
        assert gedcom_file.exists(), f"Fixture not found: {gedcom_file}"

        # First import — creates persons and events
        importer1 = GEDCOMImporter(empty_project, translation_dir)
        result1 = importer1.import_file(gedcom_file)
        assert result1.persons_added == 3, "Expected 3 persons from Test-1.ged"

        # Record event counts per person after first import
        events_per_person_before: dict[str, int] = {}
        for event in empty_project.events:
            for participant in event.participants:
                pid = participant.person_id
                events_per_person_before[pid] = (
                    events_per_person_before.get(pid, 0) + 1
                )

        # Verify we have some events to track
        assert len(events_per_person_before) > 0, "Should have events after import"

        # Second import (reimport/update) — should update, not duplicate
        importer2 = GEDCOMImporter(empty_project, translation_dir)
        result2 = importer2.import_file(gedcom_file)

        # Record event counts after reimport
        events_per_person_after: dict[str, int] = {}
        for event in empty_project.events:
            for participant in event.participants:
                pid = participant.person_id
                events_per_person_after[pid] = (
                    events_per_person_after.get(pid, 0) + 1
                )

        # Assert: event count per person should NOT have increased
        for person_id, count_before in events_per_person_before.items():
            count_after = events_per_person_after.get(person_id, 0)
            assert count_after == count_before, (
                f"Person {person_id}: event count increased from "
                f"{count_before} to {count_after} (duplicates created)"
            )


# ---------------------------------------------------------------------------
# Test 1c: Event isolation between INDI records (Bug 3)
# ---------------------------------------------------------------------------


class TestBug3EventIsolation:
    """Bug 3: Events must belong ONLY to the person from their INDI record.

    When new persons are added during update import, each person's events
    must only be attached to that person — no event-to-person mapping
    leakage between INDI records.

    Bug Condition: newPersonReceivedEventsFromOtherINDI(person, events)
    Expected Behavior: all events for person_id have participant.person_id == person_id
    """

    def test_events_isolated_between_persons_on_update(
        self,
        empty_project: ProjectData,
        translation_dir: Path,
        fixtures_dir: Path,
    ) -> None:
        """Events from Test-2.ged update must not leak between INDI records.

        1. Import Test-1.ged as base (3 persons: Stina, Anders, Bettan)
        2. Import Test-2.ged as update (adds Sune @I4@ with birth event)
        3. For EACH person, assert all their events have the correct
           participant.person_id — no events from other persons

        This WILL FAIL if event state leaks between INDI records during
        the update import.
        """
        test1_file = fixtures_dir / "Test-1.ged"
        test2_file = fixtures_dir / "Test-2.ged"
        assert test1_file.exists(), f"Fixture not found: {test1_file}"
        assert test2_file.exists(), f"Fixture not found: {test2_file}"

        # Base import
        importer1 = GEDCOMImporter(empty_project, translation_dir)
        result1 = importer1.import_file(test1_file)
        assert result1.persons_added == 3

        # Update import — adds Sune and marriage event on F1
        importer2 = GEDCOMImporter(empty_project, translation_dir)
        result2 = importer2.import_file(test2_file)

        # Verify Sune was added
        assert result2.persons_added >= 1, "Expected at least 1 new person (Sune)"

        # Build a mapping of person_id → person names for diagnostics
        person_names: dict[str, str] = {}
        for person in empty_project.persons:
            if person.names:
                name = person.names[0]
                person_names[person.id] = f"{name.given} {name.surname}"

        # For each person, verify ALL their individual events have correct
        # participant mapping (participant.person_id matches expected person)
        person_ids = {p.id for p in empty_project.persons}

        for person_id in person_ids:
            # Get all events where this person is a participant
            person_events = [
                event
                for event in empty_project.events
                if any(p.person_id == person_id for p in event.participants)
            ]

            for event in person_events:
                # For individual events (one participant), the participant
                # must be the expected person
                if len(event.participants) == 1:
                    participant = event.participants[0]
                    assert participant.person_id == person_id, (
                        f"Event {event.id} (type={event.type}) has "
                        f"participant {participant.person_id} "
                        f"({person_names.get(participant.person_id, '?')}) "
                        f"but is associated with person {person_id} "
                        f"({person_names.get(person_id, '?')}) — "
                        f"event leaked between INDI records!"
                    )


# ---------------------------------------------------------------------------
# Test 1d: Single-word PLAC value preservation (Bug 4)
# ---------------------------------------------------------------------------


class TestBug4SingleWordPlacePreservation:
    """Bug 4: Single-word PLAC values must be preserved, not silently dropped.

    When a GEDCOM event has a PLAC value with only one word (e.g. "Falun"),
    the system must preserve the place on the event, not return None.

    Bug Condition: input.placValue IS single_word AND placeDropped(event)
    Expected Behavior: event.place IS NOT None
    """

    def test_single_word_place_preserved_on_event(
        self,
        empty_project: ProjectData,
        translation_dir: Path,
        tmp_path: Path,
    ) -> None:
        """A GEDCOM event with '2 PLAC Falun' must preserve the place reference.

        When a place already exists with the same name under a parent hierarchy
        (e.g. "Falun" created from "Falun, Kopparbergs län"), a subsequent
        import with just "Falun" (single word, no parent) must still preserve
        the place on the event.

        This WILL FAIL because _resolve_place → map_place returns None when
        map_place_to_hierarchy finds an existing match via fallback (name+type
        without parent) but then TranslationManager.map_place's second
        find_matching_place call returns None (no translation mapping for the
        single-word variant), resulting in place_ref = None.
        """
        # Step 1: First import establishes "Falun" as a place with a parent
        gedcom_base = """\
0 HEAD
1 SOUR Test
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Anders /Persson/
1 SEX M
1 BIRT
2 DATE 15 JAN 1975
2 PLAC Falun, Kopparbergs län
0 TRLR
"""
        base_file = tmp_path / "base.ged"
        base_file.write_text(gedcom_base, encoding="utf-8")

        importer1 = GEDCOMImporter(empty_project, translation_dir)
        result1 = importer1.import_file(base_file)
        assert result1.persons_added == 1
        assert result1.places_added >= 1, "Expected places from multi-word PLAC"

        # Verify Falun exists as a place with a parent
        falun_places = [p for p in empty_project.places if p.name == "Falun"]
        assert len(falun_places) == 1, "Expected 'Falun' place to exist"
        assert falun_places[0].parent_place_id is not None, (
            "Expected 'Falun' to have a parent place (Kopparbergs län)"
        )

        # Step 2: Second import with single-word "Falun" — different person
        gedcom_update = """\
0 HEAD
1 SOUR Test
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Anders /Persson/
1 SEX M
1 BIRT
2 DATE 15 JAN 1975
2 PLAC Falun, Kopparbergs län
0 @I2@ INDI
1 NAME Sune /Testsson/
1 SEX M
1 BIRT
2 DATE 1 JAN 1950
2 PLAC Falun
0 TRLR
"""
        update_file = tmp_path / "update.ged"
        update_file.write_text(gedcom_update, encoding="utf-8")

        importer2 = GEDCOMImporter(empty_project, translation_dir)
        result2 = importer2.import_file(update_file)

        # Find the birth event for Sune (the new person with single-word place)
        # Sune's person_id will be the newly added one
        sune_persons = [
            p for p in empty_project.persons
            if any(n.given == "Sune" for n in p.names)
        ]
        assert len(sune_persons) >= 1, "Expected Sune to be imported"
        sune_id = sune_persons[0].id

        # Find Sune's birth event
        sune_birth_events = [
            e for e in empty_project.events
            if e.type == "birth"
            and any(p.person_id == sune_id for p in e.participants)
        ]
        assert len(sune_birth_events) >= 1, "Expected birth event for Sune"

        birth_event = sune_birth_events[0]

        # The place MUST be preserved — not None/dropped
        assert birth_event.place is not None, (
            f"Birth event place is None! Single-word PLAC 'Falun' was "
            f"silently dropped when a place named 'Falun' already existed "
            f"under a parent hierarchy. Event: {birth_event}"
        )


# ---------------------------------------------------------------------------
# Test 1e: Structured import warnings (Bug 5)
# ---------------------------------------------------------------------------


class TestBug5StructuredWarnings:
    """Bug 5: Import warnings must include structured detail.

    Each warning in result.warnings must include: xref (@I..@), person name,
    event type, raw value, and reason — not just free-text strings.

    Bug Condition: warnings.any(w => w.lacksStructuredDetail())
    Expected Behavior: warning includes xref, person_name, event_type, raw_value, reason
    """

    def test_warnings_contain_structured_information(
        self,
        empty_project: ProjectData,
        translation_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Warnings from import must include xref, person name, event type, and reason.

        Trigger a warning condition by importing a person that generates
        a warning (e.g., unsupported tag, malformed data), then assert
        the warning contains structured fields.

        This WILL FAIL because current warnings are free-text strings like
        "Rad 142: Kunde inte importera person (xref=@I10@): ..." which
        lacks person name, event type, raw value, and detailed reason.
        """
        # GEDCOM that triggers warnings — person with unsupported tags
        # and intentionally problematic data
        gedcom_content = """\
0 HEAD
1 SOUR Test
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Anna /Karlsson/
1 SEX F
1 BIRT
2 DATE 5 MAY 1900
2 PLAC Stockholm, Stockholms län, Sverige
0 _CUSTOM This is custom data that triggers a warning
0 OBJE Multimedia record that triggers a warning
0 TRLR
"""
        gedcom_file = tmp_path / "warning_test.ged"
        gedcom_file.write_text(gedcom_content, encoding="utf-8")

        # Import — should generate warnings for _CUSTOM and OBJE tags
        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(gedcom_file)

        # We expect at least some warnings
        assert len(result.warnings) > 0, "Expected warnings from unsupported tags"

        # Each warning MUST contain structured information:
        # - xref (e.g., @I1@) or record identifier
        # - person/record name
        # - event type (if applicable)
        # - raw GEDCOM value that triggered the warning
        # - reason why it was flagged
        #
        # The required structured fields for a proper warning:
        required_fields_pattern = re.compile(
            r"@[A-Z]\d+@"  # xref like @I1@, @F1@, etc.
        )

        for warning in result.warnings:
            # Each warning must have a xref reference
            has_xref = bool(required_fields_pattern.search(warning))

            # Each warning must have a person/record name
            # (not just a line number and generic message)
            has_name = any(
                name in warning
                for name in ["Anna", "Karlsson", "Anna Karlsson"]
            )

            # Each warning must mention the raw GEDCOM value/tag
            has_raw_value = any(
                raw in warning
                for raw in ["_CUSTOM", "OBJE", "Custom data", "Multimedia"]
            )

            # Each warning must have a clear reason
            has_reason = any(
                reason in warning.lower()
                for reason in ["ej stödd", "stöds inte", "ignorerade", "okänd"]
            )

            # Assert ALL structured fields are present in each warning
            assert has_xref, (
                f"Warning lacks xref: {warning!r}\n"
                f"Warnings must include record xref (e.g., @I1@)"
            )
            assert has_name, (
                f"Warning lacks person/record name: {warning!r}\n"
                f"Warnings must include the person or record name"
            )
