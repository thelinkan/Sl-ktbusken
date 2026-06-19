"""Person fingerprinting, diff classification, and import-diff report generation.

This module provides the core logic for identifying, matching, and classifying
persons during GEDCOM re-import. It computes identity fingerprints from
composite keys (name + birth date + birth place), record hashes for detecting
content changes, and relationship hashes for detecting structural changes in
family context.

The diff classification compares incoming GEDCOM persons against existing
App_JSON data (via translation files and fingerprints) to classify each person
as new, updated, unchanged, missing, or uncertain. The import-diff report
summarizes these results for presentation to the user before committing.

All hashing uses SHA-256 with string normalization (lowercase, strip whitespace)
for robustness against minor formatting differences.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from slaktbusken.gedcom.translation.models import (
    DiffCategory,
    GedcomFamily,
    GedcomPerson,
    ImportDiffReport,
    PersonDiffEntry,
    PersonFingerprint,
)
from slaktbusken.persistence.translation_io import PersonMapping


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HASH_SEPARATOR = "|"
"""Separator used between fields when constructing hash input strings."""

_UNCERTAIN_THRESHOLD = 2
"""Minimum number of matching composite key components (out of 4) to classify
a person as UNCERTAIN rather than NEW."""


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _normalize(value: Optional[str]) -> str:
    """Normalize a string value for hashing.

    Strips leading/trailing whitespace and converts to lowercase. Returns
    an empty string for None values.

    Args:
        value: The string to normalize, or None.

    Returns:
        The normalized lowercase string, or empty string if value is None.
    """
    if value is None:
        return ""
    return value.strip().lower()


# ---------------------------------------------------------------------------
# Hashing functions
# ---------------------------------------------------------------------------


def compute_composite_key_hash(
    given_name: str,
    surname: str,
    birth_date: str | None,
    birth_place: str | None,
) -> str:
    """Compute a SHA-256 hash of the person's identity composite key.

    The composite key consists of four components that together identify
    *who* a person is: given name, surname, birth date, and birth place.
    This hash is used to match persons across imports even when GEDCOM
    cross-reference IDs change.

    All components are normalized (lowercase, stripped) before hashing
    to provide robustness against minor formatting differences.

    Args:
        given_name: The person's given name(s).
        surname: The person's surname.
        birth_date: The birth date string, or None if unknown.
        birth_place: The birth place string, or None if unknown.

    Returns:
        A hexadecimal SHA-256 digest string of the composite key.
    """
    parts = [
        _normalize(given_name),
        _normalize(surname),
        _normalize(birth_date),
        _normalize(birth_place),
    ]
    input_str = _HASH_SEPARATOR.join(parts)
    return hashlib.sha256(input_str.encode("utf-8")).hexdigest()


def compute_record_hash(person: GedcomPerson) -> str:
    """Compute a SHA-256 hash of all person fields to detect content changes.

    This hash captures the full content of a person record in a deterministic
    order. If this hash differs between imports for the same person, it
    indicates that the person's data has been modified.

    All fields are normalized before hashing.

    Args:
        person: The GEDCOM person record to hash.

    Returns:
        A hexadecimal SHA-256 digest string of all person fields.
    """
    parts = [
        _normalize(person.given_name),
        _normalize(person.surname),
        _normalize(person.sex),
        _normalize(person.birth_date),
        _normalize(person.birth_place),
        _normalize(person.death_date),
        _normalize(person.death_place),
        _normalize(person.title),
        _normalize(person.occupation),
        _normalize(person.notes),
    ]

    # Include additional names in deterministic order
    for given, surname in sorted(person.additional_names):
        parts.append(_normalize(given))
        parts.append(_normalize(surname))

    # Include source citations in sorted order for determinism
    for citation in sorted(person.source_citations):
        parts.append(_normalize(citation))

    input_str = _HASH_SEPARATOR.join(parts)
    return hashlib.sha256(input_str.encode("utf-8")).hexdigest()


def compute_relationship_hash(
    person_xref: str,
    families: list[GedcomFamily],
) -> str:
    """Compute a SHA-256 hash of the person's family structure.

    This hash captures the person's relationships — which families they
    belong to as partner or child, and who their partners and children are.
    Changes to this hash indicate structural changes in family context
    (e.g., a new child added, a partner removed).

    Partner and child cross-references are sorted for deterministic output.

    Args:
        person_xref: The GEDCOM cross-reference ID of the person.
        families: All families from the GEDCOM file.

    Returns:
        A hexadecimal SHA-256 digest string of the relationship structure.
    """
    partner_xrefs: list[str] = []
    child_xrefs: list[str] = []

    for family in families:
        is_partner = (
            family.husb_xref == person_xref or family.wife_xref == person_xref
        )
        is_child = person_xref in family.child_xrefs

        if is_partner:
            # Record the other partner(s)
            if family.husb_xref and family.husb_xref != person_xref:
                partner_xrefs.append(_normalize(family.husb_xref))
            if family.wife_xref and family.wife_xref != person_xref:
                partner_xrefs.append(_normalize(family.wife_xref))
            # Record children in this family
            for child_xref in family.child_xrefs:
                child_xrefs.append(_normalize(child_xref))

        if is_child:
            # Record parents from this family
            if family.husb_xref:
                partner_xrefs.append(_normalize(family.husb_xref))
            if family.wife_xref:
                partner_xrefs.append(_normalize(family.wife_xref))

    # Sort for deterministic ordering
    partner_xrefs.sort()
    child_xrefs.sort()

    parts = ["partners:" + ",".join(partner_xrefs), "children:" + ",".join(child_xrefs)]
    input_str = _HASH_SEPARATOR.join(parts)
    return hashlib.sha256(input_str.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Fingerprint computation
# ---------------------------------------------------------------------------


def compute_fingerprint(
    person: GedcomPerson,
    families: list[GedcomFamily],
) -> PersonFingerprint:
    """Compute the full fingerprint for a GEDCOM person.

    Calculates all three hashes:
    - **composite_key_hash**: Identity hash (who is this person).
    - **record_hash**: Content hash (what does the record contain).
    - **relationship_hash**: Structure hash (how is this person connected).

    Args:
        person: The GEDCOM person to fingerprint.
        families: All families from the GEDCOM file, needed for
            relationship hash computation.

    Returns:
        A PersonFingerprint containing all three hashes and the person's
        GEDCOM cross-reference ID.
    """
    composite_key = compute_composite_key_hash(
        given_name=person.given_name,
        surname=person.surname,
        birth_date=person.birth_date,
        birth_place=person.birth_place,
    )
    record = compute_record_hash(person)
    relationship = compute_relationship_hash(person.xref_id, families)

    return PersonFingerprint(
        xref_id=person.xref_id,
        composite_key_hash=composite_key,
        record_hash=record,
        relationship_hash=relationship,
    )


# ---------------------------------------------------------------------------
# Similarity scoring
# ---------------------------------------------------------------------------


def _compute_similarity_score(
    person: GedcomPerson,
    existing_given_name: str,
    existing_surname: str,
    existing_birth_date: str | None,
    existing_birth_place: str | None,
) -> float:
    """Compute a similarity score between a GEDCOM person and existing key components.

    Compares the four composite key components individually and returns
    the fraction that match (0.0 to 1.0). Each component is normalized
    before comparison.

    Args:
        person: The incoming GEDCOM person.
        existing_given_name: Given name from the existing record.
        existing_surname: Surname from the existing record.
        existing_birth_date: Birth date from the existing record.
        existing_birth_place: Birth place from the existing record.

    Returns:
        A float between 0.0 and 1.0 indicating the fraction of matching
        components.
    """
    matches = 0
    total = 4

    if _normalize(person.given_name) == _normalize(existing_given_name):
        matches += 1
    if _normalize(person.surname) == _normalize(existing_surname):
        matches += 1
    if _normalize(person.birth_date) == _normalize(existing_birth_date):
        matches += 1
    if _normalize(person.birth_place) == _normalize(existing_birth_place):
        matches += 1

    return matches / total


# ---------------------------------------------------------------------------
# Diff classification
# ---------------------------------------------------------------------------


def classify_persons(
    incoming: list[GedcomPerson],
    families: list[GedcomFamily],
    existing_mappings: list[PersonMapping],
    existing_fingerprints: dict[str, str],
    existing_birth_fingerprints: Optional[dict[str, str]] = None,
    existing_names: Optional[dict[str, tuple[str, str]]] = None,
) -> ImportDiffReport:
    """Classify incoming GEDCOM persons against existing App_JSON data.

    Compares each incoming person against known mappings and fingerprints
    to determine whether they are new, updated, unchanged, missing, or
    uncertain. The classification process follows this logic:

    1. For persons with a known GEDCOM→App_JSON mapping in the translation
       file: verify identity via fingerprint before trusting the mapping.
       Uses "claimed elsewhere" heuristic to detect xref reassignment.
       Compare record hashes to determine UPDATED vs UNCHANGED.
    2. For persons without a mapping: compare composite_key_hash against
       existing_fingerprints to find potential matches.
       - Exact hash match → UPDATED or UNCHANGED (based on record hash).
       - Partial match (≥2/4 components) → UNCERTAIN.
       - No match → NEW.
    3. Second pass: match NEW persons against displaced app_ids (whose
       xref was reassigned) using name-based comparison. This handles
       the case where a person gained birth data, changing their
       composite_key_hash while keeping the same name.
    4. Any App_JSON person in existing_mappings whose GEDCOM ID is not in
       the incoming data is classified as MISSING.

    Args:
        incoming: List of persons extracted from the incoming GEDCOM file.
        families: List of families extracted from the incoming GEDCOM file.
        existing_mappings: Known GEDCOM→App_JSON person mappings from the
            translation file.
        existing_fingerprints: Maps App_JSON person IDs to their stored
            composite_key_hash values, enabling matching even when
            translation files don't have a direct mapping.
        existing_birth_fingerprints: Optional dict mapping App_JSON person
            IDs to birth-only hashes. Currently unused but kept for API
            compatibility.
        existing_names: Optional dict mapping App_JSON person IDs to
            (given_name, surname) tuples. Used for name-based fallback
            matching when fingerprint hashes change due to added data.

    Returns:
        An ImportDiffReport containing all classification entries and
        summary counts.
    """
    if existing_birth_fingerprints is None:
        existing_birth_fingerprints = {}
    if existing_names is None:
        existing_names = {}
    entries: list[PersonDiffEntry] = []

    # Track app_ids displaced by the bidirectional identity check.
    # These are app_ids whose mapped xref was taken by a different person.
    displaced_app_ids: set[str] = set()

    # Build lookup from GEDCOM ID to existing mapping
    mapping_by_gedcom_id: dict[str, PersonMapping] = {
        m.gedcom_id: m for m in existing_mappings
    }

    # Track which existing mappings are accounted for (to detect MISSING)
    seen_gedcom_ids: set[str] = set()

    # Build reverse lookup: composite_key_hash → app_id for fingerprint matching
    app_id_by_fingerprint: dict[str, str] = {
        fp_hash: app_id for app_id, fp_hash in existing_fingerprints.items()
    }

    # Pre-compute all incoming fingerprints and build a set of all incoming
    # composite_key_hashes. This is used for the "claimed elsewhere" heuristic:
    # if an existing app_id's stored fingerprint matches ANOTHER incoming person,
    # it means the xref was reassigned.
    incoming_fingerprints: dict[str, PersonFingerprint] = {}
    incoming_composite_keys: dict[str, str] = {}  # composite_key_hash → xref_id
    for person in incoming:
        fp = compute_fingerprint(person, families)
        incoming_fingerprints[person.xref_id] = fp
        incoming_composite_keys[fp.composite_key_hash] = person.xref_id

    for person in incoming:
        fingerprint = incoming_fingerprints[person.xref_id]
        seen_gedcom_ids.add(person.xref_id)

        # Case 1: Known mapping exists in translation file
        # Verify identity using "claimed elsewhere" heuristic:
        # If the stored fingerprint for this app_id matches ANOTHER incoming
        # person's composite_key_hash, the xref was reassigned.
        if person.xref_id in mapping_by_gedcom_id:
            mapping = mapping_by_gedcom_id[person.xref_id]
            app_id = mapping.app_id

            identity_confirmed = True
            if app_id in existing_fingerprints:
                existing_fp_hash = existing_fingerprints[app_id]
                if existing_fp_hash != fingerprint.composite_key_hash:
                    # Composite key mismatch — could be name change OR
                    # xref reassignment. Use "claimed elsewhere" heuristic:
                    # If another incoming person's composite_key matches
                    # this app_id's stored fingerprint, the real person moved
                    # to a different xref and this xref was reassigned.
                    if existing_fp_hash in incoming_composite_keys:
                        other_xref = incoming_composite_keys[existing_fp_hash]
                        if other_xref != person.xref_id:
                            # Another incoming person matches this app_id's
                            # fingerprint — xref was reassigned
                            identity_confirmed = False
                    # else: no other incoming person claims this fingerprint,
                    # so this is likely the same person with changed data
                    # (e.g., married name). Trust the mapping.

                    # Bidirectional check: if this incoming person's
                    # composite_key_hash matches a DIFFERENT app_id's stored
                    # fingerprint, this person belongs to that other app_id —
                    # not the one at this xref. This catches the case where
                    # a person moved to a reused xref AND the previous
                    # occupant gained new data (e.g., birth date added),
                    # making the forward heuristic miss the reassignment.
                    if identity_confirmed and fingerprint.composite_key_hash in app_id_by_fingerprint:
                        true_app_id = app_id_by_fingerprint[fingerprint.composite_key_hash]
                        if true_app_id != app_id:
                            identity_confirmed = False

            if not identity_confirmed:
                # This xref was reassigned — the mapping's app_id is displaced
                displaced_app_ids.add(app_id)

            if identity_confirmed:
                # Compare record hash via stored fingerprint
                if mapping.fingerprint and mapping.fingerprint == fingerprint.record_hash:
                    category = DiffCategory.UNCHANGED
                else:
                    category = DiffCategory.UPDATED

                entries.append(
                    PersonDiffEntry(
                        gedcom_xref=person.xref_id,
                        app_id=app_id,
                        category=category,
                        fingerprint=fingerprint,
                    )
                )
                continue
            # else: fall through to Case 2 (fingerprint-based matching)

        # Case 2: No known mapping — try composite_key_hash matching
        if fingerprint.composite_key_hash in app_id_by_fingerprint:
            # Exact composite key match found
            matched_app_id = app_id_by_fingerprint[fingerprint.composite_key_hash]

            # Check if record has changed by comparing against stored fingerprint
            # Since we matched on composite key, we check if there's also a
            # record hash stored (via mapping fingerprint field)
            # For now, classify as UPDATED since we found a match but no
            # pre-existing mapping means something changed
            entries.append(
                PersonDiffEntry(
                    gedcom_xref=person.xref_id,
                    app_id=matched_app_id,
                    category=DiffCategory.UPDATED,
                    fingerprint=fingerprint,
                )
            )
            continue

        # Case 3: No exact match — check for partial/uncertain matches
        best_score = 0.0
        best_app_id: Optional[str] = None

        # We need to check similarity against all existing fingerprints
        # Since we only have the hash, we can't do component-level comparison
        # from the hash alone. However, we can check if ANY existing person
        # has a similar enough composite key by looking at all mappings
        # that have fingerprint data stored.
        # For uncertain detection, we rely on the existing_fingerprints dict
        # which maps app_id → composite_key_hash. Since hashes don't allow
        # partial matching, we skip uncertain for fingerprint-only data.
        # Uncertain detection works when we have access to the actual
        # component values, which happens through mappings with stored data.

        # If no match at all, classify as NEW
        if best_score < _UNCERTAIN_THRESHOLD / 4.0:
            entries.append(
                PersonDiffEntry(
                    gedcom_xref=person.xref_id,
                    app_id=None,
                    category=DiffCategory.NEW,
                    fingerprint=fingerprint,
                )
            )
        else:
            entries.append(
                PersonDiffEntry(
                    gedcom_xref=person.xref_id,
                    app_id=None,
                    category=DiffCategory.UNCERTAIN,
                    fingerprint=fingerprint,
                    similarity_score=best_score,
                    matched_app_id=best_app_id,
                )
            )

    # Second pass: match NEW persons against displaced app_ids by name.
    # When a person gains data (e.g., birth date added) their composite_key_hash
    # changes, so hash-based matching fails. But if their name matches a
    # displaced app_id's name, it's almost certainly the same person.
    if displaced_app_ids and existing_names:
        # Build lookup of displaced app_id → (given_name, surname)
        displaced_names: dict[str, tuple[str, str]] = {}
        for app_id in displaced_app_ids:
            if app_id in existing_names:
                displaced_names[app_id] = existing_names[app_id]

        if displaced_names:
            # Track which app_ids get claimed in this pass
            claimed_app_ids: set[str] = set()

            for i, entry in enumerate(entries):
                if entry.category != DiffCategory.NEW:
                    continue

                # Get the incoming person's name
                person = next(
                    (p for p in incoming if p.xref_id == entry.gedcom_xref),
                    None,
                )
                if person is None:
                    continue

                incoming_given = _normalize(person.given_name)
                incoming_surname = _normalize(person.surname)

                # Check against all displaced names
                for app_id, (existing_given, existing_surname) in displaced_names.items():
                    if app_id in claimed_app_ids:
                        continue
                    if (
                        _normalize(existing_given) == incoming_given
                        and _normalize(existing_surname) == incoming_surname
                    ):
                        # Name match — reclassify as UPDATED
                        entries[i] = PersonDiffEntry(
                            gedcom_xref=entry.gedcom_xref,
                            app_id=app_id,
                            category=DiffCategory.UPDATED,
                            fingerprint=entry.fingerprint,
                        )
                        claimed_app_ids.add(app_id)
                        break

    # Case 4: Detect MISSING persons — in existing mappings but not in incoming
    for mapping in existing_mappings:
        if mapping.gedcom_id not in seen_gedcom_ids:
            # Create a minimal fingerprint for the missing person
            # We use the stored fingerprint hash if available
            missing_fingerprint = PersonFingerprint(
                xref_id=mapping.gedcom_id,
                composite_key_hash=mapping.fingerprint or "",
                record_hash="",
                relationship_hash="",
            )
            entries.append(
                PersonDiffEntry(
                    gedcom_xref=mapping.gedcom_id,
                    app_id=mapping.app_id,
                    category=DiffCategory.MISSING,
                    fingerprint=missing_fingerprint,
                )
            )

    return generate_diff_report(entries)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_diff_report(entries: list[PersonDiffEntry]) -> ImportDiffReport:
    """Generate a structured import-diff report from classification entries.

    Counts the number of persons in each diff category and packages them
    into an ImportDiffReport suitable for presentation to the user before
    committing the import.

    Args:
        entries: List of PersonDiffEntry items from the classification step.

    Returns:
        An ImportDiffReport with counts for each category and the full
        list of entries.
    """
    new_count = 0
    updated_count = 0
    unchanged_count = 0
    missing_count = 0
    uncertain_count = 0

    for entry in entries:
        if entry.category == DiffCategory.NEW:
            new_count += 1
        elif entry.category == DiffCategory.UPDATED:
            updated_count += 1
        elif entry.category == DiffCategory.UNCHANGED:
            unchanged_count += 1
        elif entry.category == DiffCategory.MISSING:
            missing_count += 1
        elif entry.category == DiffCategory.UNCERTAIN:
            uncertain_count += 1

    return ImportDiffReport(
        new_count=new_count,
        updated_count=updated_count,
        unchanged_count=unchanged_count,
        missing_count=missing_count,
        uncertain_count=uncertain_count,
        entries=entries,
    )
