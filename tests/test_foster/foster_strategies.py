"""Shared Hypothesis strategies for the foster-and-adoptive-parents feature.

Feature: foster-parents

These strategies build whole ``ProjectData`` instances that exercise the
Parentage_Sync_Service (``slaktbusken/services/foster_sync.py``) and the
display resolver symmetrically for *foster* and *adoptive* parentage. They are
consumed by the property tests in tasks 2.4, 2.5 and 2.6.

The design (``.kiro/specs/foster-parents/design.md``) fixes the vocabulary used
here:

* Placement START events are the single source of truth for their links:
  - ``foster_home``  -> parentage ``"foster"``   (child role ``"fosterbarn"``,
    parent role ``"fosterförälder"``)
  - ``adoption``     -> parentage ``"adoptive"``  (child role ``"adopterad"``,
    parent role ``"adoptivförälder"``)
* Placement END events annotate a placement but never create or remove a link:
  - ``foster_home_ended`` closes a ``foster_home`` start
  - ``adoption_ended``    closes an ``adoption`` start
* ``ProjectData.connection_overrides`` maps a child id to ``"biological"`` /
  ``"foster"`` / ``"adoptive"``.

The generated projects cover, across examples:

* zero / one / many placement events per child per type;
* one-parent and two-parent placement sets;
* mixed biological + foster + adoptive parentage;
* orphan foster and adoptive links that have **no** backing placement event
  (the pre-feature state the migration must not destroy);
* pre-feature purely-descriptive ``adoption`` events (a start event with *no*
  parent-role participant, which derives nothing - Req 1.9 / 13.5);
* dated and undated events (``date`` present/absent);
* start events with and without a paired end event;
* orphan end events (an end event whose start was removed / never existed);
* end-before-start dates;
* ``connection_overrides`` entries for children that have the named set and for
  children that do not (a "missing set" override that must be ignored).

Validates / supports: Requirements 2.1, 2.9, 2A.1, 13.5

Note: these are reusable strategies only. ``@settings`` (max_examples=100,
deadline=None) belong in the property-test modules that consume them, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata


# ---------------------------------------------------------------------------
# Vocabulary (mirrors slaktbusken/services/foster_sync.py:_PLACEMENT_START/_END)
# ---------------------------------------------------------------------------

#: start event type -> parentage / child role / parent role
PLACEMENT_START: dict[str, dict[str, str]] = {
    "foster_home": {
        "parentage": "foster",
        "child_role": "fosterbarn",
        "parent_role": "fosterförälder",
    },
    "adoption": {
        "parentage": "adoptive",
        "child_role": "adopterad",
        "parent_role": "adoptivförälder",
    },
}

#: end event type -> the start event type it closes
PLACEMENT_END: dict[str, str] = {
    "foster_home_ended": "foster_home",
    "adoption_ended": "adoption",
}

#: parentage types that the sync service owns
DERIVED_PARENTAGE = ("foster", "adoptive")

#: parentage types the sync service must never touch
UNTOUCHED_PARENTAGE = ("biological", "donation", "guardian")

_SEX_VALUES = ("M", "F", "X", "U")


# ---------------------------------------------------------------------------
# A planning record describing one placement, used to assemble a project.
# ---------------------------------------------------------------------------


@dataclass
class PlacementPlan:
    """A single planned placement for a child.

    This is an intermediate description the composite strategy turns into a
    START event (always), an optional END event, and - when ``descriptive`` is
    true - a parent-less descriptive start event (Req 1.9 / 13.5).
    """

    start_type: str  # "foster_home" | "adoption"
    parent_ids: list[str]  # one or two parents (empty => descriptive-only)
    dated: bool
    start_year: Optional[int]
    has_end: bool
    end_dated: bool
    end_year: Optional[int]
    end_before_start: bool
    descriptive: bool  # parent-less start event that derives nothing


@dataclass
class FosterProject:
    """A generated project plus the metadata a property test needs.

    ``project`` is a freshly built ``ProjectData``. The remaining fields record
    what the generator *intended*, so a property test can assert against the
    plan without re-deriving it from the events.
    """

    project: ProjectData
    child_ids: list[str] = field(default_factory=list)
    parent_ids: list[str] = field(default_factory=list)
    #: ids of orphan foster/adoptive links with no backing placement event
    orphan_link_family_ids: list[str] = field(default_factory=list)
    #: ids of events that are orphan end events (no matching start)
    orphan_end_event_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Primitive strategies
# ---------------------------------------------------------------------------

_identifier = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
    min_size=3,
    max_size=10,
)


def _person_id(prefix: str) -> st.SearchStrategy[str]:
    return _identifier.map(lambda s: f"{prefix}_{s}")


def _year_strategy() -> st.SearchStrategy[int]:
    return st.integers(min_value=1500, max_value=2100)


def _make_person(draw: DrawFn, person_id: str) -> Person:
    sex = draw(st.sampled_from(_SEX_VALUES))
    given = draw(st.text(alphabet=st.characters(categories=("L",)), min_size=1, max_size=8))
    surname = draw(st.text(alphabet=st.characters(categories=("L",)), min_size=1, max_size=8))
    return Person(
        id=person_id,
        sex=sex,
        names=[Name(type="birth", given=given or "A", surname=surname or "B")],
    )


def _date(year: Optional[int]) -> Optional[DateValue]:
    if year is None:
        return None
    return DateValue(value=str(year), precision="year")


# ---------------------------------------------------------------------------
# Placement-plan strategy
# ---------------------------------------------------------------------------


@st.composite
def placement_plan(
    draw: DrawFn,
    parent_pool: list[str],
    *,
    start_type: Optional[str] = None,
    allow_descriptive: bool = True,
) -> PlacementPlan:
    """Draw a single :class:`PlacementPlan` using parents from ``parent_pool``.

    ``parent_pool`` must contain at least two ids. The plan covers one- and
    two-parent sets, dated/undated start and end events, a start with or without
    a paired end, end-before-start dates, and (for adoption) parent-less
    descriptive events.
    """
    s_type = start_type if start_type is not None else draw(st.sampled_from(list(PLACEMENT_START)))

    # Descriptive (parent-less) events only make sense for adoption (the
    # pre-feature purely descriptive adoption event). They derive nothing.
    descriptive = (
        allow_descriptive
        and s_type == "adoption"
        and draw(st.booleans())
    )

    if descriptive:
        parents: list[str] = []
    else:
        n_parents = draw(st.integers(min_value=1, max_value=2))
        parents = draw(
            st.lists(
                st.sampled_from(parent_pool),
                min_size=n_parents,
                max_size=n_parents,
                unique=True,
            )
        )

    dated = draw(st.booleans())
    start_year = draw(_year_strategy()) if dated else None

    # A descriptive event derives nothing, so an end makes no sense; skip it.
    has_end = (not descriptive) and draw(st.booleans())
    end_before_start = False
    end_dated = False
    end_year: Optional[int] = None
    if has_end:
        end_dated = draw(st.booleans())
        if end_dated:
            end_before_start = draw(st.booleans())
            if dated and start_year is not None and end_before_start:
                end_year = draw(st.integers(min_value=1500, max_value=start_year))
            elif dated and start_year is not None:
                end_year = draw(st.integers(min_value=start_year, max_value=2100))
            else:
                end_year = draw(_year_strategy())

    return PlacementPlan(
        start_type=s_type,
        parent_ids=parents,
        dated=dated,
        start_year=start_year,
        has_end=has_end,
        end_dated=end_dated,
        end_year=end_year,
        end_before_start=end_before_start,
        descriptive=descriptive,
    )


# ---------------------------------------------------------------------------
# Whole-project strategy
# ---------------------------------------------------------------------------


@st.composite
def foster_project(
    draw: DrawFn,
    *,
    min_children: int = 1,
    max_children: int = 3,
    max_parents: int = 4,
    include_orphan_links: bool = True,
    include_orphan_end_events: bool = True,
    include_biological: bool = True,
    include_overrides: bool = True,
) -> FosterProject:
    """Build a whole :class:`FosterProject` covering the task-2.3 scenarios.

    The returned project is *not* synced: it is the raw input a property test
    feeds to ``sync_parentage_links``. END events are present as free-standing
    events (not yet attached to any derived family), matching the pre-sync
    state.
    """
    # --- people ---------------------------------------------------------
    child_ids = draw(
        st.lists(_person_id("child"), min_size=min_children, max_size=max_children, unique=True)
    )
    parent_ids = draw(
        st.lists(_person_id("parent"), min_size=2, max_size=max_parents, unique=True)
    )
    # Guard against accidental id collisions between the two pools.
    parent_ids = [pid for pid in parent_ids if pid not in child_ids]
    if len(parent_ids) < 2:
        parent_ids = parent_ids + [f"parent_fallback_{i}" for i in range(2 - len(parent_ids))]

    persons: list[Person] = []
    seen_ids: set[str] = set()
    for pid in [*child_ids, *parent_ids]:
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        persons.append(_make_person(draw, pid))

    events: list[Event] = []
    families: list[Family] = []
    orphan_link_family_ids: list[str] = []
    orphan_end_event_ids: list[str] = []

    counter = {"n": 0}

    def _next(prefix: str) -> str:
        counter["n"] += 1
        return f"{prefix}_{counter['n']}"

    # --- placement events per child (zero / one / many) -----------------
    for child_id in child_ids:
        n_placements = draw(st.integers(min_value=0, max_value=3))
        for _ in range(n_placements):
            plan = draw(placement_plan(parent_ids))

            spec = PLACEMENT_START[plan.start_type]
            start_id = _next("ev_start")

            start_participants = [Participant(person_id=child_id, role=spec["child_role"])]
            for p in plan.parent_ids:
                start_participants.append(
                    Participant(person_id=p, role=spec["parent_role"])
                )

            events.append(
                Event(
                    id=start_id,
                    type=plan.start_type,
                    participants=start_participants,
                    date=_date(plan.start_year),
                )
            )

            if plan.has_end:
                end_type = next(
                    e for e, s in PLACEMENT_END.items() if s == plan.start_type
                )
                end_id = _next("ev_end")
                end_participants = [
                    Participant(person_id=child_id, role=spec["child_role"])
                ]
                for p in plan.parent_ids:
                    end_participants.append(
                        Participant(person_id=p, role=spec["parent_role"])
                    )
                events.append(
                    Event(
                        id=end_id,
                        type=end_type,
                        participants=end_participants,
                        date=_date(plan.end_year),
                    )
                )

    # --- orphan end events (no matching start) --------------------------
    if include_orphan_end_events and draw(st.booleans()):
        n_orphans = draw(st.integers(min_value=1, max_value=2))
        for _ in range(n_orphans):
            end_type = draw(st.sampled_from(list(PLACEMENT_END)))
            start_type = PLACEMENT_END[end_type]
            spec = PLACEMENT_START[start_type]
            child_id = draw(st.sampled_from(child_ids))
            n_parents = draw(st.integers(min_value=1, max_value=2))
            parents = draw(
                st.lists(
                    st.sampled_from(parent_ids),
                    min_size=n_parents,
                    max_size=n_parents,
                    unique=True,
                )
            )
            end_id = _next("ev_orphan_end")
            participants = [Participant(person_id=child_id, role=spec["child_role"])]
            for p in parents:
                participants.append(Participant(person_id=p, role=spec["parent_role"]))
            dated = draw(st.booleans())
            events.append(
                Event(
                    id=end_id,
                    type=end_type,
                    participants=participants,
                    date=_date(draw(_year_strategy())) if dated else None,
                )
            )
            orphan_end_event_ids.append(end_id)

    # --- orphan foster/adoptive links with NO backing event -------------
    # (the pre-feature state the migration must preserve; Req 13.3/13.5)
    if include_orphan_links and draw(st.booleans()):
        n_orphan_links = draw(st.integers(min_value=1, max_value=2))
        for _ in range(n_orphan_links):
            parentage = draw(st.sampled_from(DERIVED_PARENTAGE))
            child_id = draw(st.sampled_from(child_ids))
            n_parents = draw(st.integers(min_value=1, max_value=2))
            parents = draw(
                st.lists(
                    st.sampled_from(parent_ids),
                    min_size=n_parents,
                    max_size=n_parents,
                    unique=True,
                )
            )
            fam_id = _next("fam_orphan")
            families.append(
                Family(
                    id=fam_id,
                    partners=[FamilyPartner(person_id=p, role="partner") for p in parents],
                    children=[child_id],
                    parent_child_links=[
                        ParentChildLink(
                            child_id=child_id,
                            parent_id=p,
                            parentage_type=parentage,
                        )
                        for p in parents
                    ],
                    event_ids=[],
                )
            )
            orphan_link_family_ids.append(fam_id)

    # --- biological links/families (must be left untouched) -------------
    if include_biological and draw(st.booleans()):
        child_id = draw(st.sampled_from(child_ids))
        n_parents = draw(st.integers(min_value=1, max_value=2))
        bio_parents = draw(
            st.lists(
                st.sampled_from(parent_ids),
                min_size=n_parents,
                max_size=n_parents,
                unique=True,
            )
        )
        parentage = draw(st.sampled_from(UNTOUCHED_PARENTAGE))
        fam_id = _next("fam_bio")
        families.append(
            Family(
                id=fam_id,
                partners=[FamilyPartner(person_id=p, role="partner") for p in bio_parents],
                children=[child_id],
                parent_child_links=[
                    ParentChildLink(
                        child_id=child_id,
                        parent_id=p,
                        parentage_type=parentage,
                    )
                    for p in bio_parents
                ],
                event_ids=[],
            )
        )

    # --- pre-feature purely descriptive adoption event ------------------
    # A start event with no parent-role participant derives nothing.
    if draw(st.booleans()):
        child_id = draw(st.sampled_from(child_ids))
        events.append(
            Event(
                id=_next("ev_descriptive"),
                type="adoption",
                participants=[Participant(person_id=child_id, role="adopterad")],
                date=_date(draw(_year_strategy())) if draw(st.booleans()) else None,
            )
        )

    # --- connection overrides (present and absent sets) -----------------
    overrides: dict[str, str] = {}
    if include_overrides and draw(st.booleans()):
        override_targets = draw(
            st.lists(st.sampled_from(child_ids), min_size=1, max_size=len(child_ids), unique=True)
        )
        for cid in override_targets:
            overrides[cid] = draw(
                st.sampled_from(["biological", "foster", "adoptive"])
            )

    project = ProjectData(
        project=ProjectMetadata(title="Foster Property Test"),
        persons=persons,
        families=families,
        events=events,
        connection_overrides=overrides,
    )

    return FosterProject(
        project=project,
        child_ids=child_ids,
        parent_ids=parent_ids,
        orphan_link_family_ids=orphan_link_family_ids,
        orphan_end_event_ids=orphan_end_event_ids,
    )


# ---------------------------------------------------------------------------
# Convenience: a project guaranteed to contain at least one derivable start
# event, for tests that need non-trivial sync output.
# ---------------------------------------------------------------------------


@st.composite
def foster_project_with_placement(draw: DrawFn) -> FosterProject:
    """Like :func:`foster_project` but guarantees at least one real (non
    descriptive, parent-bearing) placement START event exists."""
    fp = draw(foster_project())

    has_real_start = any(
        ev.type in PLACEMENT_START
        and any(
            p.role == PLACEMENT_START[ev.type]["parent_role"]
            for p in ev.participants
        )
        for ev in fp.project.events
    )
    if has_real_start:
        return fp

    child_id = fp.child_ids[0]
    start_type = draw(st.sampled_from(list(PLACEMENT_START)))
    spec = PLACEMENT_START[start_type]
    n_parents = draw(st.integers(min_value=1, max_value=2))
    parents = draw(
        st.lists(
            st.sampled_from(fp.parent_ids),
            min_size=n_parents,
            max_size=n_parents,
            unique=True,
        )
    )
    participants = [Participant(person_id=child_id, role=spec["child_role"])]
    for p in parents:
        participants.append(Participant(person_id=p, role=spec["parent_role"]))
    fp.project.events.append(
        Event(
            id=f"ev_start_guaranteed_{len(fp.project.events)}",
            type=start_type,
            participants=participants,
            date=_date(draw(_year_strategy())) if draw(st.booleans()) else None,
        )
    )
    return fp
