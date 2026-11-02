"""Family and relationship integrity of the merge plan (task 11.4, Req 23 to 26.2).

Mandatory group (b): family relationship integrity. Never skipped.
"""

from __future__ import annotations

import copy

import pytest
from hypothesis import given, settings, strategies as st

from slaktbusken.model.event import Event, Participant
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services import merge_planner as mp
from slaktbusken.services.merge_planner import MergeDecisions, build_plan
from slaktbusken.services.merge_planner_families import SAME_NAME_NOTE

pytestmark = pytest.mark.mandatory_integrity


def _person(pid, given="Anna", surname="Berg", sex="M"):
    return Person(id=pid, sex=sex, names=[Name("birth", given, surname)])


def _fam(fid, partners, children, links=(), event_ids=()):
    return Family(
        id=fid,
        partners=[FamilyPartner(p, "partner") for p in partners],
        children=list(children),
        parent_child_links=[ParentChildLink(c, p, t) for c, p, t in links],
        event_ids=list(event_ids),
    )


def _bio(child, parent):
    return (child, parent, "biological")


def _plan(data):
    """Plan the merge of p1 and p2 (survivor p1) and prove the project is untouched."""
    before = copy.deepcopy(data)
    plan = build_plan(
        data, None, MergeDecisions("p1", "p2", survivor_id="p1", survivor_confirmed=True)
    )
    assert data == before
    return plan


def _final(data, plan):
    return mp.apply_change_set(data, plan.change_set)


def _codes(plan, blocking=None):
    return [c.code for c in plan.conflicts if blocking is None or c.is_blocking == blocking]


def test_cycle_blocks_merge():
    # p1 is a parent of x and x is a parent of p2: p1 = p2 would be its own ancestor.
    data = ProjectData(
        persons=[_person("p1"), _person("p2"), _person("x", "Kalle")],
        families=[
            _fam("F1", ["p1"], ["x"], [_bio("x", "p1")]),
            _fam("F2", ["x"], ["p2"], [_bio("p2", "x")]),
        ],
    )
    plan = _plan(data)
    cycle = [c for c in plan.blocking if c.code == "cycle"]
    assert len(cycle) == 1
    assert "p1" in cycle[0].message and "x" in cycle[0].message
    assert not plan.can_execute


def test_self_partner_blocks_merge():
    data = ProjectData(
        persons=[_person("p1"), _person("p2")],
        families=[_fam("F1", ["p1", "p2"], [])],
    )
    plan = _plan(data)
    blocking = [c for c in plan.blocking if c.code == "self_partner"]
    assert len(blocking) == 1 and "F1" in blocking[0].message
    assert not plan.can_execute


def test_self_parent_child_link_blocks_merge():
    data = ProjectData(
        persons=[_person("p1"), _person("p2")],
        families=[_fam("F1", ["p1"], ["p2"], [_bio("p2", "p1")])],
    )
    plan = _plan(data)
    assert "self_parent_child" in _codes(plan, blocking=True)
    assert not plan.can_execute


def test_parent_child_link_types_preserved():
    data = ProjectData(
        persons=[_person("p1"), _person("p2"), _person("c", "Kalle")],
        families=[
            _fam("F1", ["p1"], ["c"], [_bio("c", "p1")]),
            _fam("F2", ["p2"], ["c"], [("c", "p2", "legal")]),
            _fam("F3", ["p2"], ["c"], [("c", "p2", "legal")]),
        ],
    )
    plan = _plan(data)
    assert not plan.blocking
    warnings = [c for c in plan.warnings if c.code == "parentage_type_conflict"]
    assert len(warnings) == 1
    assert "biological" in warnings[0].message and "legal" in warnings[0].message
    final = _final(data, plan)
    links = {
        (l.child_id, l.parent_id, l.parentage_type)
        for f in final.families for l in f.parent_child_links
    }
    assert links == {("c", "p1", "biological"), ("c", "p1", "legal")}
    # Several parent sets of different types never block by themselves.
    assert plan.can_execute


