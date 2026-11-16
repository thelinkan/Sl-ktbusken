"""Strategies and helpers for the record identity properties (Properties 14, 15).

Two groups:

* GEDCOM records: ``event_records`` and ``resi_records`` build ``GedcomLine``
  trees with their ``source_ids`` map; the transformation helpers apply the
  harmless differences (whitespace, change-tracking subtrees, sibling-group
  order, source renumbering) and the meaningful differences (tag, date, place,
  note, resolved source id, order of repeated siblings) of Property 15.
* Matcher scenarios: ``matcher_scenarios`` describes pools, legacy and foreign
  objects and incoming records as plain data. ``MatcherScenario.build`` turns
  it into fresh objects, so one scenario can be run several times.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Callable, Optional

from hypothesis import strategies as st

from slaktbusken.gedcom.parser import GedcomLine
from slaktbusken.gedcom.translation.record_identity import (
    IncomingRecord,
    PoolEntry,
    event_fingerprint,
    residence_fingerprint,
)
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.record_origin import RecordOrigin
from slaktbusken.model.residence import Endpoint, ResidenceFact

# ---------------------------------------------------------------------------
# GEDCOM records
# ---------------------------------------------------------------------------

SOURCE_XREFS = ("@S1@", "@S2@", "@S3@", "@S4@")
DEFAULT_SOURCE_IDS = {x: f"src-{n:04d}" for n, x in enumerate(SOURCE_XREFS, start=1)}
EVENT_TAGS = ("BIRT", "DEAT", "BURI", "BAPM", "MARR", "EVEN")
EXCLUDED_TAGS = ("CHAN", "_UPD", "_CRE", "_UID")

_WORDS = ("Anna", "Johan", "Stockholm", "Uppsala", "Malmö", "hos", "föräldrarna", "Sverige", "1850")
_DATES = ("12 MAR 1850", "1880", "FROM 1870 TO 1880", "BET 1850 AND 1860", "ABT 1700", "BEF 1900")

texts = st.lists(st.sampled_from(_WORDS), min_size=1, max_size=3).map(" ".join)
dates = st.sampled_from(_DATES)


def node(tag: str, value: Optional[str] = None, children=()) -> GedcomLine:
    """A GedcomLine with the given children (levels are fixed by ``fix_levels``)."""
    return GedcomLine(
        level=0, tag=tag, value=value, xref_id=None, line_number=0, children=list(children)
    )


def fix_levels(record: GedcomLine, level: int = 1) -> GedcomLine:
    """Set ``level`` of the record and every descendant, in place."""
    record.level = level
    for child in record.children:
        fix_levels(child, level + 1)
    return record


@st.composite
def _change_tracking(draw) -> list[GedcomLine]:
    nodes: list[GedcomLine] = []
    if draw(st.booleans()):
        nodes.append(node("CHAN", None, [node("DATE", draw(dates))]))
    if draw(st.booleans()):
        nodes.append(node("_UPD", draw(dates)))
    if draw(st.booleans()):
        nodes.append(node("_CRE", draw(dates)))
    if draw(st.booleans()):
        nodes.append(node("_UID", draw(st.sampled_from(["U-1", "U-2", "U-3"]))))
    return nodes


@st.composite
def _sour_nodes(draw, min_size: int = 0) -> list[GedcomLine]:
    xrefs = draw(
        st.lists(st.sampled_from(SOURCE_XREFS), min_size=min_size, max_size=3, unique=True)
    )
    out: list[GedcomLine] = []
    for xref in xrefs:
        children: list[GedcomLine] = []
        if draw(st.booleans()):
            children.append(node("PAGE", draw(texts)))
        if draw(st.booleans()):
            children.append(node("DATA", None, [node("TEXT", draw(texts))]))
        if draw(st.booleans()):
            children.append(node("NOTE", draw(texts)))
        out.append(node("SOUR", xref, children))
    return out


@st.composite
def _body(draw, min_notes: int, min_sources: int) -> list[GedcomLine]:
    children: list[GedcomLine] = []
    if draw(st.booleans()):
        children.append(node("DATE", draw(dates)))
    if draw(st.booleans()):
        plac_children: list[GedcomLine] = []
        if draw(st.booleans()):
            plac_children.append(
                node("MAP", None, [node("LATI", "N59.3"), node("LONG", "E18.0")])
            )
        children.append(node("PLAC", draw(texts), plac_children))
    for text in draw(st.lists(texts, min_size=min_notes, max_size=3, unique=True)):
        children.append(node("NOTE", text))
    children.extend(draw(_sour_nodes(min_size=min_sources)))
    children.extend(draw(_change_tracking()))
    return draw(st.permutations(children))


@st.composite
def event_records(draw, min_notes: int = 0, min_sources: int = 0) -> tuple[GedcomLine, dict[str, str]]:
    """A level-1 event record (``BIRT``, ``EVEN`` with TYPE and so on)."""
    tag = draw(st.sampled_from(EVENT_TAGS))
    children = list(draw(_body(min_notes, min_sources)))
    if tag == "EVEN":
        children.append(node("TYPE", draw(st.sampled_from(["Flytt", "Fosterhem", "Yrke"]))))
    if draw(st.booleans()):
        children.append(node("FAMC", draw(st.sampled_from(["@F1@", "@F2@"]))))
    return fix_levels(node(tag, None, children)), dict(DEFAULT_SOURCE_IDS)


@st.composite
def resi_records(draw, min_notes: int = 0, min_sources: int = 0) -> tuple[GedcomLine, dict[str, str]]:
    """A level-1 ``RESI`` record."""
    children = list(draw(_body(min_notes, min_sources)))
    if draw(st.booleans()):
        children.append(node("_ADPL", draw(texts)))
    return fix_levels(node("RESI", None, children)), dict(DEFAULT_SOURCE_IDS)


def gedcom_records(min_notes: int = 0, min_sources: int = 0):
    """Event records and ``RESI`` records (Properties 14 and 15 use both)."""
    return st.one_of(
        event_records(min_notes=min_notes, min_sources=min_sources),
        resi_records(min_notes=min_notes, min_sources=min_sources),
    )


# --- harmless differences ---------------------------------------------------


def _walk(record: GedcomLine):
    yield record
    for child in record.children:
        yield from _walk(child)


def add_whitespace_noise(record: GedcomLine, rnd: random.Random) -> GedcomLine:
    """Pad and widen the whitespace of every value (copy)."""
    out = copy.deepcopy(record)
    for n in _walk(out):
        if n.value is None:
            continue
        parts = n.value.split(" ")
        n.value = (
            " " * rnd.randint(0, 2)
            + "".join(p + " " * rnd.randint(1, 3) for p in parts[:-1])
            + parts[-1]
            + " " * rnd.randint(0, 2)
        )
        if rnd.random() < 0.3:
            n.value = n.value.replace(" ", "\t", 1)
    return out


def change_tracking_noise(record: GedcomLine, rnd: random.Random) -> GedcomLine:
    """Add, remove and change CHAN, _UPD, _CRE and _UID subtrees at any depth (copy)."""
    out = copy.deepcopy(record)
    for n in list(_walk(out)):
        kept: list[GedcomLine] = []
        for child in n.children:
            if child.tag in EXCLUDED_TAGS:
                if rnd.random() < 0.4:
                    continue
                child.value = (child.value or "") + rnd.choice(["", "x", "9"])
                child.children.append(node("NOTE", "changed"))
            kept.append(child)
        for tag in EXCLUDED_TAGS:
            if rnd.random() < 0.4:
                kept.insert(
                    rnd.randint(0, len(kept)),
                    node(tag, rnd.choice(_DATES), [node("DATE", "1 JAN 2020")]),
                )
        n.children = kept
    return fix_levels(out, record.level or 1)


def reorder_distinct_tags(record: GedcomLine, rnd: random.Random) -> GedcomLine:
    """Reorder the sibling groups with different tags at any depth (copy).

    Siblings with the same tag keep their relative order.
    """
    out = copy.deepcopy(record)
    for n in _walk(out):
        groups: dict[str, list[GedcomLine]] = {}
        for child in n.children:
            groups.setdefault(child.tag.upper(), []).append(child)
        order = list(groups)
        rnd.shuffle(order)
        n.children = [c for tag in order for c in groups[tag]]
    return out


def renumber_sources(
    record: GedcomLine, source_ids: dict[str, str], rnd: random.Random
) -> tuple[GedcomLine, dict[str, str]]:
    """Give the source xrefs new numbers; resolved ids stay equal (copy)."""
    out = copy.deepcopy(record)
    new_numbers = list(range(11, 11 + len(SOURCE_XREFS)))
    rnd.shuffle(new_numbers)
    rename = {x: f"@S{n}@" for x, n in zip(SOURCE_XREFS, new_numbers)}
    for n in _walk(out):
        if n.tag == "SOUR" and n.value in rename:
            n.value = rename[n.value]
    return out, {rename[x]: i for x, i in source_ids.items()}


# --- meaningful differences -------------------------------------------------


def _first_child(record: GedcomLine, tag: str) -> Optional[GedcomLine]:
    return next((c for c in record.children if c.tag == tag), None)


def change_tag(record: GedcomLine) -> GedcomLine:
    out = copy.deepcopy(record)
    out.tag = "DEAT" if out.tag != "DEAT" else "BIRT"
    return out


def _change_value(record: GedcomLine, tag: str, fallback: str) -> GedcomLine:
    out = copy.deepcopy(record)
    target = _first_child(out, tag)
    if target is None:
        out.children.append(node(tag, fallback))
    else:
        target.value = (target.value or "") + " 9"
    return fix_levels(out, record.level or 1)


def change_date(record: GedcomLine) -> GedcomLine:
    return _change_value(record, "DATE", "1999")


def change_place(record: GedcomLine) -> GedcomLine:
    return _change_value(record, "PLAC", "Nyköping")


def change_note(record: GedcomLine) -> GedcomLine:
    return _change_value(record, "NOTE", "En ny anteckning")


def swap_first_two(record: GedcomLine, tag: str) -> GedcomLine:
    """Swap the first two children with *tag* (they must differ)."""
    out = copy.deepcopy(record)
    idx = [i for i, c in enumerate(out.children) if c.tag == tag]
    assert len(idx) >= 2
    i, j = idx[0], idx[1]
    out.children[i], out.children[j] = out.children[j], out.children[i]
    return out


def first_source_xref(record: GedcomLine) -> Optional[str]:
    sour = _first_child(record, "SOUR")
    return sour.value if sour is not None else None


# ---------------------------------------------------------------------------
# Matcher scenarios
# ---------------------------------------------------------------------------

OWNER_ID = "P1"
OTHER_OWNER_ID = "P2"
HASHES = ("hash-a", "hash-b", "hash-c")
UIDS = (None, "uid-1", "uid-2")
N_CONTENTS = 3


@dataclass(frozen=True)
class OriginSpec:
    tag: str
    hash_idx: int
    uid: Optional[str]
    instance: int
    index: int = 0


@dataclass(frozen=True)
class ObjectSpec:
    role: str                              # "pool" | "legacy" | "foreign"
    origins: tuple[OriginSpec, ...] = ()   # pool and foreign
    content: int = 0                       # legacy content
    tag: str = ""                          # legacy and foreign tag key
    twice: bool = False                    # pool entry listed twice


@dataclass(frozen=True)
class IncomingSpec:
    tag: str
    hash_idx: int
    uid: Optional[str]
    index: int


@dataclass
class Built:
    incoming: list
    pool: list
    legacy: list
    foreign: list
    fingerprint_calls: list = field(default_factory=list)


_EVENT_TYPE_OF_TAG = {"BIRT": "birth", "DEAT": "death"}


def _content_of_hash(hash_idx: int) -> int:
    return hash_idx % N_CONTENTS


def make_object(kind: str, tag: str, content: int, origins: tuple[OriginSpec, ...],
                owner_id: str, serial: int):
    """A fresh event or residence with the given content and origins."""
    if kind == "residence":
        fact = ResidenceFact(
            id=f"r{serial}",
            person_id=OWNER_ID,
            place_id=f"pl{content}",
            start=Endpoint(earliest=f"18{content}0", latest=f"18{content}0"),
            end=Endpoint(),
            origins=[make_origin(kind, "INDI", owner_id, o) for o in origins],
        )
        return fact
    event = Event(
        id=f"e{serial}",
        type=_EVENT_TYPE_OF_TAG[tag],
        participants=[Participant(OWNER_ID, "subject")],
        date=DateValue(value=f"18{content}0", precision="year"),
        place=PlaceRef(place_id=f"pl{content}"),
    )
    if origins:
        event.origin = make_origin(kind, "INDI", owner_id, origins[0])
    return event


def make_origin(kind: str, owner_kind: str, owner_id: str, spec: OriginSpec) -> RecordOrigin:
    return RecordOrigin(
        owner_kind=owner_kind,
        owner_id=owner_id,
        owner_xref="@I1@",
        tag_key=spec.tag,
        index=spec.index,
        record_hash=HASHES[spec.hash_idx],
        uid=spec.uid,
        instance=spec.instance,
    )


@dataclass
class MatcherScenario:
    kind: str                           # "event" | "residence"
    objects: tuple[ObjectSpec, ...]
    incoming: tuple[IncomingSpec, ...]

    def build(
        self,
        pool_order: Optional[list[int]] = None,
        incoming_order: Optional[list[int]] = None,
    ) -> Built:
        built = Built([], [], [], [])
        serial = 0
        pool_entries: list[PoolEntry] = []
        # Objects with equal origins are separate objects carrying copies.
        for spec in self.objects:
            serial += 1
            if spec.role == "legacy":
                obj = make_object(self.kind, spec.tag, spec.content, (), OWNER_ID, serial)
                built.legacy.append(obj)
            elif spec.role == "foreign":
                obj = make_object(
                    self.kind, spec.tag, spec.content, spec.origins, OTHER_OWNER_ID, serial
                )
                built.foreign.append(obj)
            else:
                obj = make_object(
                    self.kind, spec.tag, spec.content, spec.origins, OWNER_ID, serial
                )
                origins = [obj.origin] if self.kind == "event" else list(obj.origins)
                for _ in range(2 if spec.twice else 1):
                    for o in origins:
                        pool_entries.append(PoolEntry(obj, o))
        if pool_order is not None:
            pool_entries = [pool_entries[i] for i in pool_order]
        built.pool = pool_entries

        order = incoming_order if incoming_order is not None else range(len(self.incoming))
        for i in order:
            spec = self.incoming[i]
            template = make_object(
                self.kind, spec.tag, _content_of_hash(spec.hash_idx), (), OWNER_ID, 0
            )
            fp = event_fingerprint if self.kind == "event" else residence_fingerprint

            def lazy(t=template, f=fp, calls=built.fingerprint_calls) -> str:
                calls.append(1)
                return f(t)

            built.incoming.append(
                IncomingRecord(
                    kind=self.kind,
                    owner_kind="INDI",
                    owner_id=OWNER_ID,
                    owner_xref="@I9@",
                    tag_key=spec.tag,
                    index=spec.index,
                    record_hash=HASHES[spec.hash_idx],
                    uid=spec.uid,
                    fingerprint=lazy,
                )
            )
        return built


@st.composite
def _origin_specs(draw, tag: str) -> OriginSpec:
    return OriginSpec(
        tag=tag,
        hash_idx=draw(st.integers(0, len(HASHES) - 1)),
        uid=draw(st.sampled_from(UIDS)),
        instance=draw(st.integers(0, 2)),
        index=draw(st.integers(0, 3)),
    )


@st.composite
def matcher_scenarios(draw, kind: Optional[str] = None, unique_uids: bool = False,
                      with_uids: bool = True) -> MatcherScenario:
    """Pools with several objects (one of them twice) carrying equal origins,
    residences with two origins, legacy objects and foreign objects."""
    kind = kind or draw(st.sampled_from(["event", "residence"]))
    tags = ("RESI",) if kind == "residence" else ("BIRT", "DEAT")
    tag_st = st.sampled_from(tags)

    # A small shared alphabet of origins makes equal origins common.
    alphabet = draw(st.lists(tag_st.flatmap(_origin_specs), min_size=1, max_size=4))
    origin_st = st.sampled_from(alphabet)

    objects: list[ObjectSpec] = []
    for _ in range(draw(st.integers(0, 6))):
        role = draw(st.sampled_from(["pool", "pool", "legacy", "foreign"]))
        tag = draw(tag_st)
        content = draw(st.integers(0, N_CONTENTS - 1))
        if role == "legacy":
            objects.append(ObjectSpec("legacy", (), content, tag))
            continue
        if kind == "event":
            first = draw(origin_st)
            origins = (first,)
            tag = first.tag
        else:
            n = draw(st.integers(1, 2))
            origins = tuple(draw(origin_st) for _ in range(n))
        objects.append(
            ObjectSpec(role, origins, content, tag, twice=draw(st.booleans()) if role == "pool" else False)
        )

    incoming: list[IncomingSpec] = []
    used_uids: set[str] = set()
    for _ in range(draw(st.integers(0, 6))):
        uid = draw(st.sampled_from(UIDS)) if with_uids else None
        if uid is not None and unique_uids:
            if uid in used_uids:
                uid = None
            else:
                used_uids.add(uid)
        incoming.append(
            IncomingSpec(
                tag=draw(tag_st),
                hash_idx=draw(st.integers(0, len(HASHES) - 1)),
                uid=uid,
                index=draw(st.integers(0, 3)),
            )
        )
    return MatcherScenario(kind, tuple(objects), tuple(incoming))
