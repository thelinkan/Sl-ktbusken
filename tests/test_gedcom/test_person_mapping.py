"""Unit tests for slaktbusken.gedcom.translation.person_mapping module."""

from __future__ import annotations

import pytest

from slaktbusken.gedcom.translation.models import (
    DiffCategory,
    GedcomFamily,
    GedcomPerson,
    ImportDiffReport,
    PersonDiffEntry,
    PersonFingerprint,
)
from slaktbusken.gedcom.translation.person_mapping import (
    classify_persons,
    compute_composite_key_hash,
    compute_fingerprint,
    compute_record_hash,
    compute_relationship_hash,
    generate_diff_report,
)
from slaktbusken.persistence.translation_io import PersonMapping


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_person(
    xref_id: str = "@I1@",
    given_name: str = "Erik",
    surname: str = "Svensson",
    sex: str = "M",
    birth_date: str | None = "1 JAN 1800",
    birth_place: str | None = "Ljusdal",
    death_date: str | None = None,
    death_place: str | None = None,
    **kwargs,
) -> GedcomPerson:
    """Create a GedcomPerson with sensible defaults for testing."""
    return GedcomPerson(
        xref_id=xref_id,
        given_name=given_name,
        surname=surname,
        sex=sex,
        birth_date=birth_date,
        birth_place=birth_place,
        death_date=death_date,
        death_place=death_place,
        **kwargs,
    )


def _make_family(
    xref_id: str = "@F1@",
    husb_xref: str | None = None,
    wife_xref: str | None = None,
    child_xrefs: list[str] | None = None,
) -> GedcomFamily:
    """Create a GedcomFamily with sensible defaults for testing."""
    return GedcomFamily(
        xref_id=xref_id,
        husb_xref=husb_xref,
        wife_xref=wife_xref,
        child_xrefs=child_xrefs or [],
    )


# ---------------------------------------------------------------------------
# Tests: compute_composite_key_hash
# ---------------------------------------------------------------------------


class TestComputeCompositeKeyHash:
    """Tests for the composite key hash function."""

    def test_deterministic_same_inputs_same_hash(self) -> None:
        hash1 = compute_composite_key_hash("Erik", "Svensson", "1800", "Ljusdal")
        hash2 = compute_composite_key_hash("Erik", "Svensson", "1800", "Ljusdal")
        assert hash1 == hash2

    def test_case_insensitive(self) -> None:
        hash_lower = compute_composite_key_hash("erik", "svensson", "1800", "ljusdal")
        hash_upper = compute_composite_key_hash("ERIK", "SVENSSON", "1800", "LJUSDAL")
        hash_mixed = compute_composite_key_hash("Erik", "Svensson", "1800", "Ljusdal")
        assert hash_lower == hash_upper == hash_mixed

    def test_different_names_produce_different_hashes(self) -> None:
        hash1 = compute_composite_key_hash("Erik", "Svensson", "1800", "Ljusdal")
        hash2 = compute_composite_key_hash("Anna", "Persson", "1800", "Ljusdal")
        assert hash1 != hash2

    def test_same_name_different_birth_date_different_hash(self) -> None:
        hash1 = compute_composite_key_hash("Erik", "Svensson", "1800", "Ljusdal")
        hash2 = compute_composite_key_hash("Erik", "Svensson", "1850", "Ljusdal")
        assert hash1 != hash2

    def test_same_name_different_birth_place_different_hash(self) -> None:
        hash1 = compute_composite_key_hash("Erik", "Svensson", "1800", "Ljusdal")
        hash2 = compute_composite_key_hash("Erik", "Svensson", "1800", "Stockholm")
        assert hash1 != hash2

    def test_none_birth_date_handled(self) -> None:
        hash1 = compute_composite_key_hash("Erik", "Svensson", None, "Ljusdal")
        hash2 = compute_composite_key_hash("Erik", "Svensson", None, "Ljusdal")
        assert hash1 == hash2

    def test_none_vs_empty_string_treated_same(self) -> None:
        hash_none = compute_composite_key_hash("Erik", "Svensson", None, None)
        hash_empty = compute_composite_key_hash("Erik", "Svensson", "", "")
        assert hash_none == hash_empty

    def test_whitespace_stripped(self) -> None:
        hash1 = compute_composite_key_hash("Erik", "Svensson", "1800", "Ljusdal")
        hash2 = compute_composite_key_hash("  Erik  ", " Svensson ", " 1800 ", " Ljusdal ")
        assert hash1 == hash2