def test_foster_adoptive_families_resynchronised():
    foster = Event(
        id="E1", type="foster_home",
        participants=[Participant("c", "fosterbarn"), Participant("p2", "fosterförälder")],
    )
    adoption = Event(
        id="E2", type="adoption",
        participants=[Participant("d", "adopterad"), Participant("p2", "adoptivförälder")],
    )
    data = ProjectData(
        persons=[_person("p1"), _person("p2"), _person("c", "Kalle"), _person("d", "Lisa", "F")],
        events=[foster, adoption],
        families=[
            Family("F1", [FamilyPartner("p2", "father")], ["c"],
                   [ParentChildLink("c", "p2", "foster")], ["E1"]),
            Family("F2", [FamilyPartner("p2", "father")], ["d"],
                   [ParentChildLink("d", "p2", "adoptive")], ["E2"]),
        ],
    )
    plan = _plan(data)
    assert not plan.blocking
    final = _final(data, plan)
    by_id = {f.id: f for f in final.families}
    assert [p.person_id for p in by_id["F1"].partners] == ["p1"]
    assert [(l.child_id, l.parent_id, l.parentage_type) for l in by_id["F1"].parent_child_links] == [
        ("c", "p1", "foster")
    ]
    assert by_id["F1"].event_ids == ["E1"] and by_id["F2"].event_ids == ["E2"]
    assert set(plan.preview.changed_family_ids) == {"F1", "F2"}
    assert plan.preview.family_count == 2
    # The new foster/adoptive links are the ones the real sync produces: a second
    # sync of the synchronised result changes nothing.
    from slaktbusken.services.foster_sync import sync_parentage_links

    again = copy.deepcopy(final)
    sync_parentage_links(again)
    assert again.families == final.families


def test_two_brita_seven_distinct_children():
    kids_1 = ["pelle", "kalle1", "olle1"]
    kids_2 = ["stina", "fia", "kalle2", "olle2"]
    names = {"pelle": "Pelle", "kalle1": "Kalle", "olle1": "Olle", "stina": "Stina",
             "fia": "Fia", "kalle2": "Kalle", "olle2": "Olle"}
    data = ProjectData(
        persons=[_person("p1", "Brita", sex="F"), _person("p2", "Brita", sex="F"),
                 _person("h1", "Per"), _person("h2", "Nils")]
        + [_person(k, n) for k, n in names.items()],
        families=[
            _fam("F1", ["p1", "h1"], kids_1, [_bio(k, "p1") for k in kids_1]),
            _fam("F2", ["p2", "h2"], kids_2, [_bio(k, "p2") for k in kids_2]),
        ],
    )
    plan = _plan(data)
    assert not plan.blocking
    final = _final(data, plan)
    assert len(final.families) == 2
    children = [c for f in final.families if any(p.person_id == "p1" for p in f.partners)
                for c in f.children]
    assert len(children) == 7 and set(children) == set(names)
    assert {p.id for p in final.persons} == {"p1", "h1", "h2", *names}
    assert len([l for f in final.families for l in f.parent_child_links]) == 7
    assert plan.change_set.replaced["persons"].keys() == {"p1"}


def test_same_name_siblings_stay_distinct():
    data = ProjectData(
        persons=[_person("p1"), _person("p2"), _person("k1", "Kalle"), _person("k2", "kalle"),
                 _person("m1", "Mor", sex="F"), _person("m2", "Mamma", sex="F")],
        families=[
            _fam("F1", ["m1"], ["p1", "k1"], [_bio("p1", "m1"), _bio("k1", "m1")]),
            _fam("F2", ["m2"], ["p2", "k2"], [_bio("p2", "m2"), _bio("k2", "m2")]),
        ],
    )
    plan = _plan(data)
    assert not plan.blocking
    notes = [i for i in plan.items if i.item_id == "same_name_note"]
    assert len(notes) == 1 and notes[0].detail == SAME_NAME_NOTE
    # Nothing is paired, merged or proposed for the two Kalle.
    assert plan.change_set.replaced["persons"].keys() == {"p1"}
    assert not plan.change_set.removed.get("persons", set()) - {"p2"}
    assert not any({"k1", "k2"} <= set(c.subjects) for c in plan.conflicts)
    assert {i.disposition for i in plan.items if i.item_id in ("k1", "k2")} == {
        mp.Disposition.LEFT_SEPARATE
    }
    final = _final(data, plan)
    assert {"k1", "k2"} <= {p.id for p in final.persons}
    assert [l.parent_id for f in final.families for l in f.parent_child_links
            if l.child_id in ("k1", "k2")] == ["m1", "m2"]


