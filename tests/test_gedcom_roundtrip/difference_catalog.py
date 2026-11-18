"""Catalog of every known GEDCOM round-trip difference (design C12).

Each entry has a code (K1 to K43 of the design, K44 to K49 for the Source
fields that Requirement 9 criterion 13 requires to be listed), the
Difference_Class letters (A missing from the GEDCOM output, B lost or changed
by the importer, C not representable in GEDCOM 5.5.1 without extensions, D
Släktbusken-only data that is not exported), a status and the requirement
group that owns it.

``classes[0]`` is the root cause; a second letter is the reason an extension is
needed (design, "Classification of every known difference").

Status ``fixed`` means that the comparison must report zero such differences.
``deferred`` and ``app_only`` differences are listed in the report only.
"""

from __future__ import annotations

from dataclasses import dataclass

FIXED = "fixed"
DEFERRED = "deferred"
APP_ONLY = "app_only"

STATUSES: tuple[str, ...] = (FIXED, DEFERRED, APP_ONLY)
DIFFERENCE_CLASSES: tuple[str, ...] = ("A", "B", "C", "D")


@dataclass(frozen=True)
class CatalogEntry:
    code: str
    description: str
    classes: tuple[str, ...]
    status: str
    requirement: str

    @property
    def difference_class(self) -> str:
        """The class text as the design writes it, for example ``"A/C"``."""
        return "/".join(self.classes)

    @property
    def root_class(self) -> str:
        return self.classes[0]


def _e(
    code: str,
    description: str,
    classes: str,
    status: str,
    requirement: str,
) -> CatalogEntry:
    return CatalogEntry(code, description, tuple(classes.split("/")), status, requirement)


