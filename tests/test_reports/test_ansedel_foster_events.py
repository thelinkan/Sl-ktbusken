"""Unit and property tests for foster/adoptive handling in the Ansedel report.

Covers four related bug fixes in ``ansedel.py``:

* BUG 1 — a co-partner shared across a biological and a derived foster family is
  listed once in the "Partner" section.
* BUG 2 — a foster/adoptive parent does not get the placed child's
  "Barns födelse"/"Barns död" lines; a biological parent still does.
* BUG 3 — the Fosterhem/Adoption event line differs between the parent's and the
  child's perspective and names the relevant child on the parent's line.
* BUG 4 — a placement event line lists the family's foster/adoptive parents so a
  child who lived in several families gets distinguishable lines.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.reports.ansedel import generate_ansedel
from slaktbusken.reports.content import HeadingBlock, ListBlock


def _person(pid: str, given: str, surname: str) -> Person:
    return Person(id=pid, sex="U", names=[Name(type="birth", given=given, surname=surname)])


def _birth(pid: str, date: str) -> Event:
    return Event(
        id=f"ev_birth_{pid}",
        type="birth",
        participants=[Participant(person_id=pid, role="principal")],
        date=DateValue(value=date, precision="exact"),
    )


def _death(pid: str, date: str) -> Event:
    return Event(
        id=f"ev_death_{pid}",
        type="death",
        participants=[Participant(person_id=pid, role="principal")],
        date=DateValue(value=date, precision="exact"),
    )


def _find_section(report, heading_text: str):
    """Find the block immediately after a heading with the given text."""
    blocks = report.blocks
    for i, block in enumerate(blocks):
        if isinstance(block, HeadingBlock) and block.text == heading_text:
            if i + 1 < len(blocks):
                return blocks[i + 1]
    return None


def _items(report, heading_text: str) -> list[str]:
    section = _find_section(report, heading_text)
    if isinstance(section, ListBlock):
        return list(section.items)
    return []


class TestPartnerDeduplication:
    """BUG 1: a co-partner shared across families is listed once."""

    def test_shared_co_partner_listed_once(self):
        """A co-partner in both a biological and a derived foster family appears once."""
        mother = _person("m1", "Anna", "Ek")
        father = _person("f1", "Bo", "Ek")
        bio_child = _person("c1", "Erik", "Ek")
        foster_child = _person("c2", "Lisa", "Lund")

        bio_family = Family(
            id="fam_bio",
            partners=[
                FamilyPartner(person_id="m1", role="mother"),
                FamilyPartner(person_id="f1", role="father"),
            ],
            children=["c1"],
            parent_child_links=[
                ParentChildLink(child_id="c1", parent_id="m1", parentage_type="biological"),
                ParentChildLink(child_id="c1", parent_id="f1", parentage_type="biological"),
            ],
        )
        # Derived foster family with the SAME two partners.
        foster_family = Family(
            id="fam_foster",
            partners=[
                FamilyPartner(person_id="m1", role="mother"),
                FamilyPartner(person_id="f1", role="father"),
            ],
            children=["c2"],
            parent_child_links=[
                ParentChildLink(child_id="c2", parent_id="m1", parentage_type="foster"),
                ParentChildLink(child_id="c2", parent_id="f1", parentage_type="foster"),
            ],
            event_ids=["ev_fh"],
        )

        data = ProjectData(
            persons=[mother, father, bio_child, foster_child],
            families=[bio_family, foster_family],
        )

        report = generate_ansedel(data, "m1", project_folder=None)
        partner_items = _items(report, "Partner")

        # The father (co-partner) appears exactly once despite two shared families.
        matching = [item for item in partner_items if item.startswith("Bo Ek")]
        assert len(matching) == 1

    def test_distinct_partners_all_listed(self):
        """De-duplication does not drop genuinely distinct partners."""
        person = _person("p1", "Anna", "Ek")
        first = _person("f1", "Bo", "Ek")
        second = _person("s1", "Carl", "Nord")

        fam1 = Family(
            id="fam1",
            partners=[
                FamilyPartner(person_id="p1", role="mother"),
                FamilyPartner(person_id="f1", role="father"),
            ],
            children=[],
            parent_child_links=[],
        )
        fam2 = Family(
            id="fam2",
            partners=[
                FamilyPartner(person_id="p1", role="mother"),
                FamilyPartner(person_id="s1", role="father"),
            ],
            children=[],
            parent_child_links=[],
        )
        data = ProjectData(persons=[person, first, second], families=[fam1, fam2])

        report = generate_ansedel(data, "p1", project_folder=None)
        partner_items = _items(report, "Partner")

        assert any(item.startswith("Bo Ek") for item in partner_items)
        assert any(item.startswith("Carl Nord") for item in partner_items)


class TestChildBirthDeathFiltering:
    """BUG 2: foster/adoptive children do not appear under Barns födelse/död."""

    def test_foster_parent_excludes_foster_child_birth_death(self):
        """A foster parent gets no 'Barns födelse'/'Barns död' for the foster child."""
        parent = _person("p1", "Anna", "Ek")
        child = _person("c1", "Lisa", "Lund")

        foster_family = Family(
            id="fam_foster",
            partners=[FamilyPartner(person_id="p1", role="mother")],
            children=["c1"],
            parent_child_links=[
                ParentChildLink(child_id="c1", parent_id="p1", parentage_type="foster"),
            ],
            event_ids=["ev_fh"],
        )
        events = [
            _birth("p1", "1850"),
            _death("p1", "1920"),
            _birth("c1", "1870"),
            _death("c1", "1910"),
            Event(
                id="ev_fh",
                type="foster_home",
                participants=[
                    Participant(person_id="c1", role="fosterbarn"),
                    Participant(person_id="p1", role="fosterförälder"),
                ],
                date=DateValue(value="1878", precision="exact"),
            ),
        ]
        data = ProjectData(persons=[parent, child], families=[foster_family], events=events)

        report = generate_ansedel(data, "p1", project_folder=None)
        event_items = _items(report, "Händelser")

        assert not any("Barns födelse" in item for item in event_items)
        assert not any("Barns död" in item for item in event_items)

    def test_biological_parent_still_gets_child_birth_death(self):
        """A biological parent still gets the child's birth and death lines."""
        parent = _person("p1", "Anna", "Ek")
        child = _person("c1", "Erik", "Ek")

        bio_family = Family(
            id="fam_bio",
            partners=[FamilyPartner(person_id="p1", role="mother")],
            children=["c1"],
            parent_child_links=[
                ParentChildLink(child_id="c1", parent_id="p1", parentage_type="biological"),
            ],
        )
        events = [
            _birth("p1", "1850"),
            _death("p1", "1920"),
            _birth("c1", "1870"),
            _death("c1", "1910"),
        ]
        data = ProjectData(persons=[parent, child], families=[bio_family], events=events)

        report = generate_ansedel(data, "p1", project_folder=None)
        event_items = _items(report, "Händelser")

        assert any("Barns födelse (Erik Ek)" in item for item in event_items)
        assert any("Barns död (Erik Ek)" in item for item in event_items)