def test_duplicate_families_stay_separate_with_warning():
    data = ProjectData(
        persons=[_person("p1"), _person("p2"), _person("x", "Eva", sex="F"),
                 _person("c1", "Ola"), _person("c2", "Lina", sex="F")],
        families=[
            _fam("F1", ["p1", "x"], ["c1"], [_bio("c1", "p1"), _bio("c1", "x")]),
            _fam("F2", ["p2", "x"], ["c2"], [_bio("c2", "p2"), _bio("c2", "x")]),
        ],
    )
    plan = _plan(data)
    assert not plan.blocking and plan.can_execute
    dup = [c for c in plan.warnings if c.code == "duplicate_family"]
    assert len(dup) == 1 and set(dup[0].subjects) == {"F1", "F2"}
    assert "F1" in dup[0].message and "F2" in dup[0].message
    final = _final(data, plan)
    by_id = {f.id: f for f in final.families}
    assert set(by_id) == {"F1", "F2"}
    assert by_id["F1"].children == ["c1"] and by_id["F2"].children == ["c2"]
    assert len(by_id["F1"].parent_child_links) == 2 and len(by_id["F2"].parent_child_links) == 2

# ---------------------------------------------------------------------------
# Property 32: cycle and self-relationship detection (task 11.11)
# ---------------------------------------------------------------------------

_SELF_CODES = {"cycle", "self_partner", "self_parent_child"}
_PARENTAGE_TYPES = ["biological", "legal", "step"]


@st.composite
def _family_graphs(draw):
    """Persons in topological order (index = generation rank) with p1/p2 anywhere.

    Every child sits after all of its parents, so the original graph is acyclic.
    """
    n = draw(st.integers(2, 8))
    a, b = draw(st.lists(st.integers(0, n - 1), min_size=2, max_size=2, unique=True))
    ids = [f"x{i}" for i in range(n)]
    ids[a], ids[b] = "p1", "p2"
    families = []
    for fi in range(draw(st.integers(0, 6))):
        first = draw(st.integers(0, n - 2))
        partner_idx = draw(
            st.lists(st.integers(0, first), min_size=1, max_size=2, unique=True)
        )
        top = max(partner_idx)
        child_idx = draw(
            st.lists(st.integers(top + 1, n - 1), min_size=1, max_size=3, unique=True)
        ) if top + 1 <= n - 1 else []
        if not child_idx:
            continue
        links = [
            (ids[c], ids[p], draw(st.sampled_from(_PARENTAGE_TYPES)))
            for c in child_idx for p in partner_idx
        ]
        families.append(
            _fam(f"F{fi}", [ids[p] for p in partner_idx], [ids[c] for c in child_idx], links)
        )
    return ProjectData(persons=[_person(i) for i in ids], families=families)


def _oracle(data):
    """Reference answer on the post-merge graph (p2 replaced by p1)."""
    m = lambda x: "p1" if x == "p2" else x  # noqa: E731
    self_partner = self_parent_child = False
    parents: dict[str, set[str]] = {}
    for fam in data.families:
        partners = [p.person_id for p in fam.partners]
        if "p1" in partners and "p2" in partners:
            self_partner = True
        if ("p1" in partners and "p2" in fam.children) or (
            "p2" in partners and "p1" in fam.children
        ):
            self_parent_child = True
        for link in fam.parent_child_links:
            c, p = m(link.child_id), m(link.parent_id)
            if c == p:
                self_parent_child = True
            else:
                parents.setdefault(c, set()).add(p)
    # Is p1 an ancestor of itself through at least one real parent edge?
    seen: set[str] = set()
    stack = list(parents.get("p1", ()))
    cycle = False
    while stack:
        node = stack.pop()
        if node == "p1":
            cycle = True
            break
        if node not in seen:
            seen.add(node)
            stack.extend(parents.get(node, ()))
    codes = set()
    if cycle:
        codes.add("cycle")
    if self_partner:
        codes.add("self_partner")
    if self_parent_child:
        codes.add("self_parent_child")
    return codes


