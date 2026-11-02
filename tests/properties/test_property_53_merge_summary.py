"""Property 53: The Merge_Summary is a snapshot of the plan.

The ``summary_lines`` of the history entry created by planning a merge are the
11 fixed Swedish lines in fixed order. Every count equals a count taken
independently from the input data, the decisions and the plan's change set.
Planning is deterministic, never mutates its input, and the lines hold counts
only (no names).

The generator of ``tests/test_services/test_merge_reference_rules.py`` is
imported, not edited.

**Validates: Requirements 36.1**
"""

from __future__ import annotations

import copy
import dataclasses
import re

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from slaktbusken.model.event import DateValue, PlaceRef, SourceRef
from slaktbusken.model.person import Name
from slaktbusken.model.residence import Observation
from slaktbusken.services import merge_rules as rules
from slaktbusken.services.merge_planner import MergeDecisions, build_plan
from tests.test_services.test_merge_reference_rules import (
    _P29_DECOYS,
    _P29_RETIRED,
    _P29_SURVIVOR,
    _p29_projects,
)

_LABELS = (
    "Namn tillagda",
    "Händelser flyttade",
    "Boenden flyttade",
    "Källhänvisningar flyttade",
    "Mediaobjekt med flyttade personlänkar",
    "Familjer berörda",
    "Forskningslänkar flyttade",
    "Beslut för motstridiga fält",
    "Anteckningar sammanslagna",
    "Kandidater omdirigerade",
    "Kandidater arkiverade",
)
_LINE = re.compile(r"^([^:]+): (\d+|ja|nej)$")

_GIVEN = ["Åsa", "Östen", "Märta", "Anna"]
_SURNAMES = ["Öberg", "Ström", "Berg"]
_TEXTS = st.sampled_from(["", "  ", "Dr", "Prof", "Lektor", "Smed"])
_NOTES = st.sampled_from(["", "a", "b", "b", " a "])
_SEXES = st.sampled_from(["F", "M", "U", ""])
_MEDIA = st.sampled_from([None, "m_0", "m_1"])


@st.composite
def _scenarios(draw):
    """A project (reference generator, then enriched) and complete decisions."""
    data, translation = draw(_p29_projects())
    persons = {p.id: p for p in data.persons}
    s, r = persons[_P29_SURVIVOR], persons[_P29_RETIRED]
    for p in (s, r):
        p.sex = draw(_SEXES)
        p.title = draw(st.one_of(st.none(), _TEXTS))
        p.occupation = draw(st.one_of(st.none(), _TEXTS))
        p.profile_media_id = draw(_MEDIA)
        p.notes = draw(_NOTES)
        for _ in range(draw(st.integers(0, 2))):
            p.names.append(Name(draw(st.sampled_from(["birth", "married"])),
                                draw(st.sampled_from(_GIVEN)), draw(st.sampled_from(_SURNAMES))))
    # Source references on events and residences.
    for ev in data.events:
        if draw(st.booleans()):
            ev.date = DateValue("1900", "year", [SourceRef("src_1", "primary")
                                                 for _ in range(draw(st.integers(0, 2)))])
        if draw(st.booleans()):
            ev.place = PlaceRef("place_1", [SourceRef("src_2", "primary")
                                            for _ in range(draw(st.integers(0, 2)))])
    for res in data.residences:
        res.observations = [Observation(SourceRef("src_3", "primary"))
                            for _ in range(draw(st.integers(0, 2)))]
    if draw(st.booleans()):
        data.connection_overrides[_P29_SURVIVOR] = draw(st.sampled_from(["ovr", "other"]))

    s_ov = data.connection_overrides.get(_P29_SURVIVOR)
    r_ov = data.connection_overrides.get(_P29_RETIRED)
    decisions = MergeDecisions(
        _P29_SURVIVOR, _P29_RETIRED, survivor_id=_P29_SURVIVOR, survivor_confirmed=True,
        sex=draw(st.sampled_from([s.sex, r.sex])),
        title_from=draw(st.sampled_from([_P29_SURVIVOR, _P29_RETIRED])),
        occupation_from=draw(st.sampled_from([_P29_SURVIVOR, _P29_RETIRED])),
        profile_media_id=draw(st.sampled_from([s.profile_media_id, r.profile_media_id])),
        notes_mode=draw(st.sampled_from(["keep_survivor", "keep_other", "concatenate", "concatenate",
                                    "concatenate"])),
        primary_name=rules.name_identity(s.names[0]),
        connection_override=draw(st.sampled_from([s_ov, r_ov])),
    )
    return data, translation, decisions


# ---------------------------------------------------------------------------
# Independent counts (nothing here calls merge_summary_lines or reads plan.items)
# ---------------------------------------------------------------------------


def _source_refs(obj) -> int:
    """Own reflective walk over dataclasses and lists."""
    if isinstance(obj, SourceRef):
        return 1
    if isinstance(obj, (list, tuple)):
        return sum(_source_refs(x) for x in obj)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return sum(_source_refs(getattr(obj, f.name)) for f in dataclasses.fields(obj))
    return 0


def _blank(v) -> bool:
    return v is None or not v.strip()


def _conflict(a, b) -> bool:
    return not _blank(a) and not _blank(b) and a.strip() != b.strip()


def _known_sex(v) -> bool:
    return not _blank(v) and v.strip() != "U"