# ---------------------------------------------------------------------------
# Tests: compute_record_hash
# ---------------------------------------------------------------------------


class TestComputeRecordHash:
    """Tests for the record hash function."""

    def test_deterministic_same_input(self) -> None:
        person = _make_person()
        hash1 = compute_record_hash(person)
        hash2 = compute_record_hash(person)
        assert hash1 == hash2

    def test_changing_given_name_changes_hash(self) -> None:
        person1 = _make_person(given_name="Erik")
        person2 = _make_person(given_name="Lars")
        assert compute_record_hash(person1) != compute_record_hash(person2)

    def test_changing_surname_changes_hash(self) -> None:
        person1 = _make_person(surname="Svensson")
        person2 = _make_person(surname="Persson")
        assert compute_record_hash(person1) != compute_record_hash(person2)

    def test_changing_sex_changes_hash(self) -> None:
        person1 = _make_person(sex="M")
        person2 = _make_person(sex="F")
        assert compute_record_hash(person1) != compute_record_hash(person2)

    def test_changing_birth_date_changes_hash(self) -> None:
        person1 = _make_person(birth_date="1 JAN 1800")
        person2 = _make_person(birth_date="2 FEB 1850")
        assert compute_record_hash(person1) != compute_record_hash(person2)

    def test_changing_birth_place_changes_hash(self) -> None:
        person1 = _make_person(birth_place="Ljusdal")
        person2 = _make_person(birth_place="Stockholm")
        assert compute_record_hash(person1) != compute_record_hash(person2)

    def test_changing_death_date_changes_hash(self) -> None:
        person1 = _make_person(death_date=None)
        person2 = _make_person(death_date="1 JAN 1880")
        assert compute_record_hash(person1) != compute_record_hash(person2)

    def test_changing_death_place_changes_hash(self) -> None:
        person1 = _make_person(death_place=None)
        person2 = _make_person(death_place="Gävle")
        assert compute_record_hash(person1) != compute_record_hash(person2)

    def test_changing_title_changes_hash(self) -> None:
        person1 = _make_person(title=None)
        person2 = _make_person(title="Kyrkoherde")
        assert compute_record_hash(person1) != compute_record_hash(person2)

    def test_changing_occupation_changes_hash(self) -> None:
        person1 = _make_person(occupation=None)
        person2 = _make_person(occupation="Bonde")
        assert compute_record_hash(person1) != compute_record_hash(person2)

    def test_changing_notes_changes_hash(self) -> None:
        person1 = _make_person(notes="")
        person2 = _make_person(notes="Har en notering")
        assert compute_record_hash(person1) != compute_record_hash(person2)

    def test_additional_names_affect_hash(self) -> None:
        person1 = _make_person(additional_names=[])
        person2 = _make_person(additional_names=[("Karl", "Eriksson")])
        assert compute_record_hash(person1) != compute_record_hash(person2)

    def test_source_citations_affect_hash(self) -> None:
        person1 = _make_person(source_citations=[])
        person2 = _make_person(source_citations=["@S1@"])
        assert compute_record_hash(person1) != compute_record_hash(person2)


# ---------------------------------------------------------------------------
# Tests: compute_relationship_hash
# ---------------------------------------------------------------------------