class TestPlacementEventPerspective:
    """BUG 3 + BUG 4: role-aware placement event rendering."""

    def test_parent_line_names_child_and_differs_from_child_line(self):
        """Parent and child see different lines; the parent line names the child."""
        parent = _person("p1", "Anna", "Ek")
        child = _person("c1", "Lisa", "Lund")

        foster_family = Family(
            id="fam_foster",
            partners=[FamilyPartner(person_id="p1", role="mother")],
            children=["c1"],
            parent_child_links=[
                ParentChildLink(child_id="c1", parent_id="p1", parentage_type="foster"),
            ],
            event_ids=["ev_fh"],
        )
        events = [
            Event(
                id="ev_fh",
                type="foster_home",
                participants=[
                    Participant(person_id="c1", role="fosterbarn"),
                    Participant(person_id="p1", role="fosterförälder"),
                ],
                date=DateValue(value="1878", precision="exact"),
            ),
        ]
        data = ProjectData(persons=[parent, child], families=[foster_family], events=events)

        parent_items = _items(generate_ansedel(data, "p1", project_folder=None), "Händelser")
        child_items = _items(generate_ansedel(data, "c1", project_folder=None), "Händelser")

        parent_line = next(item for item in parent_items if item.startswith("Fosterhem"))
        child_line = next(item for item in child_items if item.startswith("Fosterhem"))

        # Parent line names the foster child.
        assert "Lisa Lund" in parent_line
        assert "fosterbarn" in parent_line
        # Child line names the foster parent, not itself.
        assert "Anna Ek" in child_line
        assert "fosterföräldrar" in child_line
        # The two perspectives differ.
        assert parent_line != child_line

    def test_parent_with_multiple_foster_children_identifies_each(self):
        """A foster parent with two foster children sees each identified."""
        parent = _person("p1", "Anna", "Ek")
        child_a = _person("c1", "Lisa", "Lund")
        child_b = _person("c2", "Olle", "Berg")

        fam_a = Family(
            id="fam_a",
            partners=[FamilyPartner(person_id="p1", role="mother")],
            children=["c1"],
            parent_child_links=[
                ParentChildLink(child_id="c1", parent_id="p1", parentage_type="foster"),
            ],
            event_ids=["ev_a"],
        )
        fam_b = Family(
            id="fam_b",
            partners=[FamilyPartner(person_id="p1", role="mother")],
            children=["c2"],
            parent_child_links=[
                ParentChildLink(child_id="c2", parent_id="p1", parentage_type="foster"),
            ],
            event_ids=["ev_b"],
        )
        events = [
            Event(
                id="ev_a",
                type="foster_home",
                participants=[
                    Participant(person_id="c1", role="fosterbarn"),
                    Participant(person_id="p1", role="fosterförälder"),
                ],
                date=DateValue(value="1878", precision="exact"),
            ),
            Event(
                id="ev_b",
                type="foster_home",
                participants=[
                    Participant(person_id="c2", role="fosterbarn"),
                    Participant(person_id="p1", role="fosterförälder"),
                ],
                date=DateValue(value="1882", precision="exact"),
            ),
        ]
        data = ProjectData(
            persons=[parent, child_a, child_b], families=[fam_a, fam_b], events=events
        )

        parent_items = _items(generate_ansedel(data, "p1", project_folder=None), "Händelser")
        foster_lines = [item for item in parent_items if item.startswith("Fosterhem")]

        assert any("Lisa Lund" in line for line in foster_lines)
        assert any("Olle Berg" in line for line in foster_lines)

    def test_child_in_two_foster_families_gets_distinguishable_lines(self):
        """A child placed in two foster families gets two lines naming each family's parents."""
        child = _person("c1", "Lisa", "Lund")
        parent_a = _person("p1", "Anna", "Ek")
        parent_b = _person("p2", "Bo", "Berg")

        fam_a = Family(
            id="fam_a",
            partners=[FamilyPartner(person_id="p1", role="mother")],
            children=["c1"],
            parent_child_links=[
                ParentChildLink(child_id="c1", parent_id="p1", parentage_type="foster"),
            ],
            event_ids=["ev_a"],
        )
        fam_b = Family(
            id="fam_b",
            partners=[FamilyPartner(person_id="p2", role="father")],
            children=["c1"],
            parent_child_links=[
                ParentChildLink(child_id="c1", parent_id="p2", parentage_type="foster"),
            ],
            event_ids=["ev_b"],
        )
        events = [
            Event(
                id="ev_a",
                type="foster_home",
                participants=[
                    Participant(person_id="c1", role="fosterbarn"),
                    Participant(person_id="p1", role="fosterförälder"),
                ],
                date=DateValue(value="1878", precision="exact"),
            ),
            Event(
                id="ev_b",
                type="foster_home",
                participants=[
                    Participant(person_id="c1", role="fosterbarn"),
                    Participant(person_id="p2", role="fosterförälder"),
                ],
                date=DateValue(value="1884", precision="exact"),
            ),
        ]
        data = ProjectData(
            persons=[child, parent_a, parent_b], families=[fam_a, fam_b], events=events
        )

        child_items = _items(generate_ansedel(data, "c1", project_folder=None), "Händelser")
        foster_lines = [item for item in child_items if item.startswith("Fosterhem")]

        assert len(foster_lines) == 2
        assert any("Anna Ek" in line for line in foster_lines)
        assert any("Bo Berg" in line for line in foster_lines)
        # The two lines are distinguishable.
        assert foster_lines[0] != foster_lines[1]

    def test_adoption_parent_and_child_perspectives(self):
        """Adoption rendering mirrors foster rendering with adoptive wording."""
        parent = _person("p1", "Anna", "Ek")
        child = _person("c1", "Lisa", "Lund")

        adopt_family = Family(
            id="fam_adopt",
            partners=[FamilyPartner(person_id="p1", role="mother")],
            children=["c1"],
            parent_child_links=[
                ParentChildLink(child_id="c1", parent_id="p1", parentage_type="adoptive"),
            ],
            event_ids=["ev_adopt"],
        )
        events = [
            Event(
                id="ev_adopt",
                type="adoption",
                participants=[
                    Participant(person_id="c1", role="adopterad"),
                    Participant(person_id="p1", role="adoptivförälder"),
                ],
                date=DateValue(value="1878", precision="exact"),
            ),
        ]
        data = ProjectData(persons=[parent, child], families=[adopt_family], events=events)

        parent_items = _items(generate_ansedel(data, "p1", project_folder=None), "Händelser")
        child_items = _items(generate_ansedel(data, "c1", project_folder=None), "Händelser")

        parent_line = next(item for item in parent_items if item.startswith("Adoption"))
        child_line = next(item for item in child_items if item.startswith("Adoption"))

        assert "Lisa Lund" in parent_line
        assert "adoptivbarn" in parent_line
        assert "Anna Ek" in child_line
        assert "adoptivföräldrar" in child_line
        assert parent_line != child_line


