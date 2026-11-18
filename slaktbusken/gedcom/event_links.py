"""Event_Link_Module: ``_SLK_EREF`` links of a Name or an endpoint to an Event.

All code for ``Name.event_id`` and ``Endpoint.event_id`` lives here, so the
feature can be removed by deleting this module and its hooks (Requirement 16).
The exporter calls the two functions below, one hook per writer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Collection, Mapping, Optional

from slaktbusken.gedcom.parser import GedcomLine
from slaktbusken.model.event import Event

EREF_TAG = "_SLK_EREF"


def _eref_line(
    level: int,
    event_id: Optional[str],
    events: Mapping[str, Event],
    token_of: Callable[[Event], str],
) -> list[str]:
    """``<level> _SLK_EREF <token>``, or nothing when the event does not exist."""
    if not event_id:
        return []
    event = events.get(event_id)
    if event is None:
        return []
    token = token_of(event)
    if not token:
        return []
    return [f"{level} {EREF_TAG} {token}"]


def export_name_link(
    name,
    events: Mapping[str, Event],
    token_of: Callable[[Event], str],
) -> list[str]:
    """Lines to append under ``1 NAME`` (level 2) for ``Name.event_id``."""
    return _eref_line(2, getattr(name, "event_id", None), events, token_of)


def export_endpoint_link(
    endpoint,
    events: Mapping[str, Event],
    token_of: Callable[[Event], str],
) -> list[str]:
    """Lines to append under ``2 _SLK_START``/``_SLK_END`` (level 3)."""
    return _eref_line(3, getattr(endpoint, "event_id", None), events, token_of)


# ---------------------------------------------------------------------------
# Import side. This module is the only reader of ``_SLK_EREF``.
# ---------------------------------------------------------------------------


@dataclass
class LinkRequest:
    """One ``_SLK_EREF`` found in the file: set ``target.event_id`` later.

    ``target`` is a ``Name`` or an ``Endpoint``; ``token`` is the Event_Token.
    """

    target: object
    token: str
    xref: Optional[str] = None
    line_number: int = 0


def read_eref(node: Optional[GedcomLine]) -> Optional[str]:
    """The Event_Token of the ``_SLK_EREF`` child of *node*, or ``None``.

    Total: an empty value, a value with whitespace inside, or a repeat
    (the first counts) never raises.
    """
    for child in getattr(node, "children", None) or []:
        if getattr(child, "tag", "") != EREF_TAG:
            continue
        value = getattr(child, "value", None)
        token = value.strip() if isinstance(value, str) else ""
        if not token or any(ch.isspace() for ch in token):
            return None
        return token
    return None


def collect_name_links(
    requests: list[LinkRequest],
    names: list,
    tokens: list[Optional[str]],
    first_token_index: int,
    xref: Optional[str],
) -> None:
    """Queue links of built names. ``names[k]`` came from ``tokens[k + offset]``."""
    for k, name in enumerate(names):
        index = k + first_token_index
        if 0 <= index < len(tokens) and tokens[index]:
            requests.append(LinkRequest(name, tokens[index], xref))


def collect_endpoint_links(
    requests: list[LinkRequest],
    residence,
    resi_record: GedcomLine,
    xref: Optional[str],
) -> None:
    """Queue the ``_SLK_EREF`` of ``_SLK_START``/``_SLK_END`` of a new residence."""
    for tag, endpoint in (("_SLK_START", residence.start), ("_SLK_END", residence.end)):
        for node in getattr(resi_record, "children", None) or []:
            if getattr(node, "tag", "") == tag:
                token = read_eref(node)
                if token:
                    requests.append(LinkRequest(
                        endpoint, token, xref, getattr(node, "line_number", 0)
                    ))
                break


def resolve_event_links(
    requests: list[LinkRequest],
    token_map: Mapping[str, str],
    event_ids: Collection[str],
    warn: Callable[[LinkRequest], None],
) -> int:
    """Set ``event_id`` of every request whose token names a known event.

    An unresolved token calls ``warn`` and leaves the target unchanged.
    Returns the number of links that now point at an event.
    """
    resolved = 0
    for request in requests:
        event_id = token_map.get(request.token)
        if event_id is None or event_id not in event_ids:
            warn(request)
            continue
        if getattr(request.target, "event_id", None) != event_id:
            request.target.event_id = event_id
        resolved += 1
    return resolved