class TestComputeRelationshipHash:
    """Tests for the relationship hash function."""

    def test_includes_partner_xrefs(self) -> None:
        family = _make_family(husb_xref="@I1@", wife_xref="@I2@", child_xrefs=["@I3@"])
        hash1 = compute_relationship_hash("@I1@", [family])
        # Change partner
        family2 = _make_family(husb_xref="@I1@", wife_xref="@I99@", child_xrefs=["@I3@"])
        hash2 = compute_relationship_hash("@I1@", [family2])
        assert hash1 != hash2

    def test_includes_child_xrefs(self) -> None:
        family1 = _make_family(husb_xref="@I1@", wife_xref="@I2@", child_xrefs=["@I3@"])
        family2 = _make_family(
            husb_xref="@I1@", wife_xref="@I2@", child_xrefs=["@I3@", "@I4@"]
        )
        hash1 = compute_relationship_hash("@I1@", [family1])
        hash2 = compute_relationship_hash("@I1@", [family2])
        assert hash1 != hash2

    def test_stable_regardless_of_child_order(self) -> None:
        family1 = _make_family(
            husb_xref="@I1@", wife_xref="@I2@", child_xrefs=["@I3@", "@I4@", "@I5@"]
        )
        family2 = _make_family(
            husb_xref="@I1@", wife_xref="@I2@", child_xrefs=["@I5@", "@I3@", "@I4@"]
        )
        hash1 = compute_relationship_hash("@I1@", [family1])
        hash2 = compute_relationship_hash("@I1@", [family2])
        assert hash1 == hash2

    def test_stable_regardless_of_family_order(self) -> None:
        fam_a = _make_family(
            xref_id="@F1@", husb_xref="@I1@", wife_xref="@I2@", child_xrefs=["@I3@"]
        )
        fam_b = _make_family(
            xref_id="@F2@", husb_xref="@I1@", wife_xref="@I4@", child_xrefs=["@I5@"]
        )
        hash1 = compute_relationship_hash("@I1@", [fam_a, fam_b])
        hash2 = compute_relationship_hash("@I1@", [fam_b, fam_a])
        assert hash1 == hash2

    def test_no_families_produces_consistent_hash(self) -> None:
        hash1 = compute_relationship_hash("@I1@", [])
        hash2 = compute_relationship_hash("@I1@", [])
        assert hash1 == hash2

    def test_person_as_child_includes_parents(self) -> None:
        family = _make_family(husb_xref="@I1@", wife_xref="@I2@", child_xrefs=["@I3@"])
        # @I3@ is a child — parents should appear in the hash
        hash_with_parents = compute_relationship_hash("@I3@", [family])
        hash_no_family = compute_relationship_hash("@I3@", [])
        assert hash_with_parents != hash_no_family


# ---------------------------------------------------------------------------
# Tests: compute_fingerprint
# ---------------------------------------------------------------------------


class TestComputeFingerprint:
    """Tests for the full fingerprint computation."""

    def test_combines_all_three_hashes(self) -> None:
        person = _make_person()
        families = [
            _make_family(husb_xref="@I1@", wife_xref="@I2@", child_xrefs=["@I3@"])
        ]
        fp = compute_fingerprint(person, families)

        expected_composite = compute_composite_key_hash(
            person.given_name, person.surname, person.birth_date, person.birth_place
        )
        expected_record = compute_record_hash(person)
        expected_relationship = compute_relationship_hash(person.xref_id, families)

        assert fp.xref_id == person.xref_id
        assert fp.composite_key_hash == expected_composite
        assert fp.record_hash == expected_record
        assert fp.relationship_hash == expected_relationship

    def test_returns_person_fingerprint_instance(self) -> None:
        person = _make_person()
        fp = compute_fingerprint(person, [])
        assert isinstance(fp, PersonFingerprint)

    def test_fingerprint_xref_id_matches_person(self) -> None:
        person = _make_person(xref_id="@I42@")
        fp = compute_fingerprint(person, [])
        assert fp.xref_id == "@I42@"


# ---------------------------------------------------------------------------
# Tests: classify_persons
# ---------------------------------------------------------------------------