def _expected_decisions(data, d: MergeDecisions) -> int:
    persons = {p.id: p for p in data.persons}
    s, r = persons[d.survivor_id], persons[d.retired_id]
    count = 0
    if (_known_sex(s.sex) and _known_sex(r.sex) and s.sex.strip() != r.sex.strip()
            and d.sex is not None and d.sex.strip() in {s.sex.strip(), r.sex.strip()}):
        count += 1
    for a, b, chosen in ((s.title, r.title, d.title_from),
                         (s.occupation, r.occupation, d.occupation_from)):
        if _conflict(a, b) and chosen in (d.survivor_id, d.retired_id):
            count += 1
    if (_conflict(s.profile_media_id, r.profile_media_id) and d.profile_media_id is not None
            and d.profile_media_id.strip() in (s.profile_media_id.strip(),
                                               r.profile_media_id.strip())):
        count += 1
    if _conflict(s.notes, r.notes) and d.notes_mode in ("keep_survivor", "keep_other"):
        count += 1
    ov = data.connection_overrides
    if (d.retired_id in ov and d.survivor_id in ov and ov[d.retired_id] != ov[d.survivor_id]
            and d.connection_override in (ov[d.retired_id], ov[d.survivor_id])):
        count += 1
    return count


def _expected_lines(data, d: MergeDecisions, plan) -> list[str]:
    r_id, s_id = d.retired_id, d.survivor_id
    cs = plan.change_set
    persons = {p.id: p for p in data.persons}
    def identities(person):
        return {(n.given, n.surname, n.type, n.event_id) for n in person.names}

    # Names that are new to the survivor, counted once each; the result must
    # also be what the planned survivor record actually holds.
    names = len(identities(persons[r_id]) - identities(persons[s_id]))
    assert identities(cs.replaced["persons"][s_id]) == (
        identities(persons[s_id]) | identities(persons[r_id])
    )

    events = cs.replaced.get("events", {})
    residences = cs.replaced.get("residences", {})
    citations = (sum(_source_refs(e) for e in events.values())
                 + sum(_source_refs(x) for x in residences.values()))

    def person_link(entity_type, entity_id):
        return entity_type == "person" and entity_id == r_id

    media = sum(
        1 for m in data.media
        if any(person_link(le.entity_type, le.entity_id) for le in m.linked_entities)
        or r_id in m.mentioned_person_ids
        or any(person_link(a.entity_type, a.entity_id) for a in m.annotations)
    )
    families = sum(
        1 for f in data.families
        if any(p.person_id == r_id for p in f.partners) or r_id in f.children
        or any(r_id in (l.child_id, l.parent_id) for l in f.parent_child_links)
    )
    research = (
        sum(1 for c in data.research_cases
            for e in [c.primary_entity_ref, *c.linked_entities]
            if e is not None and e.entity_type == "person" and e.entity_id == r_id)
        + sum(1 for h in data.research_hypotheses for e in h.linked_entities
              if e.entity_type == "person" and e.entity_id == r_id)
    )
    notes_joined = (
        not _blank(persons[s_id].notes) and not _blank(persons[r_id].notes)
        and persons[s_id].notes.strip() != persons[r_id].notes.strip()
        and d.notes_mode == "concatenate"
    )
    redirected = len(cs.replaced.get("merge_candidates", {}))
    archived = len(cs.removed.get("merge_candidates", set()))
    values = [names, len(events), len(residences), citations, media, families,
              research, _expected_decisions(data, d),
              "ja" if notes_joined else "nej", redirected, archived]
    return [f"{label}: {v}" for label, v in zip(_LABELS, values)]


def _entry(plan):
    (entry,) = plan.change_set.added["merge_history"]
    return entry


# Feature: person-comparison-and-merge, Property 53: Merge summary is a snapshot of the plan and round-trips
@settings(max_examples=300, deadline=None,
          suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large,
                                 HealthCheck.filter_too_much])
@given(_scenarios())
def test_property_53_merge_summary_is_snapshot_of_plan(scenario):
    """**Validates: Requirements 36.1**"""
    data, translation, decisions = scenario
    data_before, translation_before = copy.deepcopy(data), copy.deepcopy(translation)

    plan = build_plan(data, translation, decisions)
    assume(plan.can_execute)
    lines = list(_entry(plan).summary_lines)

    # Planning does not mutate its input.
    assert data == data_before
    assert translation == translation_before

    # 11 fixed lines in fixed order, each "label: count".
    assert len(lines) == len(_LABELS)
    parsed = [_LINE.match(x) for x in lines]
    assert all(parsed), lines
    assert [m.group(1) for m in parsed] == list(_LABELS)

    # Each count equals the independent count.
    assert lines == _expected_lines(data, decisions, plan)

    # Deterministic for equal input (also for an equal deep copy).
    again = build_plan(copy.deepcopy(data), copy.deepcopy(translation), decisions)
    assert list(_entry(again).summary_lines) == lines

    # Counts only: no person name or id appears in any line.
    text = "\n".join(lines)
    for forbidden in (*_GIVEN, *_SURNAMES, "person_", _P29_SURVIVOR, _P29_RETIRED, *_P29_DECOYS):
        assert forbidden not in text


def test_decision_detail_strings_are_still_emitted_by_the_planners():
    """Drift guard for the Swedish strings the decision count is derived from.

    **Validates: Requirements 36.1**
    """
    import inspect

    from slaktbusken.services import merge_planner_candidates as summary_module
    from slaktbusken.services import merge_planner_person, merge_planner_refs

    emitted = inspect.getsource(merge_planner_person) + inspect.getsource(merge_planner_refs)
    for detail in summary_module._DECISION_DETAILS:
        assert detail in emitted, detail
