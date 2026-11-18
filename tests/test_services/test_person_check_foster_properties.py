# Feature: foster-parents, Person checks foster/adoptive awareness
"""Tests that the Person_Check_Engine treats foster and adoptive parents
correctly.

Covers Requirement 12:
- 12.1 foster/adoptive links are distinguished from biological links when
  building the per-person parent list.
- 12.2 a child with only foster and/or adoptive parents is not flagged as
  lacking relations solely because biological parents are absent.
- 12.4 parent age-gap / chronology checks are skipped for foster links (and
  for adoptive links where the check is biologically meaningless), while
  still running for biological parents.

**Validates: Requirements 12.1, 12.2, 12.4**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.settings_io import (
    AgeCheckConfig,
    AgeCheckThreshold,
    LogicCheckConfig,
    PersonCheckConfig,
)
from slaktbusken.services.checks.age_checks import (
    check_max_age_at_childbirth,
    check_min_age_at_childbirth,
)
from slaktbusken.services.checks.chronology_checks import (
    check_birth_not_after_parent_death,
    check_no_event_before_parent_birth,
)
from slaktbusken.services.checks.structure_checks import check_must_have_relations
from slaktbusken.services.person_check_engine import (
    CheckContext,
    PersonCheckEngine,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _person(pid: str, sex: str = "U") -> Person:
    return Person(id=pid, sex=sex, names=[Name(type="birth", given="T", surname=pid)])


def _birth(pid: str, year: int) -> Event:
    return Event(
        id=f"birth_{pid}",
        type="birth",
        participants=[Participant(person_id=pid, role="subject")],
        date=DateValue(value=str(year), precision="exact"),
    )


def _death(pid: str, year: int) -> Event:
    return Event(
        id=f"death_{pid}",
        type="death",
        participants=[Participant(person_id=pid, role="subject")],
        date=DateValue(value=str(year), precision="exact"),
    )


def _family_with_links(
    family_id: str,
    child_id: str,
    parent_links: list[tuple[str, str]],
) -> Family:
    """Build a family with ``parent_child_links`` of the given parentage types.

    ``parent_links`` is a list of ``(parent_id, parentage_type)`` tuples.
    """
    return Family(
        id=family_id,
        partners=[FamilyPartner(person_id=p, role="partner") for p, _ in parent_links],
        children=[child_id],
        parent_child_links=[
            ParentChildLink(child_id=child_id, parent_id=p, parentage_type=t)
            for p, t in parent_links
        ],
    )


def _build_project(persons: list[Person], events: list[Event], families: list[Family]) -> ProjectData:
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=persons,
        events=events,
        families=families,
    )


def _context(project: ProjectData) -> CheckContext:
    """Build a CheckContext via the engine so the parentage maps are populated."""
    engine = PersonCheckEngine(data=project, config=PersonCheckConfig())
    return engine._context  # noqa: SLF001 - exercising the computed context


# ---------------------------------------------------------------------------
# 12.1 — parentage types are distinguished in the context
# ---------------------------------------------------------------------------


class TestParentageDistinction:
    """Req 12.1: the context exposes parentage type per (child, parent)."""

    def test_biological_foster_and_adoptive_are_distinguished(self) -> None:
        child = _person("c1")
        bio = _person("bio")
        foster = _person("fos")
        adoptive = _person("ado")
        fam = _family_with_links(
            "f1",
            "c1",
            [("bio", "biological"), ("fos", "foster"), ("ado", "adoptive")],
        )
        project = _build_project([child, bio, foster, adoptive], [], [fam])
        ctx = _context(project)

        # all parents present
        assert set(ctx.parents_of["c1"]) == {"bio", "fos", "ado"}
        # but only the biological parent is reported as biological
        assert ctx.biological_parents_of("c1") == ["bio"]
        assert ctx.parentage_type_of("c1", "fos") == "foster"
        assert ctx.parentage_type_of("c1", "ado") == "adoptive"

    def test_unknown_pair_defaults_to_biological(self) -> None:
        ctx = CheckContext()
        assert ctx.parentage_type_of("x", "y") == "biological"

    def test_biological_children_filters_non_biological(self) -> None:
        parent = _person("p")
        bio_child = _person("bc")
        foster_child = _person("fc")
        fam_bio = _family_with_links("f1", "bc", [("p", "biological")])
        fam_foster = _family_with_links("f2", "fc", [("p", "foster")])
        project = _build_project(
            [parent, bio_child, foster_child], [], [fam_bio, fam_foster]
        )
        ctx = _context(project)

        assert set(ctx.children_of["p"]) == {"bc", "fc"}
        assert ctx.biological_children_of("p") == ["bc"]


# ---------------------------------------------------------------------------
# 12.2 — only non-biological parents is not "saknar föräldrar"
# ---------------------------------------------------------------------------


class TestMissingParents:
    """Req 12.2: a foster/adoptive-only child is not flagged as isolated."""

    def _run(self, project: ProjectData, child_id: str) -> int:
        ctx = _context(project)
        child = ctx.persons_by_id[child_id]
        config = PersonCheckConfig(
            logic_checks=LogicCheckConfig(must_have_relations=True)
        )
        findings = check_must_have_relations(
            person=child,
            events=[],
            families=ctx.families_by_person.get(child_id, []),
            config=config,
            context=ctx,
        )
        return len(findings)

    def test_only_foster_parents_not_flagged(self) -> None:
        child = _person("c")
        foster = _person("f")
        fam = _family_with_links("fam", "c", [("f", "foster")])
        project = _build_project([child, foster], [], [fam])
        assert self._run(project, "c") == 0

    def test_only_adoptive_parents_not_flagged(self) -> None:
        child = _person("c")
        adoptive = _person("a")
        fam = _family_with_links("fam", "c", [("a", "adoptive")])
        project = _build_project([child, adoptive], [], [fam])
        assert self._run(project, "c") == 0

    def test_no_parents_at_all_is_flagged(self) -> None:
        child = _person("c")
        project = _build_project([child], [], [])
        assert self._run(project, "c") == 1

    def test_biological_parent_not_flagged(self) -> None:
        child = _person("c")
        bio = _person("b")
        fam = _family_with_links("fam", "c", [("b", "biological")])
        project = _build_project([child, bio], [], [fam])
        assert self._run(project, "c") == 0


# ---------------------------------------------------------------------------
# 12.4 — age-gap / chronology checks skip foster (and meaningless adoptive)
# ---------------------------------------------------------------------------


def _age_config() -> PersonCheckConfig:
    return PersonCheckConfig(
        age_checks=AgeCheckConfig(
            min_age_at_childbirth=AgeCheckThreshold(True, 12, 12),
            max_age_at_childbirth=AgeCheckThreshold(True, 60, 60),
        )
    )


class TestChildbirthAgeGapSkips:
    """Req 12.4: age-at-childbirth is biological-only."""

    def _childbirth_findings(self, parentage: str) -> tuple[int, int]:
        # Parent born 1900, child born 1905 -> biologically "too young" (age 5)
        parent = _person("p", sex="F")
        child = _person("c")
        fam = _family_with_links("fam", "c", [("p", parentage)])
        project = _build_project(
            [parent, child],
            [_birth("p", 1900), _birth("c", 1905)],
            [fam],
        )
        ctx = _context(project)
        config = _age_config()
        parent_events = ctx.events_by_person.get("p", [])
        low = check_min_age_at_childbirth(parent, parent_events, config, ctx)
        high = check_max_age_at_childbirth(parent, parent_events, config, ctx)
        return len(low), len(high)

    def test_biological_min_age_flagged(self) -> None:
        low, _ = self._childbirth_findings("biological")
        assert low == 1

    def test_foster_min_age_skipped(self) -> None:
        low, high = self._childbirth_findings("foster")
        assert low == 0
        assert high == 0

    def test_adoptive_min_age_skipped(self) -> None:
        low, high = self._childbirth_findings("adoptive")
        assert low == 0
        assert high == 0

    def test_biological_max_age_flagged(self) -> None:
        # Parent born 1800, child born 1900 -> age 100 > 60
        parent = _person("p", sex="F")
        child = _person("c")
        fam = _family_with_links("fam", "c", [("p", "biological")])
        project = _build_project(
            [parent, child],
            [_birth("p", 1800), _birth("c", 1900)],
            [fam],
        )
        ctx = _context(project)
        high = check_max_age_at_childbirth(
            parent, ctx.events_by_person.get("p", []), _age_config(), ctx
        )
        assert len(high) == 1


class TestParentDeathChronologySkips:
    """Req 12.4: birth-after-parent-death is biological-only."""

    def _findings(self, parentage: str) -> int:
        # Parent dies 1900, child born 1905 -> >270 days after parent death
        parent = _person("p")
        child = _person("c")
        fam = _family_with_links("fam", "c", [("p", parentage)])
        project = _build_project(
            [parent, child],
            [_death("p", 1900), _birth("c", 1905)],
            [fam],
        )
        ctx = _context(project)
        child_events = ctx.events_by_person.get("c", [])
        config = PersonCheckConfig(
            logic_checks=LogicCheckConfig(birth_not_after_parent_death=True)
        )
        return len(
            check_birth_not_after_parent_death(child, child_events, config, ctx)
        )

    def test_biological_flagged(self) -> None:
        assert self._findings("biological") == 1

    def test_foster_skipped(self) -> None:
        assert self._findings("foster") == 0

    def test_adoptive_skipped(self) -> None:
        assert self._findings("adoptive") == 0


class TestEventBeforeParentBirthSkips:
    """Req 12.4: event-before-parent-birth is biological-only."""

    def _findings(self, parentage: str) -> int:
        # Parent born 1950, child born 1900 -> child event before parent birth
        parent = _person("p")
        child = _person("c")
        fam = _family_with_links("fam", "c", [("p", parentage)])
        project = _build_project(
            [parent, child],
            [_birth("p", 1950), _birth("c", 1900)],
            [fam],
        )
        ctx = _context(project)
        child_events = ctx.events_by_person.get("c", [])
        config = PersonCheckConfig(
            logic_checks=LogicCheckConfig(no_event_before_parent_birth=True)
        )
        return len(
            check_no_event_before_parent_birth(child, child_events, config, ctx)
        )

    def test_biological_flagged(self) -> None:
        assert self._findings("biological") == 1

    def test_foster_skipped(self) -> None:
        assert self._findings("foster") == 0

    def test_adoptive_skipped(self) -> None:
        assert self._findings("adoptive") == 0


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

_NON_BIO = st.sampled_from(["foster", "adoptive"])


class TestFosterAdoptiveProperties:
    """Property coverage for Requirement 12.

    **Validates: Requirements 12.1, 12.2, 12.4**
    """

    @given(parentage=_NON_BIO)
    @settings(max_examples=50, deadline=None)
    def test_non_biological_only_child_has_parents(self, parentage: str) -> None:
        """A child with only non-biological parents is never flagged isolated."""
        child = _person("c")
        parent = _person("p")
        fam = _family_with_links("fam", "c", [("p", parentage)])
        project = _build_project([child, parent], [], [fam])
        ctx = _context(project)
        config = PersonCheckConfig(
            logic_checks=LogicCheckConfig(must_have_relations=True)
        )
        findings = check_must_have_relations(
            child, [], ctx.families_by_person.get("c", []), config, ctx
        )
        assert findings == []
        assert ctx.has_any_parents("c") is True
        assert ctx.biological_parents_of("c") == []

    @given(
        parent_year=st.integers(min_value=1800, max_value=1899),
        child_year=st.integers(min_value=1800, max_value=1899),
        parentage=_NON_BIO,
    )
    @settings(max_examples=50, deadline=None)
    def test_childbirth_age_never_flags_non_biological(
        self, parent_year: int, child_year: int, parentage: str
    ) -> None:
        """No age-at-childbirth finding is ever produced for a foster/adoptive
        child, regardless of the (implausible) year combination."""
        parent = _person("p", sex="F")
        child = _person("c")
        fam = _family_with_links("fam", "c", [("p", parentage)])
        project = _build_project(
            [parent, child],
            [_birth("p", parent_year), _birth("c", child_year)],
            [fam],
        )
        ctx = _context(project)
        config = _age_config()
        parent_events = ctx.events_by_person.get("p", [])
        assert check_min_age_at_childbirth(parent, parent_events, config, ctx) == []
        assert check_max_age_at_childbirth(parent, parent_events, config, ctx) == []
