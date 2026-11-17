"""Registry of the ``_SLK_`` custom GEDCOM tags and the tolerant readers.

The registry :data:`SLK_TAG_REGISTRY` is the code form of the "Tag Registry"
table of the design of ``gedcom-roundtrip-0-3-0``. The readers are pure and
*total*: they never raise on malformed input. An uninterpretable value of a
known tag becomes a :class:`SlkProblem` (a Recoverable_Input_Problem that the
importer turns into a warning) and the reader returns the standard fallback.
Unknown ``_SLK_`` tags are never reported as problems; the importer lists them
through :func:`unknown_slk_children` as an info line.

Every reader takes an optional ``problems`` list and appends to it. No reader
touches ``_SLK_EREF`` (only the Event_Link_Module reads it) and none writes to
the project.

Pure module: no Qt, no I/O.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Collection, Optional

from slaktbusken.gedcom.parser import GedcomLine
from slaktbusken.model.date_span import is_valid_iso, strictly_earlier
from slaktbusken.model.validators import (
    _STRUCTURED_REFERENCE_FIELDS,
    _VALID_PARENTAGE_TYPES,
    _VALID_PARTNER_ROLES,
    _VALID_SOURCE_TYPES,
)

SLK_PREFIX = "_SLK_"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SlkTag:
    """One row of the Tag_Registry.

    ``parents`` names the tags below which the tag may occur. Symbolic names in
    angle brackets stand for groups: ``<event>`` any INDI or FAM event
    structure (including ``EVEN``), ``<family event>`` a FAM event structure,
    ``<SOUR record>`` and ``<REPO record>`` the level-0 records. ``SOUR`` is a
    citation and ``REPO`` the ``1 REPO`` reference below a SOUR record.
    """

    tag: str
    purpose: str
    parents: tuple[str, ...]
    children: tuple[str, ...]
    cardinality: str  # "0:1", "0:n" or "1:1"
    supported_values: str
    importer_behaviour: str
    standard_fallback: str

    @property
    def structure(self) -> str:
        children = ", ".join(self.children) if self.children else "none"
        return f"{', '.join(self.parents)}; {children}; {self.cardinality}"


def _row(
    tag: str,
    purpose: str,
    parents: tuple[str, ...],
    children: tuple[str, ...],
    cardinality: str,
    supported_values: str,
    importer_behaviour: str,
    standard_fallback: str,
) -> SlkTag:
    return SlkTag(
        tag,
        purpose,
        parents,
        children,
        cardinality,
        supported_values,
        importer_behaviour,
        standard_fallback,
    )


_ENDPOINT_PARENTS = ("_SLK_START", "_SLK_END")
_ENDPOINT_BEHAVIOUR = (
    "Present: the endpoint is built from the children, DATE and prose are "
    "ignored for it. All children bad: endpoint from DATE, warning"
)

_ROWS: tuple[SlkTag, ...] = (
    _row(
        "_SLK_VERS",
        "Marks a file as written to this registry; selects Hash_Profile slk1",
        ("HEAD",), (), "0:1", "1",
        "Absent: profile legacy. Any other value: profile legacy, one warning "
        "(no slk1 rules are guessed)",
        "HEAD.SOUR names Släktbusken",
    ),
    _row(
        "_SLK_EID",
        "Names one Event inside the file so that other structures and the "
        "fallback can refer to it",
        ("<event>",), (), "0:1", "non-empty text without spaces",
        "Empty: ignored, event is single. Twice on one INDI with equal token: "
        "first used, warning",
        "none",
    ),
    _row(
        "_SLK_EVTYPE",
        "Släktbusken event type of an EVEN",
        ("EVEN",), (), "0:1", "event type text",
        "Known type: that type. Unknown type: custom_individual_event with the "
        "TYPE text, warning",
        "EVEN.TYPE text",
    ),
    _row(
        "_SLK_ROLE",
        "Participant role of an INDI event, event participant or partner",
        ("<event>", "_SLK_PART", "_SLK_PARTNER"), (), "0:1", "role text",
        "Empty or absent: subject (INDI event), spouse (FAM event participant), "
        "husband/wife by slot (partner, only if no _SLK_PARTNER is usable)",
        "none",
    ),
    _row(
        "_SLK_PART",
        "Participant of a family event",
        ("<family event>",), ("_SLK_ROLE",), "0:n",
        "@Ix@ of an INDI in the file",
        "Pointer to no INDI: entry skipped, warning. No usable entry: "
        "participants and role spouse as before",
        "HUSB, WIFE of the FAM",
    ),
    _row(
        "_SLK_PARTNER",
        "Partner list entry: order and role, tied to the individual",
        ("FAM",), ("_SLK_ROLE",), "0:n", "@Ix@ of an INDI in the file",
        "Used only if the entries name exactly the persons of HUSB and WIFE; "
        "else all entries ignored, warning, partners from HUSB/WIFE with roles "
        "husband, wife. Never changes Person.sex",
        "HUSB, WIFE (placeholders)",
    ),
    _row(
        "_SLK_SEX",
        "Sex X",
        ("SEX",), (), "0:1", "X",
        "Other value: ignored, warning, sex from SEX",
        "SEX U",
    ),
    _row(
        "_SLK_PLINK",
        "Parent-child link with its own parentage type",
        ("FAMC",), ("TYPE",), "0:n",
        "@Ix@ of a parent, or empty for a link without parent",
        "Pointer to no INDI: link without parent, warning. Unknown TYPE: PEDI "
        "of the FAMC is used, warning",
        "PEDI",
    ),
    _row(
        "_SLK_QUAL",
        "Citation quality that QUAY cannot hold",
        ("SOUR",), (), "0:1", "non-empty text",
        "Read before QUAY. Empty: ignored, QUAY used",
        "QUAY",
    ),
    _row(
        "_SLK_CTX",
        "Context of a citation of an event",
        ("SOUR",), (), "0:1", "date, place, from_place",
        "Other value: context event, warning. Context whose carrier (date, "
        "place, from_place) is absent: event level, no warning",
        "event-level SOUR",
    ),
    _row(
        "_SLK_ASP",
        "One aspect of a citation",
        ("SOUR",), (), "0:n", "text",
        "Empty: skipped",
        "none",
    ),
    _row(
        "_SLK_FROMPLAC",
        "from_place of a flytt event",
        ("EVEN",), (), "0:1", "place hierarchy text",
        "Empty: no from_place",
        "NOTE Från:",
    ),
    _row(
        "_SLK_START",
        "Container of the start endpoint of a residence",
        ("RESI",),
        ("_SLK_EARLIEST", "_SLK_LATEST", "_SLK_PREC", "_SLK_EREF", "_SLK_NOTE"),
        "0:1", "none",
        _ENDPOINT_BEHAVIOUR,
        "DATE FROM … TO …",
    ),
    _row(
        "_SLK_END",
        "Container of the end endpoint of a residence",
        ("RESI",),
        ("_SLK_EARLIEST", "_SLK_LATEST", "_SLK_PREC", "_SLK_EREF", "_SLK_NOTE"),
        "0:1", "none",
        _ENDPOINT_BEHAVIOUR,
        "DATE FROM … TO …",
    ),
    _row(
        "_SLK_EARLIEST",
        "Earliest bound of an endpoint",
        _ENDPOINT_PARENTS, (), "0:1", "ISO date YYYY, YYYY-MM or YYYY-MM-DD",
        "Invalid date: that bound unset, warning",
        "DATE, prose NOTE",
    ),
    _row(
        "_SLK_LATEST",
        "Latest bound of an endpoint",
        _ENDPOINT_PARENTS, (), "0:1", "ISO date YYYY, YYYY-MM or YYYY-MM-DD",
        "Invalid date: that bound unset, warning",
        "DATE, prose NOTE",
    ),
    _row(
        "_SLK_PREC",
        "Endpoint precision",
        _ENDPOINT_PARENTS, (), "0:1", "day, month, year, approximate",
        "Other value: precision derived from the date, warning",
        "ABT in DATE",
    ),
    _row(
        "_SLK_EREF",
        "Link of a Name or an endpoint to an Event (Event_Link_Module)",
        ("NAME", "_SLK_START", "_SLK_END"), (), "0:1",
        "an Event_Token of the file",
        "Token without event: link empty, warning. Module removed: ignored",
        "none",
    ),
    _row(
        "_SLK_NOTE",
        "Endpoint note or note of an observation citation",
        ("_SLK_START", "_SLK_END", "SOUR"), (), "0:1", "text (CONT/CONC)",
        "Empty: ignored",
        "none",
    ),
    _row(
        "_SLK_HHROLE",
        "ResidenceFact.role_in_household",
        ("RESI",), (), "0:1", "text",
        "Empty: unset",
        "NOTE Roll:",
    ),
    _row(
        "_SLK_RNOTES",
        "ResidenceFact.notes",
        ("RESI",), (), "0:1", "text",
        "Empty: unset",
        "NOTE",
    ),
    _row(
        "_SLK_OBSFROM",
        "Observation period start",
        ("SOUR",), (), "0:1", "YYYY",
        "Invalid year or start after end: period from NOTE Observation:, else "
        "unset, warning",
        "NOTE Observation:",
    ),
    _row(
        "_SLK_OBSTO",
        "Observation period end",
        ("SOUR",), (), "0:1", "YYYY",
        "Invalid year or start after end: period from NOTE Observation:, else "
        "unset, warning",
        "NOTE Observation:",
    ),
    _row(
        "_SLK_STYPE",
        "Source.source_type",
        ("<SOUR record>",), (), "0:1", "a known source type",
        "Unknown value: keyword detection of detect_source_type, warning",
        "keyword detection",
    ),
    _row(
        "_SLK_PROV",
        "Source.provider",
        ("<SOUR record>",), (), "0:1", "text",
        "Empty: provider as before",
        "AUTH",
    ),
    _row(
        "_SLK_LEV",
        "Leverantör by name",
        ("<SOUR record>",), (), "0:1", "name text",
        "No such name in the project: ids stay empty, no warning",
        "none",
    ),
    _row(
        "_SLK_KTYP",
        "Källtyp by name",
        ("<SOUR record>",), (), "0:1", "name text",
        "No such name in the project: ids stay empty, no warning",
        "none",
    ),
    _row(
        "_SLK_SREF",
        "Container of structured reference fields",
        ("<SOUR record>",), ("_SLK_FLD",), "0:1", "none",
        "Empty or all fields bad: reference text parsed as before",
        "TEXT",
    ),
    _row(
        "_SLK_FLD",
        "One structured reference field",
        ("_SLK_SREF",), (), "0:n",
        "<key> <json> where json is a string, an integer or null",
        "Bad JSON or unknown key: field skipped, warning",
        "TEXT",
    ),
    _row(
        "_SLK_RTYPE",
        "Repository.type",
        ("<REPO record>",), (), "0:1", "text",
        "Empty: type empty",
        "none",
    ),
    _row(
        "_SLK_XID",
        "One entry of Repository.external_ids",
        ("<REPO record>",), (), "0:n", "text",
        "Empty: skipped",
        "none",
    ),
    _row(
        "_SLK_RSTYPE",
        "RepositoryRef.source_type",
        ("REPO",), (), "0:1", "text",
        "Empty: unset",
        "none",
    ),
    _row(
        "_SLK_RIMG",
        "RepositoryRef.image_number",
        ("REPO",), (), "0:1", "non-negative integer",
        "Not an integer: unset, warning",
        "none",
    ),
    _row(
        "_SLK_RPAGE",
        "RepositoryRef.page_number",
        ("REPO",), (), "0:1", "non-negative integer",
        "Not an integer: unset, warning",
        "none",
    ),
    _row(
        "_SLK_RMEDNAME",
        "RepositoryRef.media_name",
        ("REPO",), (), "0:1", "text",
        "Empty: unset",
        "CALN.MEDI holds the media type only",
    ),
)

SLK_TAG_REGISTRY: dict[str, SlkTag] = {row.tag: row for row in _ROWS}


def is_known_slk_tag(tag: str) -> bool:
    """Whether *tag* is in the registry."""
    return tag in SLK_TAG_REGISTRY


def unknown_slk_children(node: Optional[GedcomLine]) -> list[GedcomLine]:
    """Children of *node* with a ``_SLK_`` tag that is not in the registry.

    These are skipped together with their children and are not a problem; the
    caller may write one info line per entry to the import log.
    """
    return [
        child
        for child in _children(node)
        if _tag(child).startswith(SLK_PREFIX) and _tag(child) not in SLK_TAG_REGISTRY
    ]


# ---------------------------------------------------------------------------
# Problems and small helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SlkProblem:
    """A Recoverable_Input_Problem: the importer turns it into a warning."""

    code: str
    message: str  # Swedish
    tag: str = ""
    line_number: int = 0


def _tag(node: object) -> str:
    tag = getattr(node, "tag", "")
    return tag if isinstance(tag, str) else ""


def _text(node: object) -> str:
    """The value of *node* as text; ``""`` for no value."""
    value = getattr(node, "value", None)
    return value if isinstance(value, str) else ""


def _line(node: object) -> int:
    number = getattr(node, "line_number", 0)
    return number if isinstance(number, int) else 0


def _children(node: Optional[GedcomLine]) -> list[GedcomLine]:
    kids = getattr(node, "children", None)
    return list(kids) if isinstance(kids, list) else []


def _kids(node: Optional[GedcomLine], tag: str) -> list[GedcomLine]:
    return [c for c in _children(node) if _tag(c) == tag]


def _report(
    problems: Optional[list[SlkProblem]],
    code: str,
    message: str,
    node: object = None,
) -> None:
    if problems is not None:
        problems.append(SlkProblem(code, message, _tag(node), _line(node)))


def _first(
    node: Optional[GedcomLine],
    tag: str,
    problems: Optional[list[SlkProblem]],
) -> Optional[GedcomLine]:
    """First child *tag* of a ``0:1`` tag; a repeat gives one warning."""
    found = _kids(node, tag)
    if len(found) > 1:
        _report(
            problems,
            "duplicate",
            f"{tag} förekommer flera gånger; första värdet används.",
            found[1],
        )
    return found[0] if found else None


_POINTER_RE = re.compile(r"^@[^@\s]+@$")


def _pointer(
    value: str,
    known_xrefs: Optional[Collection[str]],
) -> Optional[str]:
    """The xref in *value* when it is a pointer to a known record, else ``None``."""
    xref = value.strip()
    if not _POINTER_RE.match(xref):
        return None
    if known_xrefs is not None and xref not in known_xrefs:
        return None
    return xref


def _valid_date(value: str) -> bool:
    return value.isascii() and value == value.strip() and is_valid_iso(value)


_YEAR_RE = re.compile(r"^[0-9]{4}$")
_OBS_YEAR_MIN, _OBS_YEAR_MAX = 1500, 2100


def _valid_obs_year(value: str) -> bool:
    return bool(_YEAR_RE.match(value)) and _OBS_YEAR_MIN <= int(value) <= _OBS_YEAR_MAX


def _parse_observation_period(value: str) -> Optional[tuple[str, str]]:
    """Parse ``YYYY`` or ``YYYY-YYYY`` (start not after end) to ``(from, to)``.

    ``to`` equals ``from`` for a single year. Returns ``None`` for anything else.
    """
    parts = value.split("-")
    if len(parts) not in (1, 2) or not all(_valid_obs_year(p) for p in parts):
        return None
    start, end = parts[0], parts[-1]
    if int(start) > int(end):
        return None
    return start, end


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------


@dataclass
class CitationData:
    """What a citation ``SOUR`` line says, with standard fallbacks applied."""

    quality: str = "secondary"
    context: str = "event"
    note: str = ""
    page: str = ""
    aspects: list[str] = field(default_factory=list)
    observed_from: str = ""
    observed_to: str = ""


_QUAY_TO_QUALITY = {"3": "primary", "2": "secondary", "1": "tertiary", "0": "tertiary"}
_CONTEXTS = ("date", "place", "from_place")
_OBSERVATION_PREFIX = "Observation:"


def read_citation(
    node: Optional[GedcomLine],
    problems: Optional[list[SlkProblem]] = None,
) -> CitationData:
    """Read a citation ``SOUR`` line (event or observation). Total."""
    data = CitationData()

    # Quality: _SLK_QUAL first, then QUAY (3, 2, 1 and 0), else secondary.
    qual = _first(node, "_SLK_QUAL", problems)
    if qual is not None and _text(qual).strip():
        data.quality = _text(qual).strip()
    else:
        quay = _first(node, "QUAY", None)
        if quay is not None:
            mapped = _QUAY_TO_QUALITY.get(_text(quay).strip())
            if mapped is None:
                _report(
                    problems, "bad_quay",
                    f"Ogiltigt QUAY-värde '{_text(quay)}'; kvaliteten sätts till "
                    "'secondary'.",
                    quay,
                )
            else:
                data.quality = mapped

    ctx = _first(node, "_SLK_CTX", problems)
    if ctx is not None and _text(ctx).strip():
        value = _text(ctx).strip()
        if value in _CONTEXTS:
            data.context = value
        else:
            _report(
                problems, "bad_ctx",
                f"Ogiltigt _SLK_CTX-värde '{value}'; händelsenivå används.",
                ctx,
            )

    # Note: _SLK_NOTE (observations) first, then the first NOTE that is not
    # the exporter's "Observation:" line.
    slk_note = _first(node, "_SLK_NOTE", problems)
    if slk_note is not None and _text(slk_note).strip():
        data.note = _text(slk_note)
    else:
        for note in _kids(node, "NOTE"):
            if not _text(note).startswith(_OBSERVATION_PREFIX):
                data.note = _text(note)
                break

    page = _first(node, "PAGE", None)
    if page is not None:
        data.page = _text(page)

    data.aspects = [
        _text(a) for a in _kids(node, "_SLK_ASP") if _text(a).strip()
    ]

    data.observed_from, data.observed_to = _read_observation_period(node, problems)
    return data


def _read_observation_period(
    node: Optional[GedcomLine],
    problems: Optional[list[SlkProblem]],
) -> tuple[str, str]:
    from_node = _first(node, "_SLK_OBSFROM", problems)
    to_node = _first(node, "_SLK_OBSTO", problems)
    start = _text(from_node).strip() if from_node is not None else ""
    end = _text(to_node).strip() if to_node is not None else ""
    if not start and not end:
        return "", ""

    bad = False
    for raw, tag_node in ((start, from_node), (end, to_node)):
        if raw and not _valid_obs_year(raw):
            _report(
                problems, "bad_obs_year",
                f"Ogiltigt observationsår '{raw}' (förväntat ÅÅÅÅ mellan 1500 "
                "och 2100).",
                tag_node,
            )
            bad = True
    if not bad and start and end and int(start) > int(end):
        _report(
            problems, "inverted_obs_period",
            f"Observationens startår {start} är senare än slutåret {end}.",
            from_node,
        )
        bad = True
    if not bad:
        return start, end

    # Fall back to the exporter's own "NOTE Observation:" line, else unset.
    for note in _kids(node, "NOTE"):
        text = _text(note)
        if text.startswith(_OBSERVATION_PREFIX + " "):
            period = _parse_observation_period(text[len(_OBSERVATION_PREFIX) + 1:])
            if period is not None:
                return period
    return "", ""


# ---------------------------------------------------------------------------
# Residence endpoints
# ---------------------------------------------------------------------------

_PRECISIONS = ("day", "month", "year", "approximate")
_ENDPOINT_NOTE_MAX = 1000


@dataclass
class EndpointData:
    """One residence endpoint read from ``_SLK_START`` or ``_SLK_END``."""

    earliest: Optional[str] = None
    latest: Optional[str] = None
    precision: Optional[str] = None
    note: Optional[str] = None


def _derived_precision(*dates: Optional[str]) -> Optional[str]:
    """The coarsest precision of the given ISO dates; ``None`` without a date."""
    sizes = [len(d.split("-")) for d in dates if d]
    if not sizes:
        return None
    return {1: "year", 2: "month", 3: "day"}[min(sizes)]


def read_endpoint(
    node: Optional[GedcomLine],
    problems: Optional[list[SlkProblem]] = None,
) -> Optional[EndpointData]:
    """Read a ``_SLK_START``/``_SLK_END`` node. Total.

    Returns ``None`` when the node gives no usable value; the caller then
    builds the endpoint from ``DATE``. ``_SLK_EREF`` is not read here.
    """
    if node is None:
        return None
    data = EndpointData()
    seen_value = False

    bounds: dict[str, Optional[str]] = {}
    for tag in ("_SLK_EARLIEST", "_SLK_LATEST"):
        child = _first(node, tag, problems)
        raw = _text(child).strip() if child is not None else ""
        if not raw:
            bounds[tag] = None
            continue
        seen_value = True
        if _valid_date(raw):
            bounds[tag] = raw
        else:
            bounds[tag] = None
            _report(
                problems, "bad_date",
                f"Ogiltigt datum '{raw}' i {tag} (förväntat ÅÅÅÅ, ÅÅÅÅ-MM eller "
                "ÅÅÅÅ-MM-DD).",
                child,
            )
    earliest, latest = bounds["_SLK_EARLIEST"], bounds["_SLK_LATEST"]
    if earliest and latest and strictly_earlier(latest, earliest):
        _report(
            problems, "inverted_endpoint",
            f"Tidigaste datum {earliest} är senare än senaste datum {latest}.",
            node,
        )
        earliest = latest = None
    data.earliest, data.latest = earliest, latest

    prec = _first(node, "_SLK_PREC", problems)
    raw_prec = _text(prec).strip() if prec is not None else ""
    if raw_prec:
        seen_value = True
        if raw_prec in _PRECISIONS:
            data.precision = raw_prec
        else:
            _report(
                problems, "bad_precision",
                f"Ogiltig precision '{raw_prec}'; härleds från datumet.",
                prec,
            )
            data.precision = _derived_precision(earliest, latest)

    note = _first(node, "_SLK_NOTE", problems)
    if note is not None and _text(note).strip():
        seen_value = True
        text = _text(note)
        if len(text) > _ENDPOINT_NOTE_MAX:
            _report(
                problems, "note_too_long",
                f"Endpunktens anteckning kortades till {_ENDPOINT_NOTE_MAX} tecken.",
                note,
            )
            text = text[:_ENDPOINT_NOTE_MAX]
        data.note = text

    if data.earliest is None and data.latest is None and data.precision is None \
            and data.note is None:
        if seen_value:
            _report(
                problems, "endpoint_unusable",
                f"{_tag(node)} saknar användbara värden; datumraden används.",
                node,
            )
        return None
    return data


_RESIDENCE_NOTES_MAX = 5000


def read_residence_texts(
    resi: Optional[GedcomLine],
    problems: Optional[list[SlkProblem]] = None,
) -> tuple[str, str]:
    """Read ``_SLK_HHROLE`` and ``_SLK_RNOTES`` of a RESI record as ``(role, notes)``.

    Empty text gives ``""``. A role longer than 100 characters (after trim)
    is ignored and a note longer than 5000 characters is cut, both with a
    problem. Total.
    """
    role = ""
    role_node = _first(resi, "_SLK_HHROLE", problems)
    if role_node is not None and _text(role_node).strip():
        role = _text(role_node)
        if len(role.strip()) > _ROLE_MAX_LENGTH:
            _report(
                problems, "role_too_long",
                f"_SLK_HHROLE är längre än {_ROLE_MAX_LENGTH} tecken och "
                "ignorerades.",
                role_node,
            )
            role = ""
    notes = ""
    notes_node = _first(resi, "_SLK_RNOTES", problems)
    if notes_node is not None and _text(notes_node).strip():
        notes = _text(notes_node)
        if len(notes) > _RESIDENCE_NOTES_MAX:
            _report(
                problems, "notes_too_long",
                f"_SLK_RNOTES kortades till {_RESIDENCE_NOTES_MAX} tecken.",
                notes_node,
            )
            notes = notes[:_RESIDENCE_NOTES_MAX]
    return role, notes


# ---------------------------------------------------------------------------
# Partners
# ---------------------------------------------------------------------------


def read_partners(
    fam: Optional[GedcomLine],
    known_xrefs: Optional[Collection[str]] = None,
    problems: Optional[list[SlkProblem]] = None,
) -> Optional[list[tuple[str, str]]]:
    """Read the ``_SLK_PARTNER`` list of a FAM record as ``(xref, role)`` pairs.

    Returns ``None`` when there is no ``_SLK_PARTNER`` or when the entries do
    not name exactly the persons of HUSB and WIFE (the latter with a problem);
    the caller then takes the partners from HUSB and WIFE. An absent or empty
    role gets the slot role of that person (``husband`` or ``wife``), and so
    does a role that is not a valid partner role (with a problem). Total.
    """
    entries = _kids(fam, "_SLK_PARTNER")
    if not entries:
        return None

    husb = _first(fam, "HUSB", None)
    wife = _first(fam, "WIFE", None)
    husb_ref = _text(husb).strip() if husb is not None else ""
    wife_ref = _text(wife).strip() if wife is not None else ""
    slots = {x for x in (husb_ref, wife_ref) if x}

    xrefs: list[str] = []
    ok = True
    for entry in entries:
        xref = _pointer(_text(entry), known_xrefs)
        if xref is None:
            ok = False
            break
        xrefs.append(xref)
    if ok and (len(set(xrefs)) != len(xrefs) or set(xrefs) != slots):
        ok = False
    if not ok:
        _report(
            problems, "partners_mismatch",
            "_SLK_PARTNER stämmer inte med HUSB och WIFE; partnerna läses från "
            "HUSB och WIFE.",
            entries[0],
        )
        return None

    result: list[tuple[str, str]] = []
    for entry, xref in zip(entries, xrefs):
        slot_role = "husband" if xref == husb_ref else "wife"
        role_node = _first(entry, "_SLK_ROLE", problems)
        role = _text(role_node).strip() if role_node is not None else ""
        if role and role not in _VALID_PARTNER_ROLES:
            _report(
                problems, "bad_partner_role",
                f"Ogiltig partnerroll '{role}'; '{slot_role}' används.",
                role_node,
            )
            role = ""
        result.append((xref, role or slot_role))
    return result


def read_event_participants(
    event: Optional[GedcomLine],
    known_xrefs: Optional[Collection[str]] = None,
    problems: Optional[list[SlkProblem]] = None,
) -> Optional[list[tuple[str, str]]]:
    """Read the ``_SLK_PART`` entries of a family event as ``(xref, role)``.

    An entry that points to no known INDI is skipped with a problem, and so is
    a repeated pointer (the first entry wins). An empty or absent role is
    ``spouse``. Returns ``None`` when there is no usable entry; the caller then
    takes the participants from HUSB and WIFE with the role ``spouse``. Total.
    """
    entries = _kids(event, "_SLK_PART")
    if not entries:
        return None
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for entry in entries:
        xref = _pointer(_text(entry), known_xrefs)
        if xref is None:
            _report(
                problems, "unknown_participant",
                f"_SLK_PART pekar på '{_text(entry)}' som inte är en person i "
                "filen; deltagaren hoppas över.",
                entry,
            )
            continue
        if xref in seen:
            _report(
                problems, "duplicate_participant",
                f"_SLK_PART pekar flera gånger på {xref}; första posten används.",
                entry,
            )
            continue
        seen.add(xref)
        role_node = _first(entry, "_SLK_ROLE", problems)
        role = _text(role_node).strip() if role_node is not None else ""
        result.append((xref, role or "spouse"))
    return result or None


# ---------------------------------------------------------------------------
# Event tags: role, type, token and from_place
# ---------------------------------------------------------------------------

# Event types the application knows (the types of the event editor).
KNOWN_EVENT_TYPES = frozenset({
    "adoption", "adoption_ended", "foster_home", "foster_home_ended",
    "baptism", "birth", "blessing", "burial", "census", "confirmation",
    "cremation", "death", "emigration", "first_communion", "flytt",
    "gender_correction", "graduation", "immigration", "name_change",
    "retirement", "will", "custom_individual_event",
    "divorce", "divorce_filed", "engagement", "marriage",
    "custom_family_event",
})

# Family types: a ``1 EVEN`` of an INDI with one of these is an
# Individual_Fallback structure.
FAMILY_EVENT_TYPES = frozenset({
    "divorce", "divorce_filed", "engagement", "marriage", "custom_family_event",
})

_ROLE_MAX_LENGTH = 100


@dataclass
class EventTagData:
    """``_SLK_ROLE``, ``_SLK_EVTYPE``, ``_SLK_EID`` and ``_SLK_FROMPLAC`` of an event.

    ``role`` is ``None`` when absent or empty. ``evtype`` is the text of
    ``_SLK_EVTYPE`` (``None`` when absent or empty) and ``evtype_known`` tells
    whether it names a known event type. ``token`` is ``None`` for an absent,
    empty or unusable token. ``from_place`` is the place text or ``None``.
    """

    role: Optional[str] = None
    evtype: Optional[str] = None
    evtype_known: bool = False
    token: Optional[str] = None
    from_place: Optional[str] = None


def read_event_tags(
    event: Optional[GedcomLine],
    problems: Optional[list[SlkProblem]] = None,
) -> EventTagData:
    """Read the ``_SLK_`` tags of one event structure. Total; never raises.

    A repeated tag uses the first value and gives a problem. A token with
    white space inside is unusable: ignored with a problem. An unknown
    ``_SLK_EVTYPE`` is returned with ``evtype_known`` false; the importer
    decides what to create and warns.
    """
    data = EventTagData()

    role_node = _first(event, "_SLK_ROLE", problems)
    role = _text(role_node).strip() if role_node is not None else ""
    if role:
        if len(role) > _ROLE_MAX_LENGTH:
            _report(
                problems, "role_too_long",
                f"_SLK_ROLE är längre än {_ROLE_MAX_LENGTH} tecken och "
                "ignorerades.",
                role_node,
            )
        else:
            data.role = role

    type_node = _first(event, "_SLK_EVTYPE", problems)
    evtype = _text(type_node).strip() if type_node is not None else ""
    if evtype:
        data.evtype = evtype
        data.evtype_known = evtype in KNOWN_EVENT_TYPES

    eid_node = _first(event, "_SLK_EID", problems)
    token = _text(eid_node).strip() if eid_node is not None else ""
    if token:
        if any(ch.isspace() for ch in token):
            _report(
                problems, "bad_event_token",
                f"_SLK_EID '{token}' innehåller blanksteg och ignorerades; "
                "händelsen behandlas som en enskild händelse.",
                eid_node,
            )
        else:
            data.token = token

    from_node = _first(event, "_SLK_FROMPLAC", problems)
    from_place = _text(from_node).strip() if from_node is not None else ""
    if from_place:
        data.from_place = from_place
    return data


# ---------------------------------------------------------------------------
# Parent-child links and name types
# ---------------------------------------------------------------------------


@dataclass
class PlinkData:
    """One ``_SLK_PLINK``: a parent (or none) and a parentage type (or ``None``)."""

    parent_xref: Optional[str]
    parentage_type: Optional[str]


def read_parentage_type(
    node: Optional[GedcomLine],
    problems: Optional[list[SlkProblem]] = None,
) -> Optional[str]:
    """Read the ``TYPE`` child of a ``_SLK_PLINK`` as a parentage type.

    ``None`` (with a problem) when absent or unknown: the caller uses ``PEDI``.
    """
    type_node = _first(node, "TYPE", None)
    value = _text(type_node).strip().lower() if type_node is not None else ""
    if value in _VALID_PARENTAGE_TYPES:
        return value
    _report(
        problems, "bad_parentage_type",
        f"Okänd föräldratyp '{value}' i _SLK_PLINK; PEDI används.",
        type_node if type_node is not None else node,
    )
    return None


def read_plinks(
    famc: Optional[GedcomLine],
    known_xrefs: Optional[Collection[str]] = None,
    problems: Optional[list[SlkProblem]] = None,
) -> list[PlinkData]:
    """Read the ``_SLK_PLINK`` children of a ``FAMC`` line in order. Total."""
    links: list[PlinkData] = []
    for entry in _kids(famc, "_SLK_PLINK"):
        raw = _text(entry).strip()
        parent: Optional[str] = None
        if raw:
            parent = _pointer(raw, known_xrefs)
            if parent is None:
                _report(
                    problems, "unknown_parent",
                    f"_SLK_PLINK pekar på '{raw}' som inte är en person i filen; "
                    "länken saknar förälder.",
                    entry,
                )
        links.append(PlinkData(parent, read_parentage_type(entry, problems)))
    return links


_NAME_TYPES = {
    "birth": "birth",
    "maiden": "birth",
    "married": "married",
    "aka": "alias",
    "adopted": "adopted",
    "other": "other",
}


def read_name_type(
    name: Optional[GedcomLine],
    problems: Optional[list[SlkProblem]] = None,
) -> Optional[str]:
    """Map the ``TYPE`` of a ``NAME`` line to a Name type (Requirement 3).

    ``None`` when the NAME has no (or an empty) TYPE. Any TYPE that is not
    listed maps to ``other`` without a problem. *problems* is unused and only
    there for a uniform signature.
    """
    type_node = _first(name, "TYPE", None)
    if type_node is None:
        return None
    value = _text(type_node).strip().lower()
    if not value:
        return None
    return _NAME_TYPES.get(value, "other")


# ---------------------------------------------------------------------------
# Sources and repositories
# ---------------------------------------------------------------------------

_KNOWN_REFERENCE_KEYS = frozenset().union(*_STRUCTURED_REFERENCE_FIELDS.values())


@dataclass
class SourceExtras:
    """Values of the ``_SLK_`` tags of a SOUR record; ``None`` when unusable."""

    source_type: Optional[str] = None
    provider: Optional[str] = None
    leverantor_name: Optional[str] = None
    kalltyp_name: Optional[str] = None
    reference_fields: Optional[dict[str, Optional[str | int]]] = None


def _nonempty(
    node: Optional[GedcomLine],
    tag: str,
    problems: Optional[list[SlkProblem]],
) -> Optional[str]:
    child = _first(node, tag, problems)
    text = _text(child).strip() if child is not None else ""
    return text or None


def _parse_field(
    line: GedcomLine,
    problems: Optional[list[SlkProblem]],
) -> Optional[tuple[str, Optional[str | int]]]:
    parts = _text(line).strip().split(None, 1)
    if len(parts) != 2 or parts[0] not in _KNOWN_REFERENCE_KEYS:
        _report(
            problems, "bad_field",
            f"Ogiltigt eller okänt referensfält '{_text(line)}'; fältet hoppas över.",
            line,
        )
        return None
    try:
        value = json.loads(parts[1])
    except (ValueError, RecursionError):
        value = _BAD
    if value is not _BAD and (
        value is None
        or isinstance(value, str)
        or (isinstance(value, int) and not isinstance(value, bool))
    ):
        return parts[0], value
    _report(
        problems, "bad_field_value",
        f"Ogiltigt värde för referensfältet '{parts[0]}'; fältet hoppas över.",
        line,
    )
    return None


_BAD = object()


def read_source_fields(
    sour: Optional[GedcomLine],
    problems: Optional[list[SlkProblem]] = None,
) -> SourceExtras:
    """Read the ``_SLK_`` tags of a level-0 SOUR record. Total."""
    extras = SourceExtras()

    stype = _nonempty(sour, "_SLK_STYPE", problems)
    if stype is not None:
        if stype in _VALID_SOURCE_TYPES:
            extras.source_type = stype
        else:
            _report(
                problems, "bad_source_type",
                f"Okänd källtyp '{stype}'; källtypen avgörs av nyckelord.",
                _first(sour, "_SLK_STYPE", None),
            )

    extras.provider = _nonempty(sour, "_SLK_PROV", problems)
    extras.leverantor_name = _nonempty(sour, "_SLK_LEV", problems)
    extras.kalltyp_name = _nonempty(sour, "_SLK_KTYP", problems)

    sref = _first(sour, "_SLK_SREF", problems)
    if sref is not None:
        fields: dict[str, Optional[str | int]] = {}
        for line in _kids(sref, "_SLK_FLD"):
            parsed = _parse_field(line, problems)
            if parsed is None:
                continue
            key, value = parsed
            if key in fields:
                _report(
                    problems, "duplicate_field",
                    f"Referensfältet '{key}' förekommer flera gånger; första "
                    "värdet används.",
                    line,
                )
                continue
            fields[key] = value
        extras.reference_fields = fields or None
    return extras


@dataclass
class RepositoryData:
    """``_SLK_`` values of a level-0 REPO record."""

    type: str = ""
    external_ids: list[str] = field(default_factory=list)


@dataclass
class RepositoryRefData:
    """``_SLK_`` values of a ``1 REPO`` reference below a SOUR record."""

    source_type: str = ""
    image_number: Optional[int] = None
    page_number: Optional[int] = None
    media_name: str = ""


_NUMBER_RE = re.compile(r"^[0-9]+$")


def read_repository_record(
    node: Optional[GedcomLine],
    problems: Optional[list[SlkProblem]] = None,
) -> RepositoryData:
    """Read ``_SLK_RTYPE`` and ``_SLK_XID`` of a level-0 REPO record. Total."""
    data = RepositoryData()
    rtype = _nonempty(node, "_SLK_RTYPE", problems)
    data.type = rtype or ""
    data.external_ids = [
        _text(x).strip() for x in _kids(node, "_SLK_XID") if _text(x).strip()
    ]
    return data


def _read_count(
    node: Optional[GedcomLine],
    tag: str,
    problems: Optional[list[SlkProblem]],
) -> Optional[int]:
    child = _first(node, tag, problems)
    raw = _text(child).strip() if child is not None else ""
    if not raw:
        return None
    if _NUMBER_RE.match(raw):
        return int(raw)
    _report(
        problems, "bad_number",
        f"Ogiltigt heltal '{raw}' i {tag}; värdet lämnas tomt.",
        child,
    )
    return None


def read_repository_ref(
    node: Optional[GedcomLine],
    problems: Optional[list[SlkProblem]] = None,
) -> RepositoryRefData:
    """Read the ``_SLK_R*`` tags of a ``1 REPO`` reference. Total."""
    return RepositoryRefData(
        source_type=_nonempty(node, "_SLK_RSTYPE", problems) or "",
        image_number=_read_count(node, "_SLK_RIMG", problems),
        page_number=_read_count(node, "_SLK_RPAGE", problems),
        media_name=_nonempty(node, "_SLK_RMEDNAME", problems) or "",
    )


def read_repository(
    node: Optional[GedcomLine],
    problems: Optional[list[SlkProblem]] = None,
) -> RepositoryData | RepositoryRefData:
    """Read a REPO line: a record (has an xref) or a reference below a SOUR."""
    if getattr(node, "xref_id", None):
        return read_repository_record(node, problems)
    return read_repository_ref(node, problems)


# ---------------------------------------------------------------------------
# Legacy prose (files without the SLK_Marker only)
# ---------------------------------------------------------------------------

_START_PREFIX = "Tidigast början:"
_END_PREFIX = "Senast slut:"
_ROLE_PREFIX = "Roll:"
_ROLE_MAX = 100


@dataclass
class LegacyObservation:
    """A period read from ``NOTE Observation:`` below one ``SOUR`` of a RESI."""

    source_xref: str
    observed_from: str
    observed_to: str


@dataclass
class LegacyResidence:
    """What the legacy prose lines of a RESI record say.

    ``interpreted`` lists the NOTE lines that were read as structured data.
    Every other NOTE line stays ordinary note text.
    """

    start_earliest: Optional[str] = None
    end_latest: Optional[str] = None
    role_in_household: Optional[str] = None
    observations: list[LegacyObservation] = field(default_factory=list)
    interpreted: list[GedcomLine] = field(default_factory=list)


def _after_prefix(text: str, prefix: str) -> Optional[str]:
    """The value after ``<prefix> `` (one space), or ``None`` without the prefix.

    Case-sensitive and anchored at the start of the line. A line that is the
    bare prefix gives ``""``.
    """
    if text == prefix:
        return ""
    if text.startswith(prefix + " "):
        return text[len(prefix) + 1:]
    return None


def read_legacy_prose(
    resi: Optional[GedcomLine],
    problems: Optional[list[SlkProblem]] = None,
) -> LegacyResidence:
    """Read the exact legacy prose formats of a RESI record (Requirement 7.7).

    Accepted, and nothing else: ``NOTE Tidigast början: <ISO date>``,
    ``NOTE Senast slut: <ISO date>`` and ``NOTE Roll: <text>`` below RESI, and
    ``NOTE Observation: YYYY`` or ``YYYY-YYYY`` below a ``SOUR`` of the RESI.
    A line with a matching prefix and an invalid value gives a problem and
    stays note text. Only the caller decides that the file has no SLK_Marker.
    Total.
    """
    result = LegacyResidence()

    for note in _kids(resi, "NOTE"):
        text = _text(note)
        for prefix, attr in (
            (_START_PREFIX, "start_earliest"),
            (_END_PREFIX, "end_latest"),
        ):
            value = _after_prefix(text, prefix)
            if value is None:
                continue
            if _valid_date(value):
                if getattr(result, attr) is None:
                    setattr(result, attr, value)
                    result.interpreted.append(note)
                else:
                    _report(
                        problems, "duplicate_prose",
                        f"'{prefix}' förekommer flera gånger; första värdet "
                        "används.",
                        note,
                    )
            else:
                _report(
                    problems, "bad_prose_date",
                    f"Ogiltigt datum '{value}' efter '{prefix}'; raden behandlas "
                    "som vanlig anteckning.",
                    note,
                )
            break
        else:
            role = _after_prefix(text, _ROLE_PREFIX)
            if role is None or not role.strip():
                continue
            if role != role.strip() or len(role) > _ROLE_MAX:
                _report(
                    problems, "bad_prose_role",
                    f"Ogiltig roll efter '{_ROLE_PREFIX}'; raden behandlas som "
                    "vanlig anteckning.",
                    note,
                )
            elif result.role_in_household is None:
                result.role_in_household = role
                result.interpreted.append(note)
            else:
                _report(
                    problems, "duplicate_prose",
                    f"'{_ROLE_PREFIX}' förekommer flera gånger; första värdet "
                    "används.",
                    note,
                )

    for sour in _kids(resi, "SOUR"):
        for note in _kids(sour, "NOTE"):
            value = _after_prefix(_text(note), _OBSERVATION_PREFIX)
            if not value:
                # Not an observation line, or the bare "Observation:" that the
                # exporter writes when there is no period.
                continue
            period = _parse_observation_period(value)
            if period is None:
                _report(
                    problems, "bad_prose_period",
                    f"Ogiltigt observationsår '{value}' efter "
                    f"'{_OBSERVATION_PREFIX}'; raden behandlas som vanlig "
                    "anteckning.",
                    note,
                )
                continue
            result.observations.append(
                LegacyObservation(_text(sour).strip(), period[0], period[1])
            )
            result.interpreted.append(note)
            break
    return result