class TestClassifyPersons:
    """Tests for person diff classification."""

    def test_known_mapping_same_record_hash_unchanged(self) -> None:
        person = _make_person(xref_id="@I1@")
        families: list[GedcomFamily] = []
        record_hash = compute_record_hash(person)
        mappings = [PersonMapping(gedcom_id="@I1@", app_id="person_1", fingerprint=record_hash)]

        report = classify_persons([person], families, mappings, {})
        assert len(report.entries) == 1
        assert report.entries[0].category == DiffCategory.UNCHANGED
        assert report.entries[0].app_id == "person_1"

    def test_known_mapping_different_record_hash_updated(self) -> None:
        person = _make_person(xref_id="@I1@")
        families: list[GedcomFamily] = []
        mappings = [
            PersonMapping(gedcom_id="@I1@", app_id="person_1", fingerprint="old_hash_value")
        ]

        report = classify_persons([person], families, mappings, {})
        assert len(report.entries) == 1
        assert report.entries[0].category == DiffCategory.UPDATED
        assert report.entries[0].app_id == "person_1"

    def test_no_mapping_matching_composite_key_hash_updated(self) -> None:
        person = _make_person(xref_id="@I1@")
        families: list[GedcomFamily] = []
        # Compute the composite key hash for the person
        composite_hash = compute_composite_key_hash(
            person.given_name, person.surname, person.birth_date, person.birth_place
        )
        # existing_fingerprints maps app_id → composite_key_hash
        existing_fingerprints = {"person_42": composite_hash}

        report = classify_persons([person], families, [], existing_fingerprints)
        assert len(report.entries) == 1
        assert report.entries[0].category == DiffCategory.UPDATED
        assert report.entries[0].app_id == "person_42"

    def test_no_mapping_no_matching_fingerprint_new(self) -> None:
        person = _make_person(xref_id="@I1@")
        families: list[GedcomFamily] = []

        report = classify_persons([person], families, [], {})
        assert len(report.entries) == 1
        assert report.entries[0].category == DiffCategory.NEW
        assert report.entries[0].app_id is None

    def test_existing_mapping_absent_from_incoming_missing(self) -> None:
        mappings = [PersonMapping(gedcom_id="@I99@", app_id="person_99", fingerprint=None)]

        report = classify_persons([], [], mappings, {})
        assert len(report.entries) == 1
        assert report.entries[0].category == DiffCategory.MISSING
        assert report.entries[0].app_id == "person_99"
        assert report.entries[0].gedcom_xref == "@I99@"

    def test_empty_incoming_with_existing_mappings_all_missing(self) -> None:
        mappings = [
            PersonMapping(gedcom_id="@I1@", app_id="person_1", fingerprint=None),
            PersonMapping(gedcom_id="@I2@", app_id="person_2", fingerprint=None),
            PersonMapping(gedcom_id="@I3@", app_id="person_3", fingerprint=None),
        ]

        report = classify_persons([], [], mappings, {})
        assert report.missing_count == 3
        assert all(e.category == DiffCategory.MISSING for e in report.entries)

    def test_empty_existing_mappings_with_new_persons_all_new(self) -> None:
        persons = [
            _make_person(xref_id="@I1@", given_name="Erik"),
            _make_person(xref_id="@I2@", given_name="Anna"),
        ]

        report = classify_persons(persons, [], [], {})
        assert report.new_count == 2
        assert all(e.category == DiffCategory.NEW for e in report.entries)

    def test_mixed_scenario_multiple_categories(self) -> None:
        # Person 1: known mapping, same hash → UNCHANGED
        person1 = _make_person(xref_id="@I1@", given_name="Erik")
        record_hash_1 = compute_record_hash(person1)

        # Person 2: known mapping, different hash → UPDATED
        person2 = _make_person(xref_id="@I2@", given_name="Anna")

        # Person 3: no mapping, no fingerprint match → NEW
        person3 = _make_person(xref_id="@I3@", given_name="Lars")

        families: list[GedcomFamily] = []
        mappings = [
            PersonMapping(gedcom_id="@I1@", app_id="person_1", fingerprint=record_hash_1),
            PersonMapping(gedcom_id="@I2@", app_id="person_2", fingerprint="stale_hash"),
            # @I99@ is not in incoming → MISSING
            PersonMapping(gedcom_id="@I99@", app_id="person_99", fingerprint=None),
        ]

        report = classify_persons([person1, person2, person3], families, mappings, {})

        categories = {e.gedcom_xref: e.category for e in report.entries}
        assert categories["@I1@"] == DiffCategory.UNCHANGED
        assert categories["@I2@"] == DiffCategory.UPDATED
        assert categories["@I3@"] == DiffCategory.NEW
        assert categories["@I99@"] == DiffCategory.MISSING

        assert report.unchanged_count == 1
        assert report.updated_count == 1
        assert report.new_count == 1
        assert report.missing_count == 1


