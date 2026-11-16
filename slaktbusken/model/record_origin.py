"""Durable GEDCOM record identity for events and residences.

A :class:`RecordOrigin` states which GEDCOM record an Event or ResidenceFact
was created from. Pure module: no Qt, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class RecordOrigin:
    """The GEDCOM record an object was imported from."""

    owner_kind: str          # "INDI" | "FAM"
    owner_id: str            # app person or family id resolved at import; used for matching
    owner_xref: str          # "@I12@" at import time; informational, never used for matching
    tag_key: str             # "BIRT", "EVEN:flytt", "RESI"
    index: int               # occurrence among records with this tag_key; informational
    record_hash: str         # sha256 hex of the canonical record
    uid: Optional[str] = None
    instance: int = 0        # import-assigned; copied by a split, kept by a merge


def origin_key(origin: RecordOrigin) -> tuple:
    """The Origin_Key of *origin*.

    ``(owner_kind, owner_id, tag_key, record_hash, instance, uid or "")``.
    ``owner_xref`` and ``index`` are informational and not part of the key.
    """
    return (
        origin.owner_kind,
        origin.owner_id,
        origin.tag_key,
        origin.record_hash,
        origin.instance,
        origin.uid or "",
    )
