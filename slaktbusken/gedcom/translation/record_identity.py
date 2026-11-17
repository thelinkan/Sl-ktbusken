"""Record identity matcher for GEDCOM events and residences.

Pure module: no Qt, no file I/O, no mutation of the objects it is given.

``match_records`` decides, for the records of one owner, which existing objects
an incoming GEDCOM record stands for. The claim unit is the *Origin_Group*:
all pool objects of one owner that carry an equal ``origin_key``. Objects
without origin (legacy objects) are never grouped and are claimed one to one,
only on exact content. Nothing is claimed by tag and index, by event type and
place, or by residence date and place; ``index`` is never read.

Design: ``.kiro/specs/data-integrity-0-3-0/design.md``, Component 7.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Mapping, Optional, Sequence, Union

from slaktbusken.gedcom.parser import GedcomLine
from slaktbusken.model.event import Event
from slaktbusken.model.record_origin import RecordOrigin, origin_key
from slaktbusken.model.residence import ResidenceFact

__all__ = [
    "IncomingRecord",
    "PoolEntry",
    "OriginGroup",
    "Outcome",
    "MatchResult",
    "origin_key",
    "record_hash",
    "event_fingerprint",
    "residence_fingerprint",
    "tag_key_of",
    "build_origin_groups",
    "match_records",
]

Obj = Union[Event, ResidenceFact]

# ---------------------------------------------------------------------------
# Record hash
# ---------------------------------------------------------------------------

_EXCLUDED_TAGS = frozenset({"CHAN", "_UPD", "_CRE", "_UID"})
_POINTER_RE = re.compile(r"^@[^@\s]+@$")
_POINTER_TOKEN = "@PTR@"
_WS_RE = re.compile(r"\s+")
_PROFILES = frozenset({"legacy", "slk1"})
_SLK1_SOUR_DROPPED = frozenset({"QUAY", "PAGE", "DATA", "OBJE"})


def _canonical_value(tag: str, value: Optional[str], source_ids: Mapping[str, str]) -> str:
    text = _WS_RE.sub(" ", value or "").strip()
    if _POINTER_RE.match(text):
        if tag == "SOUR":
            return source_ids.get(text, text)
        return _POINTER_TOKEN
    return text


def _skip_child_slk1(parent_tag: str, child: GedcomLine) -> bool:
    """Nodes that Hash_Profile ``slk1`` removes before hashing."""
    tag = child.tag.upper()
    if tag.startswith("_SLK_"):
        return True
    if tag == "CAUS":
        # Older exporters never wrote the cause; skipping it keeps the hash of
        # an event stable when a later export adds ``CAUS``.
        return True
    if parent_tag == "SOUR":
        if tag in _SLK1_SOUR_DROPPED:
            return True
        if tag == "NOTE":
            raw = child.raw_value if child.raw_value is not None else child.value
            text = _WS_RE.sub(" ", raw or "").strip()
            return not text.startswith("Observation:")
    return False


def _canonical_lines(
    node: GedcomLine,
    depth: int,
    source_ids: Mapping[str, str],
    out: list[str],
    profile: str = "legacy",
) -> None:
    tag = node.tag.upper()
    # raw_value is the value as written in the file (``@@`` not unescaped), so
    # that the parser's unescape does not change stored hashes.
    raw = node.raw_value if node.raw_value is not None else node.value
    value = _canonical_value(tag, raw, source_ids)
    out.append(f"{depth} {tag} {value}".rstrip())
    kept = [c for c in node.children if c.tag.upper() not in _EXCLUDED_TAGS]
    if profile == "slk1":
        kept = [c for c in kept if not _skip_child_slk1(tag, c)]
    # sorted() is stable: siblings with equal tag keep their file order.
    for child in sorted(kept, key=lambda c: c.tag.upper()):
        _canonical_lines(child, depth + 1, source_ids, out, profile)


def record_hash(
    record: GedcomLine, source_ids: Mapping[str, str], profile: str = "legacy"
) -> str:
    """SHA-256 (hex) of the canonical form of an event or ``RESI`` record.

    The record itself is written at depth 1 (``1 RESI``), whatever its level.
    ``profile`` is the Hash_Profile: ``"legacy"`` (the original canonical form)
    or ``"slk1"`` (files with the ``_SLK_VERS`` marker; additionally drops
    ``_SLK_`` nodes, ``CAUS`` children and the ``QUAY``, ``PAGE``, ``DATA``, ``OBJE`` and
    non-``Observation:`` ``NOTE`` children of ``SOUR`` lines).
    """
    if profile not in _PROFILES:
        raise ValueError(f"unknown hash profile: {profile!r}")
    lines: list[str] = []
    _canonical_lines(record, 1, source_ids, lines, profile)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Fingerprints and tag keys
# ---------------------------------------------------------------------------


def _digest(parts: object) -> str:
    text = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def event_fingerprint(event: Event) -> str:
    """Content fingerprint of an event (None and empty text compare equal)."""
    date = event.date
    return _digest(
        [
            event.type,
            event.custom_type_name or "",
            date.qualifier if date else "",
            date.value if date else "",
            (date.value_to or "") if date else "",
            date.calendar if date else "",
            (date.original_text or "") if date else "",
            event.place.place_id if event.place else "",
            sorted([p.person_id, p.role] for p in event.participants),
            event.cause_of_death or "",
        ]
    )


def residence_fingerprint(fact: ResidenceFact, ignore_links: bool = False) -> str:
    """Content fingerprint of a residence. ``Endpoint.precision`` is excluded.

    With ``ignore_links`` the endpoint event links (``Endpoint.event_id``) are
    left out, as they resolve only after the families exist.
    """

    def endpoint(ep) -> list:
        link = "" if ignore_links else (ep.event_id or "")
        return [ep.earliest or "", ep.latest or "", link, ep.note or ""]

    return _digest(
        [
            fact.person_id,
            fact.place_id or "",
            endpoint(fact.start),
            endpoint(fact.end),
            fact.role_in_household or "",
            fact.notes or "",
            [
                [
                    o.source_ref.source_id,
                    o.source_ref.quality,
                    o.observed_from or "",
                    o.observed_to or "",
                    o.page_note or "",
                ]
                for o in fact.observations
            ],
        ]
    )


# Mirrors importer._INDI_EVENT_TAGS / _FAM_EVENT_TAGS (inverse). Kept here so
# this pure module does not import the importer. CHR is an alias of BAPM.
_TYPE_TO_TAG: dict[str, str] = {
    "birth": "BIRT",
    "death": "DEAT",
    "burial": "BURI",
    "baptism": "BAPM",
    "emigration": "EMIG",
    "immigration": "IMMI",
    "census": "CENS",
    "retirement": "RETI",
    "graduation": "GRAD",
    "cremation": "CREM",
    "confirmation": "CONF",
    "will": "WILL",
    "adoption": "ADOP",
    "blessing": "BLES",
    "first_communion": "FCOM",
    "marriage": "MARR",
    "divorce": "DIV",
    "engagement": "ENGA",
    "divorce_filed": "DIVF",
}
_TYPE_TO_EVEN_TYPE: dict[str, str] = {"flytt": "flytt", "foster_home": "fosterhem"}


def tag_key_of(event: Event) -> str:
    """The tag key of *event*: ``origin.tag_key``, or derived from the type."""
    if event.origin is not None:
        return event.origin.tag_key
    if event.type in _TYPE_TO_EVEN_TYPE:
        return "EVEN:" + _TYPE_TO_EVEN_TYPE[event.type]
    if event.type in _TYPE_TO_TAG:
        return _TYPE_TO_TAG[event.type]
    name = (event.custom_type_name or "").strip().lower()
    return f"EVEN:{name}" if name else "EVEN"


def _obj_tag_key(obj: Obj) -> str:
    return "RESI" if isinstance(obj, ResidenceFact) else tag_key_of(obj)


def _obj_fingerprint(obj: Obj) -> str:
    if isinstance(obj, ResidenceFact):
        return residence_fingerprint(obj)
    return event_fingerprint(obj)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IncomingRecord:
    kind: str                       # "event" | "residence"
    owner_kind: str                 # "INDI" | "FAM"
    owner_id: str
    owner_xref: str                 # informational only
    tag_key: str
    index: int                      # informational only, never read
    record_hash: str
    uid: Optional[str]
    fingerprint: Callable[[], str]  # lazy; evaluated only in step 3


@dataclass(frozen=True)
class PoolEntry:
    obj: Obj
    origin: RecordOrigin


@dataclass(frozen=True)
class OriginGroup:
    key: tuple
    members: tuple


class Outcome(Enum):
    UNCHANGED = "unchanged"
    CHANGED_UID = "changed_uid"
    LEGACY_CLAIMED = "legacy_claimed"
    NEW = "new"
    NEW_AMBIGUOUS = "new_ambiguous"


@dataclass
class MatchResult:
    incoming: IncomingRecord
    members: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    instance: Optional[int] = None
    outcome: Outcome = Outcome.NEW


# ---------------------------------------------------------------------------
# Matcher
# ---------------------------------------------------------------------------


def build_origin_groups(pool: Sequence[PoolEntry]) -> list[OriginGroup]:
    """Group pool entries by Origin_Key (first-seen order, members once each)."""
    members: dict[tuple, list[Obj]] = {}
    for entry in pool:
        bucket = members.setdefault(origin_key(entry.origin), [])
        if not any(m is entry.obj for m in bucket):
            bucket.append(entry.obj)
    return [OriginGroup(key=k, members=tuple(v)) for k, v in members.items()]


def _owner_of(key: tuple) -> tuple:
    return (key[0], key[1])


def match_records(
    incoming: Sequence[IncomingRecord],
    pool: Sequence[PoolEntry],
    legacy_pool: Sequence[Obj],
    foreign: Sequence[Obj],
) -> list[MatchResult]:
    """Pair incoming records with existing objects. Never alters an object.

    Returns one :class:`MatchResult` per incoming record, in the order given.
    """
    # Step 0: groups.
    groups = build_origin_groups(pool)
    claimed_groups: set[int] = set()  # indexes into ``groups``
    results: list[Optional[MatchResult]] = [None] * len(incoming)

    def owner_of_rec(rec: IncomingRecord) -> tuple:
        return (rec.owner_kind, rec.owner_id)

    # Step 1: uid.
    for i, rec in enumerate(incoming):
        if not rec.uid:
            continue
        hits = [
            gi
            for gi, g in enumerate(groups)
            if gi not in claimed_groups
            and _owner_of(g.key) == owner_of_rec(rec)
            and g.key[5] == rec.uid
        ]
        if len(hits) != 1:
            continue
        gi = hits[0]
        claimed_groups.add(gi)
        same = groups[gi].key[3] == rec.record_hash
        results[i] = MatchResult(
            incoming=rec,
            members=list(groups[gi].members),
            outcome=Outcome.UNCHANGED if same else Outcome.CHANGED_UID,
        )

    # Step 2: owner, tag key and hash; groups by instance, records in file order.
    buckets: dict[tuple, list[int]] = {}
    for gi, g in enumerate(groups):
        if gi not in claimed_groups:
            k = (_owner_of(g.key), g.key[2], g.key[3])
            buckets.setdefault(k, []).append(gi)
    for k in buckets:
        buckets[k].sort(key=lambda gi: (groups[gi].key[4], groups[gi].key))
    for i, rec in enumerate(incoming):
        if results[i] is not None:
            continue
        bucket = buckets.get((owner_of_rec(rec), rec.tag_key, rec.record_hash))
        if not bucket:
            continue
        gi = bucket.pop(0)
        claimed_groups.add(gi)
        results[i] = MatchResult(
            incoming=rec, members=list(groups[gi].members), outcome=Outcome.UNCHANGED
        )

    # Step 3: legacy fingerprint, only while an unclaimed legacy object exists.
    legacy: list[Obj] = []
    for obj in legacy_pool:
        if not any(obj is o for o in legacy):
            legacy.append(obj)
    legacy_claimed: list[bool] = [False] * len(legacy)
    legacy_fp: dict[int, str] = {}
    for i, rec in enumerate(incoming):
        if results[i] is not None:
            continue
        if all(legacy_claimed):
            break
        want = rec.fingerprint()
        for li, obj in enumerate(legacy):
            if legacy_claimed[li]:
                continue
            fp = legacy_fp.get(li)
            if fp is None:
                fp = legacy_fp[li] = _obj_fingerprint(obj)
            if fp == want:
                legacy_claimed[li] = True
                results[i] = MatchResult(
                    incoming=rec, members=[obj], outcome=Outcome.LEGACY_CLAIMED
                )
                break

    # Step 4 and instance assignment, in file order.
    used: dict[tuple, set[int]] = {}
    for g in groups:
        k = (_owner_of(g.key), g.key[2], g.key[3])
        used.setdefault(k, set()).add(g.key[4])
    # Pool origins of the same (owner, tag key, hash) count even when the
    # group is keyed by a different uid; groups cover every pool origin, and
    # origin_key keeps the instance, so ``used`` above is complete.

    def next_instance(rec: IncomingRecord) -> int:
        taken = used.setdefault((owner_of_rec(rec), rec.tag_key, rec.record_hash), set())
        n = 0
        while n in taken:
            n += 1
        taken.add(n)
        return n

    for i, rec in enumerate(incoming):
        res = results[i]
        if res is not None and res.outcome in (Outcome.UNCHANGED, Outcome.CHANGED_UID):
            continue
        if res is None:
            res = results[i] = MatchResult(incoming=rec, outcome=Outcome.NEW)
            cands: list[Obj] = []
            seen: set[int] = set()

            def add(obj: Obj) -> None:
                if id(obj) not in seen:
                    seen.add(id(obj))
                    cands.append(obj)

            owner = owner_of_rec(rec)
            for gi, g in enumerate(groups):
                if gi not in claimed_groups and _owner_of(g.key) == owner and g.key[2] == rec.tag_key:
                    for m in g.members:
                        add(m)
            for li, obj in enumerate(legacy):
                if not legacy_claimed[li] and _obj_tag_key(obj) == rec.tag_key:
                    add(obj)
            for obj in foreign:
                if _obj_tag_key(obj) == rec.tag_key:
                    add(obj)
            if cands:
                res.candidates = cands
                res.outcome = Outcome.NEW_AMBIGUOUS
        res.instance = next_instance(rec)

    return [r for r in results if r is not None]