# Feature: person-comparison-and-merge, Property 32:
@settings(settings.get_profile("sbk"))
@given(_family_graphs())
def test_property_32_cycle_and_self_relationship(data):
    """**Validates: Requirements 23.6, 23.7**"""
    expected = _oracle(data)
    plan = _plan(data)  # also proves the project is unchanged
    blocking_self = [c for c in plan.blocking if c.code in _SELF_CODES]
    assert {c.code for c in blocking_self} == expected
    for conflict in blocking_self:
        assert "p1" in conflict.message or "p1" in conflict.subjects
    # Several parentage types for one child never block by themselves.
    assert {c.code for c in plan.blocking} <= _SELF_CODES
    assert plan.can_execute == (not expected)


# ---------------------------------------------------------------------------
# Property 33: families stay separate (task 11.12)
# ---------------------------------------------------------------------------

_PARTNER_POOL = ["p1", "p2", "a", "b"]


@st.composite
def _equivalent_family_projects(draw):
    """Families over a small partner pool, so equal partner sets are frequent."""
    partner_sets = draw(
        st.lists(
            st.lists(st.sampled_from(_PARTNER_POOL), min_size=1, max_size=2, unique=True)
            .filter(lambda s: not {"p1", "p2"} <= set(s)),
            min_size=2, max_size=6,
        )
    )
    families, kids = [], []
    for i, partners in enumerate(partner_sets):
        children = [f"k{i}_{j}" for j in range(draw(st.integers(0, 2)))]
        kids += children
        families.append(
            _fam(f"F{i}", partners, children,
                 [_bio(c, p) for c in children for p in partners])
        )
    persons = [_person(i, n) for i, n in (("p1", "Anna"), ("p2", "Anna"), ("a", "Eva"), ("b", "Per"))]
    persons += [_person(k, "Barn") for k in kids]
    return ProjectData(persons=persons, families=families)


# Feature: person-comparison-and-merge, Property 33:
@settings(settings.get_profile("sbk"))
@given(_equivalent_family_projects())
def test_property_33_families_stay_separate(data):
    """**Validates: Requirements 23.9, 23.10**"""
    plan = _plan(data)
    assert not plan.blocking
    final = _final(data, plan)

    def mapped(ids):
        return frozenset("p1" if i == "p2" else i for i in ids)

    # No family is combined, deleted or has members moved on the basis of equal
    # partner sets: ids, children and partners (retired -> survivor) are preserved.
    assert [f.id for f in final.families] == [f.id for f in data.families]
    after = {f.id: f for f in final.families}
    for fam in data.families:
        new = after[fam.id]
        assert new.children == fam.children
        assert mapped(p.person_id for p in new.partners) == mapped(
            p.person_id for p in fam.partners
        )
        assert {(l.child_id, l.parent_id) for l in new.parent_child_links} == {
            (l.child_id, "p1" if l.parent_id == "p2" else l.parent_id)
            for l in fam.parent_child_links
        }
    assert plan.preview.family_count == len(data.families)
    assert not plan.preview.added_family_ids and not plan.preview.removed_family_ids

    # Every pair that became equivalent through the merge yields a non-blocking
    # warning naming both families.
    expected = set()
    for i, first in enumerate(data.families):
        for second in data.families[i + 1:]:
            set_1 = mapped(p.person_id for p in first.partners)
            if set_1 != mapped(p.person_id for p in second.partners):
                continue
            touched = any(
                "p2" in (p.person_id for p in f.partners) for f in (first, second)
            )
            if "p1" in set_1 and touched:
                expected.add(frozenset((first.id, second.id)))
    warned = {
        frozenset(c.subjects) for c in plan.warnings if c.code == "duplicate_family"
    }
    assert expected <= warned
    for c in plan.conflicts:
        if c.code == "duplicate_family":
            assert not c.is_blocking
            assert all(fid in c.message for fid in c.subjects)


# ---------------------------------------------------------------------------
# Property 34: relatives stay distinct (task 11.13)
# ---------------------------------------------------------------------------

_CHILD_NAMES = ["Kalle", "Olle", "kalle", "Stina"]  # few names: same-named relatives are common