# ---------------------------------------------------------------------------
# Tests: generate_diff_report
# ---------------------------------------------------------------------------


class TestGenerateDiffReport:
    """Tests for import-diff report generation."""

    def _make_entry(self, category: DiffCategory, xref: str = "@I1@") -> PersonDiffEntry:
        """Helper to create a PersonDiffEntry with minimal data."""
        return PersonDiffEntry(
            gedcom_xref=xref,
            app_id="person_1" if category != DiffCategory.NEW else None,
            category=category,
            fingerprint=PersonFingerprint(
                xref_id=xref,
                composite_key_hash="abc",
                record_hash="def",
                relationship_hash="ghi",
            ),
        )

    def test_report_counts_match_actual_entries(self) -> None:
        entries = [
            self._make_entry(DiffCategory.NEW, "@I1@"),
            self._make_entry(DiffCategory.NEW, "@I2@"),
            self._make_entry(DiffCategory.UPDATED, "@I3@"),
            self._make_entry(DiffCategory.UNCHANGED, "@I4@"),
            self._make_entry(DiffCategory.MISSING, "@I5@"),
        ]
        report = generate_diff_report(entries)
        assert report.new_count == 2
        assert report.updated_count == 1
        assert report.unchanged_count == 1
        assert report.missing_count == 1
        assert report.uncertain_count == 0

    def test_total_count_is_sum_of_all_categories(self) -> None:
        entries = [
            self._make_entry(DiffCategory.NEW, "@I1@"),
            self._make_entry(DiffCategory.UPDATED, "@I2@"),
            self._make_entry(DiffCategory.UNCHANGED, "@I3@"),
            self._make_entry(DiffCategory.MISSING, "@I4@"),
            self._make_entry(DiffCategory.UNCERTAIN, "@I5@"),
        ]
        report = generate_diff_report(entries)
        assert report.total_count == 5
        assert report.total_count == (
            report.new_count
            + report.updated_count
            + report.unchanged_count
            + report.missing_count
            + report.uncertain_count
        )

    def test_has_uncertain_true_when_uncertain_count_positive(self) -> None:
        entries = [
            self._make_entry(DiffCategory.UNCERTAIN, "@I1@"),
            self._make_entry(DiffCategory.NEW, "@I2@"),
        ]
        report = generate_diff_report(entries)
        assert report.has_uncertain is True

    def test_has_uncertain_false_when_no_uncertain(self) -> None:
        entries = [
            self._make_entry(DiffCategory.NEW, "@I1@"),
            self._make_entry(DiffCategory.UNCHANGED, "@I2@"),
        ]
        report = generate_diff_report(entries)
        assert report.has_uncertain is False

    def test_has_changes_true_when_new_present(self) -> None:
        entries = [self._make_entry(DiffCategory.NEW, "@I1@")]
        report = generate_diff_report(entries)
        assert report.has_changes is True

    def test_has_changes_true_when_updated_present(self) -> None:
        entries = [self._make_entry(DiffCategory.UPDATED, "@I1@")]
        report = generate_diff_report(entries)
        assert report.has_changes is True

    def test_has_changes_true_when_missing_present(self) -> None:
        entries = [self._make_entry(DiffCategory.MISSING, "@I1@")]
        report = generate_diff_report(entries)
        assert report.has_changes is True

    def test_has_changes_false_when_only_unchanged(self) -> None:
        entries = [
            self._make_entry(DiffCategory.UNCHANGED, "@I1@"),
            self._make_entry(DiffCategory.UNCHANGED, "@I2@"),
        ]
        report = generate_diff_report(entries)
        assert report.has_changes is False

    def test_empty_entries_produce_zero_counts(self) -> None:
        report = generate_diff_report([])
        assert report.new_count == 0
        assert report.updated_count == 0
        assert report.unchanged_count == 0
        assert report.missing_count == 0
        assert report.uncertain_count == 0
        assert report.total_count == 0
        assert report.has_uncertain is False
        assert report.has_changes is False
        assert report.entries == []
