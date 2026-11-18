# Mandatory-guard findings (task 1.1; guard, conftest.py and
# scripts/run_mandatory_tests.py were read, tests/mandatory_groups.py is untouched):
#
# * MandatoryGroup.properties MAY be an empty tuple. It is only used by
#   test_every_mandatory_property_is_tagged in the guard, which loops over
#   group.properties; an empty tuple means no tag is required. The runner and
#   the conftest hooks never read it. Non-empty entries require a
#   "# Feature: person-comparison-and-merge, Property {n}:" tag in the group's
#   modules (that tag text is fixed to the other feature in the guard).
# * required_tests entries "module::pattern" are matched with
#   fnmatch.fnmatchcase on the function name (parametrised ids stripped, class
#   methods match by method name). A trailing "*" therefore makes a prefix
#   entry: "test_dp_property_*" needs at least one collected test whose name
#   starts with "test_dp_property_". The guard (AST), conftest strict collection
#   check and runner (junit) all use this same rule. The runner also requires at
#   least len(required_tests) executed tests per group.
# * Modules are only subject to the guard and the conftest skip/xfail hooks
#   once they are listed in a group's `modules` (task 12.1). Unregistered
#   modules carrying pytestmark = pytest.mark.mandatory_integrity are ignored by
#   the guard, and the marker is already registered, so the package does not
#   break the guard before registration.
"""Hypothesis strategies for the Dataskydd tests (filled by later tasks)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.mandatory_integrity

from hypothesis import strategies as st

from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.record_origin import RecordOrigin
from slaktbusken.model.residence import Endpoint, ResidenceFact

_TEXT = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters=" åäöÅÄÖ"
    ),
    max_size=12,
)
_NON_EMPTY_TEXT = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1,
    max_size=12,
)
_ID = st.integers(1, 50)


@st.composite
def iso_days(draw) -> str:
    """A full ISO date that is real in both calendars (day 1..28)."""
    return (
        f"{draw(st.integers(1500, 1999)):04d}-"
        f"{draw(st.integers(1, 12)):02d}-{draw(st.integers(1, 28)):02d}"
    )


@st.composite
def iso_values(draw) -> str:
    """ÅÅÅÅ, ÅÅÅÅ-MM or ÅÅÅÅ-MM-DD, real in both calendars."""
    full = draw(iso_days())
    return full[: draw(st.sampled_from([4, 7, 10]))]


source_refs = st.builds(
    SourceRef,
    source_id=_ID.map(lambda n: f"source_{n}"),
    quality=st.sampled_from(["primary", "secondary", "tradition"]),
    note=_TEXT,
    aspects=st.lists(_NON_EMPTY_TEXT, max_size=2),
)

record_origins = st.builds(
    RecordOrigin,
    owner_kind=st.sampled_from(["INDI", "FAM"]),
    owner_id=_ID.map(lambda n: f"person_{n}"),
    owner_xref=_ID.map(lambda n: f"@I{n}@"),
    tag_key=st.sampled_from(["BIRT", "DEAT", "EVEN:flytt", "MARR"]),
    index=st.integers(0, 5),
    record_hash=st.text(alphabet="0123456789abcdef", min_size=64, max_size=64),
    uid=st.one_of(st.none(), _NON_EMPTY_TEXT),
    instance=st.integers(0, 4),
)

residence_origins = record_origins.map(
    lambda o: RecordOrigin(
        "INDI", o.owner_id, o.owner_xref, "RESI", o.index, o.record_hash,
        o.uid, o.instance,
    )
)


@st.composite
def valid_date_values(draw) -> DateValue:
    """A DateValue that passes ``validate_date_value`` with any new field mix."""
    refs = draw(st.lists(source_refs, max_size=2))
    calendar = draw(st.sampled_from(["gregorian", "julian"]))
    original = draw(st.one_of(st.none(), _NON_EMPTY_TEXT))
    kind = draw(st.sampled_from(["exact", "single", "range", "interpreted", "unparsed"]))
    if kind == "exact":
        return DateValue(
            draw(iso_values()), draw(st.sampled_from(["day", "month", "year", "approximate"])),
            refs, "exact", None, calendar, original,
        )
    if kind == "single":
        q = draw(st.sampled_from(
            ["about", "estimated", "calculated", "before", "after", "from", "to"]
        ))
        return DateValue(draw(iso_values()), "approximate", refs, q, None, calendar, original)
    if kind == "range":
        q = draw(st.sampled_from(["between", "from_to"]))
        start = draw(iso_days())
        end = f"{int(start[:4]) + draw(st.integers(0, 5)):04d}{start[4:]}"
        return DateValue(start, "approximate", refs, q, end, calendar, original)
    if kind == "interpreted":
        return DateValue(
            draw(iso_values()), "approximate", refs, "interpreted", None,
            calendar, draw(_NON_EMPTY_TEXT),
        )
    return DateValue(
        "", draw(st.sampled_from(["day", "month", "year", "approximate"])),
        refs, "unparsed", None, calendar, draw(_NON_EMPTY_TEXT),
    )


@st.composite
def events(draw) -> Event:
    """An event with any combination of the 0.5 fields."""
    n = draw(_ID)
    return Event(
        id=f"event_{n}",
        type=draw(st.sampled_from(["birth", "death", "baptism", "census"])),
        participants=[Participant(f"person_{draw(_ID)}", "self")],
        date=draw(st.one_of(st.none(), valid_date_values())),
        place=draw(st.one_of(
            st.none(),
            st.builds(PlaceRef, _ID.map(lambda k: f"place_{k}"), st.lists(source_refs, max_size=1)),
        )),
        source_refs=draw(st.lists(source_refs, max_size=3)),
        origin=draw(st.one_of(st.none(), record_origins)),
    )


@st.composite
def residences(draw) -> ResidenceFact:
    """A residence with zero or more origins (equal ones allowed)."""
    origins = draw(st.lists(residence_origins, max_size=3))
    if origins and draw(st.booleans()):
        origins.append(origins[0])
    return ResidenceFact(
        id=f"residence_{draw(_ID)}",
        person_id=f"person_{draw(_ID)}",
        place_id=f"place_{draw(_ID)}",
        start=Endpoint(earliest=draw(st.one_of(st.none(), iso_values()))),
        end=Endpoint(),
        origins=origins,
    )


# A JSON-like document body for migration properties.
_json_leaf = st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=10))
json_values = st.recursive(
    _json_leaf,
    lambda c: st.one_of(
        st.lists(c, max_size=3), st.dictionaries(st.text(max_size=6), c, max_size=3)
    ),
    max_leaves=8,
)


@st.composite
def documents_0_4(draw) -> dict:
    """An arbitrary 0.4-versioned project dictionary."""
    doc = draw(
        st.dictionaries(
            st.text(max_size=8).filter(lambda k: k not in ("version", "format_version")),
            json_values,
            max_size=6,
        )
    )
    doc["version"] = "0.4"
    doc["format_version"] = "0.4"
    return doc


# --- Event citations (task 3.4) ------------------------------------------------

_ref_lists = st.lists(source_refs, max_size=3)


@st.composite
def cited_events(draw, *, with_date: bool = False) -> Event:
    """An event with citations in any mix of event, date, place and from-place.

    One participant, ``person_1``. ``with_date`` forces a non-empty date value,
    so comparison items exist for the event.
    """
    date = None
    if with_date or draw(st.booleans()):
        date = DateValue(draw(iso_values()), "day", draw(_ref_lists))
    place = draw(st.one_of(
        st.none(),
        st.builds(PlaceRef, _ID.map(lambda k: f"place_{k}"), _ref_lists),
    ))
    from_place = draw(st.one_of(
        st.none(),
        st.builds(PlaceRef, _ID.map(lambda k: f"place_{k}"), _ref_lists),
    ))
    return Event(
        id=f"event_{draw(_ID)}",
        type="birth",
        participants=[Participant("person_1", "self")],
        date=date,
        place=place,
        from_place=from_place,
        source_refs=draw(_ref_lists),
    )


def cited_event_lists(*, with_date: bool = False, max_size: int = 4):
    """Lists of cited events with unique ids."""
    return st.lists(
        cited_events(with_date=with_date), max_size=max_size, unique_by=lambda e: e.id
    )