@st.composite
def _two_parent_projects(draw):
    """p1 and p2 each have 0-4 own children (distinct ids, names drawn from a tiny pool)."""
    kids_1 = [f"a{i}" for i in range(draw(st.integers(0, 4)))]
    kids_2 = [f"b{i}" for i in range(draw(st.integers(0, 4)))]
    persons = [_person("p1", "Brita", sex="F"), _person("p2", "Brita", sex="F"),
               _person("h1", "Per"), _person("h2", "Nils")]
    for kid in kids_1 + kids_2:
        persons.append(_person(kid, draw(st.sampled_from(_CHILD_NAMES))))
    families = []
    if kids_1 or draw(st.booleans()):
        families.append(_fam("F1", ["p1", "h1"], kids_1, [_bio(k, "p1") for k in kids_1]))
    if kids_2 or draw(st.booleans()):
        families.append(_fam("F2", ["p2", "h2"], kids_2, [_bio(k, "p2") for k in kids_2]))
    return ProjectData(persons=persons, families=families), kids_1, kids_2


# Feature: person-comparison-and-merge, Property 34:
@settings(settings.get_profile("sbk"))
@given(_two_parent_projects())
def test_property_34_relatives_stay_distinct(case):
    """**Validates: Requirements 24.1, 24.2, 24.3, 24.4, 24.8, 33.4**"""
    data, kids_1, kids_2 = case
    plan = _plan(data)  # also proves planning leaves the project unchanged
    assert not plan.blocking
    final = _final(data, plan)

    # Only the retired person disappears; every relative keeps its own record.
    assert {p.id for p in final.persons} == {p.id for p in data.persons} - {"p2"}
    for person in data.persons:
        if person.id not in ("p1", "p2"):
            assert next(p for p in final.persons if p.id == person.id) == person

    # The survivor is the parent of the union of the children, each child once,
    # and every link keeps its own child, parentage type and (survivor) parent.
    children = [c for f in final.families
                if any(p.person_id == "p1" for p in f.partners) for c in f.children]
    assert sorted(children) == sorted(kids_1 + kids_2)
    links = [(l.child_id, l.parent_id, l.parentage_type)
             for f in final.families for l in f.parent_child_links
             if l.child_id in set(kids_1 + kids_2)]
    assert sorted(links) == sorted((k, "p1", "biological") for k in kids_1 + kids_2)
    assert not any("p2" in (p.person_id for p in f.partners) for f in final.families)

    # No relative is paired, merged or proposed as a candidate (24.2, 24.8).
    relatives = set(kids_1 + kids_2 + ["h1", "h2"])
    assert not plan.change_set.removed.get("persons", set()) - {"p2"}
    assert plan.change_set.replaced.get("persons", {}).keys() <= {"p1"}
    assert not (plan.change_set.removed.get("persons", set()) & relatives)
    assert not any(len(set(c.subjects) & relatives) > 1 for c in plan.conflicts)
    assert plan.candidate_ops == mp.CandidateOps()
    assert "merge_candidates" not in plan.change_set.touched_collections()
    assert (getattr(final, "merge_candidates", None) or []) == (
        getattr(data, "merge_candidates", None) or []
    )


# ---------------------------------------------------------------------------
# Property 35: plan equals synchronised result (task 11.14)
# ---------------------------------------------------------------------------

_PLACEMENTS = {
    "foster_home": ("foster", "fosterbarn", "fosterförälder"),
    "adoption": ("adoptive", "adopterad", "adoptivförälder"),
}
_PARENT_POOL = ["p1", "p2", "h"]


@st.composite
def _placement_projects(draw):
    """Biological families plus foster/adoption placement events for p1, p2 and h.

    The project is synchronised before planning (as a saved project is), so the
    derived families exist. Children are never parents: no cycle can arise.
    """
    children = [f"c{i}" for i in range(draw(st.integers(1, 4)))]
    events, families, n_event = [], [], 0
    for child in children:
        if draw(st.booleans()):
            parent = draw(st.sampled_from(_PARENT_POOL))
            families.append(
                _fam(f"B{child}", [parent], [child], [_bio(child, parent)])
            )
        for _ in range(draw(st.integers(0, 2))):
            etype = draw(st.sampled_from(sorted(_PLACEMENTS)))
            _, child_role, parent_role = _PLACEMENTS[etype]
            parents = draw(
                st.lists(st.sampled_from(_PARENT_POOL), min_size=1, max_size=2, unique=True)
                # p1 and p2 as one parent set would be a self-partner (Property 32).
                .filter(lambda s: not {"p1", "p2"} <= set(s))
            )
            n_event += 1
            events.append(
                Event(
                    id=f"E{n_event}", type=etype,
                    participants=[Participant(child, child_role)]
                    + [Participant(p, parent_role) for p in parents],
                )
            )
    persons = [_person(i) for i in _PARENT_POOL] + [_person(c, "Barn") for c in children]
    data = ProjectData(persons=persons, events=events, families=families)
    from slaktbusken.services.foster_sync import sync_parentage_links

    sync_parentage_links(data)
    return data