_ENTRIES: tuple[CatalogEntry, ...] = (
    _e("K1", "Marriage outside `Family.event_ids` not written", "A", FIXED, "1"),
    _e("K2", "Orphan family event without unique family", "A", FIXED, "1"),
    _e("K3", "Person notes not written", "A", FIXED, "2"),
    _e("K4", "Person title not written", "A", FIXED, "2"),
    _e("K5", "Multi-line text breaks the file (residence notes)", "A", FIXED, "2"),
    _e("K6", "NAME written without TYPE", "A", FIXED, "3"),
    _e("K7", "Name type chosen by position on import", "B", FIXED, "3"),
    _e("K8", "Update import resets existing name types", "B", FIXED, "3"),
    _e("K9", "`Name.event_id`", "C", FIXED, "3, 16"),
    _e("K10", "HUSB/WIFE by list order", "A", FIXED, "4"),
    _e("K11", "Partner roles collapse to husband and wife", "B/C", FIXED, "4"),
    _e("K12", "Update import overwrites partner roles", "B", FIXED, "4"),
    _e("K13", "Sex `X` written without SEX; `U` comes back as `U` (no loss)", "A/C", FIXED, "4"),
    _e(
        "K14",
        "Parentage `legal`, `step`, `unknown_donor`, `donation` not written",
        "A/C",
        FIXED,
        "5",
    ),
    _e("K15", "One PEDI applied to both parents", "B", FIXED, "5"),
    _e("K16", "Date and place citations flattened to event level", "C", FIXED, "6"),
    _e("K17", "Citation quality not written; `QUAY` ignored; import sets `secondary`", "A/B", FIXED, "6"),
    _e("K18", "Citation note and aspects not written", "A/C", FIXED, "6"),
    _e("K19", "`3 TEXT` under a citation holds source text", "A", DEFERRED, "6"),
    _e("K20", "`from_place` citations skipped", "C", FIXED, "6"),
    _e("K21", "`from_place` not restored", "C", FIXED, "6"),
    _e("K22", "Observation periods (prose written, ignored by importer)", "B/C", FIXED, "7"),
    _e("K23", "Observation quality", "A/B", FIXED, "7"),
    _e("K24", "`start.earliest`, `end.latest`, exact endpoints (prose ignored)", "B/C", FIXED, "7"),
    _e("K25", "`Endpoint.event_id`", "C", FIXED, "7, 16"),
    _e("K26", "Residence role and notes (prose written, ignored)", "B", FIXED, "7"),
    _e("K27", "Event types without export tag", "A", FIXED, "8"),
    _e("K28", "Participant roles become `subject`", "C", FIXED, "8"),
    _e(
        "K29",
        "Individual event with several participants written once per person, imported as separate events",
        "A/B",
        FIXED,
        "8",
    ),
    _e("K30", "Media, portraits, media links", "A/C", DEFERRED, "10"),
    _e("K31", "Repositories and call numbers", "A/B", FIXED, "9"),
    _e("K32", "Provider, `leverantor_id`, `kalltyp_id`", "A/C", FIXED, "9"),
    _e("K33", "`source_type` invented by keywords", "A/B", FIXED, "9"),
    _e("K34", "Structured reference value types, `page` null", "B", FIXED, "9"),
    _e("K35", "Place type (`church` to `ort`)", "C", DEFERRED, "10"),
    _e("K36", "Other place attributes (alternative names, notes, external ids)", "C", DEFERRED, "10"),
    _e(
        "K37",
        "DNA, clusters, research cases, merge history, `connection_overrides`",
        "D",
        APP_ONLY,
        "10",
    ),
    _e("K38", "Event origins, retired ids, translation files, edit state", "D", APP_ONLY, "10"),
    _e("K39", "Generated ids (person, family, event, source ids)", "D", APP_ONLY, "14"),
    _e("K40", "Person `profile_media_id`", "A/C", DEFERRED, "10"),
    _e("K41", "Record hash changes for records with new nodes", "B", FIXED, "12"),
    _e("K42", "Person `occupation` not written", "A", FIXED, "2"),
    _e(
        "K43",
        "HUSB/WIFE placeholder shown by other programs as husband and wife; `_SLK_PARTNER` ignored by them",
        "C",
        DEFERRED,
        "4",
    ),
    # Source fields without a GEDCOM representation (Requirement 9 criterion 13).
    # The design table has no code for them; K44 to K49 are added here.
    _e("K44", "Source `provider_ref` not exported", "A", DEFERRED, "9"),
    _e("K45", "Source `short_note` not exported", "A", DEFERRED, "9"),
    _e("K46", "Source `free_note` not exported", "A", DEFERRED, "9"),
    _e("K47", "Source `arkivreferens` not exported", "A", DEFERRED, "9"),
    _e("K48", "Source `arkivreferenser` not exported", "A", DEFERRED, "9"),
    _e("K49", "Source `media_ids` not exported (media deferred)", "A/C", DEFERRED, "9"),
    # Documented limitations of the finished round trip (task 13.2). Each one is
    # a difference that remains after the fixes above, or a deliberate
    # consequence of them.
    _e(
        "K50",
        "Source `reference_text` is rebuilt on import from the written citation text or "
        "the title (empty text becomes the title; `Bild 3` becomes `Bild: 3 Sida: 17`)",
        "B",
        DEFERRED,
        "9",
    ),
    _e(
        "K51",
        "Family event outside `Family.event_ids` is written once in its unique family "
        "and listed in `Family.event_ids` after import (the event itself round-trips)",
        "B",
        DEFERRED,
        "1",
    ),
    _e(
        "K52",
        "Legacy residence (no origin) whose endpoint links to an event is not claimed "
        "on re-import of a file that carries the link",
        "B",
        DEFERRED,
        "7, 16",
    ),
    _e(
        "K53",
        "Foster-only family without events that comes from an import is replaced by a "
        "family derived from the placement event (new id, same partners and roles); "
        "a family that holds placement and other events is split in two, and links "
        "without a placement event get a derived placement event",
        "B",
        DEFERRED,
        "5",
    ),
    _e(
        "K54",
        "Family with partial or missing parent-child links comes back with a "
        "biological link for every partner",
        "B",
        DEFERRED,
        "5",
    ),
    _e(
        "K55",
        "Swedish `NOTE` lines and `3 TEXT` are kept next to the `_SLK_` lines so that "
        "record hashes stay stable",
        "C",
        DEFERRED,
        "12",
    ),
    _e(
        "K56",
        "Death cause (`Event.cause_of_death`) is not written; the importer reads `CAUS` "
        "but the exporter writes none",
        "A",
        FIXED,
        "8",
    ),
    _e(
        "K57",
        "Old hash-based xrefs `@X<abs(hash(id)) % 99999>@` (records whose id has no "
        "numeric suffix) were never stable; importing such an old file into a project "
        "that holds a new export of the same data creates duplicates (MergeTest: "
        "2 families, 2 marriages), no matcher is added",
        "B",
        DEFERRED,
        "12",
    ),
)

CATALOG: dict[str, CatalogEntry] = {entry.code: entry for entry in _ENTRIES}

# Source fields that the exporter does not write, with the code that covers each.
UNCOVERED_SOURCE_FIELDS: dict[str, str] = {
    "provider_ref": "K44",
    "short_note": "K45",
    "free_note": "K46",
    "arkivreferens": "K47",
    "arkivreferenser": "K48",
    "media_ids": "K49",
}


def code_number(code: str) -> int:
    return int(code[1:])


def entry_for(code: str) -> CatalogEntry | None:
    return CATALOG.get(code)


def sorted_codes() -> list[str]:
    return sorted(CATALOG, key=code_number)