class TestPlacementEventProperties:
    """Property test: parent and child perspectives always differ and name the right people.

    **Validates: Requirements (BUG 3, BUG 4 placement rendering)**
    """

    @given(
        child_given=st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll")), min_size=1, max_size=8),
        parent_given=st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll")), min_size=1, max_size=8),
        etype=st.sampled_from(["foster_home", "adoption"]),
    )
    def test_parent_and_child_lines_always_distinct(self, child_given, parent_given, etype):
        roles = {
            "foster_home": ("fosterbarn", "fosterförälder"),
            "adoption": ("adopterad", "adoptivförälder"),
        }[etype]
        child_role, parent_role = roles

        parent = _person("p1", parent_given, "Parent")
        child = _person("c1", child_given, "Child")

        parentage = "foster" if etype == "foster_home" else "adoptive"
        family = Family(
            id="fam",
            partners=[FamilyPartner(person_id="p1", role="mother")],
            children=["c1"],
            parent_child_links=[
                ParentChildLink(child_id="c1", parent_id="p1", parentage_type=parentage),
            ],
            event_ids=["ev"],
        )
        events = [
            Event(
                id="ev",
                type=etype,
                participants=[
                    Participant(person_id="c1", role=child_role),
                    Participant(person_id="p1", role=parent_role),
                ],
                date=DateValue(value="1878", precision="exact"),
            ),
        ]
        data = ProjectData(persons=[parent, child], families=[family], events=events)

        label = "Fosterhem" if etype == "foster_home" else "Adoption"
        parent_items = _items(generate_ansedel(data, "p1", project_folder=None), "Händelser")
        child_items = _items(generate_ansedel(data, "c1", project_folder=None), "Händelser")
        parent_line = next(item for item in parent_items if item.startswith(label))
        child_line = next(item for item in child_items if item.startswith(label))

        # Parent perspective names the child; child perspective names the parent.
        child_name = _format_name(child)
        parent_name = _format_name(parent)
        assert child_name in parent_line
        assert parent_name in child_line
        assert parent_line != child_line


def _format_name(person: Person) -> str:
    n = person.names[0]
    return " ".join(part for part in (n.given, n.surname) if part)