def _canonical_families(families):
    """Order- and id-independent form of a family list."""
    return sorted(
        (
            tuple(sorted(p.person_id for p in f.partners)),
            tuple(sorted(f.children)),
            tuple(sorted((l.child_id, l.parent_id, l.parentage_type) for l in f.parent_child_links)),
            tuple(sorted(f.event_ids)),
        )
        for f in families
    )


def _independent_sync_result(data):
    """Rewrite p2 -> p1 by hand on a deep copy, then run the real sync on it."""
    from slaktbusken.services.foster_sync import sync_parentage_links

    work = copy.deepcopy(data)
    m = lambda x: "p1" if x == "p2" else x  # noqa: E731
    work.persons = [p for p in work.persons if p.id != "p2"]
    for ev in work.events:
        seen, kept = set(), []
        for part in ev.participants:
            part.person_id = m(part.person_id)
            if (part.person_id, part.role) not in seen:
                seen.add((part.person_id, part.role))
                kept.append(part)
        ev.participants = kept
    for fam in work.families:
        partners, seen = [], set()
        for p in fam.partners:
            p.person_id = m(p.person_id)
            if p.person_id not in seen:
                seen.add(p.person_id)
                partners.append(p)
        fam.partners = partners
        fam.children = list(dict.fromkeys(m(c) for c in fam.children))
        links, seen_links = [], set()
        for l in fam.parent_child_links:
            l.child_id = m(l.child_id)
            l.parent_id = m(l.parent_id) if l.parent_id is not None else None
            key = (l.child_id, l.parent_id, l.parentage_type)
            if key not in seen_links:
                seen_links.add(key)
                links.append(l)
        fam.parent_child_links = links
    sync_parentage_links(work)
    return work


# Feature: person-comparison-and-merge, Property 35:
@settings(settings.get_profile("sbk"))
@given(_placement_projects())
def test_property_35_plan_equals_synchronised_result(data):
    """**Validates: Requirements 23.12, 23.13, 26.2**"""
    from slaktbusken.model.validators import validate_family
    from slaktbusken.services.foster_sync import sync_parentage_links

    plan = _plan(data)  # also proves the project is unchanged
    assert not plan.blocking
    final = _final(data, plan)

    # The families of the plan are those of the real sync run on an
    # independently rewritten working copy.
    expected = _independent_sync_result(data)
    assert _canonical_families(final.families) == _canonical_families(expected.families)

    # Applying the sync to the synchronised copy again changes nothing.
    again = copy.deepcopy(final)
    sync_parentage_links(again)
    assert again.families == final.families

    # The preview is read from the same synchronised structures.
    original = {f.id: f for f in data.families}
    after = {f.id: f for f in final.families}
    assert plan.preview.family_count == len(final.families)
    assert plan.preview.parent_child_link_count == sum(
        len(f.parent_child_links) for f in final.families
    )
    assert set(plan.preview.removed_family_ids) == set(original) - set(after)
    assert set(plan.preview.added_family_ids) == set(after) - set(original)
    assert set(plan.preview.changed_family_ids) == {
        fid for fid, f in after.items() if fid in original and f != original[fid]
    }

    # Every changed or added family passes family validation (otherwise a
    # blocking conflict would exist, which was excluded above).
    ids = {p.id for p in final.persons}
    for fid in set(plan.preview.changed_family_ids) | set(plan.preview.added_family_ids):
        assert validate_family(after[fid], ids) == []

    # No foster or adoptive link is dropped: each link, with p2 mapped to p1,
    # is present in the synchronised result.
    m = lambda x: "p1" if x == "p2" else x  # noqa: E731
    kept = {
        (l.child_id, l.parent_id, l.parentage_type)
        for f in final.families for l in f.parent_child_links
    }
    for fam in data.families:
        for l in fam.parent_child_links:
            if l.parentage_type in ("foster", "adoptive"):
                assert (m(l.child_id), m(l.parent_id), l.parentage_type) in kept
