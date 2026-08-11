"""Unit tests for the residences section in the Ansedel report.

Tests that residence facts are listed with place, interval and role,
ordered by start.earliest (absent first), start.latest (absent first),
then place display name in Swedish alphabetical order.

Requirements: 11.7, 11.8
"""

from __future__ import annotations

from pathlib import Path

from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, ResidenceFact
from slaktbusken.reports.ansedel import generate_ansedel
from slaktbusken.reports.content import EmptyStateBlock, HeadingBlock, ListBlock


def _make_person():
    """Create a minimal person with required fields."""
    from slaktbusken.model.person import Name, Person

    return Person(id="p1", sex="M", names=[Name(type="birth", given="Erik", surname="Svensson")])


def _find_section(report, heading_text: str):
    """Find the block immediately after a heading with the given text."""
    blocks = report.blocks
    for i, block in enumerate(blocks):
        if isinstance(block, HeadingBlock) and block.text == heading_text:
            if i + 1 < len(blocks):
                return blocks[i + 1]
    return None


class TestAnsedelResidencesSection:
    """The Ansedel report lists residences per Requirement 11.8."""

    def test_no_residences_shows_empty_state(self):
        """When a person has no residence facts, the section shows an empty state."""
        data = ProjectData(persons=[_make_person()])
        report = generate_ansedel(data, "p1", project_folder=None)
        section = _find_section(report, "Boenden")
        assert isinstance(section, EmptyStateBlock)
        assert section.text == "Inga boenden registrerade."

    def test_single_residence_with_role(self):
        """A residence with a role renders place, interval and role."""
        place = Place(id="pl1", type="farm", name="Ekeby")
        fact = ResidenceFact(
            id="r1",
            person_id="p1",
            place_id="pl1",
            start=Endpoint(earliest="1840", latest="1840"),
            end=Endpoint(earliest="1846", latest="1846"),
            role_in_household="dräng",
        )
        data = ProjectData(
            persons=[_make_person()],
            places=[place],
            residences=[fact],
        )
        report = generate_ansedel(data, "p1", project_folder=None)
        section = _find_section(report, "Boenden")
        assert isinstance(section, ListBlock)
        assert len(section.items) == 1
        assert section.items[0] == "Ekeby, 1840\u20131846, dräng"

    def test_single_residence_without_role(self):
        """A residence with an empty role renders place and interval only."""
        place = Place(id="pl1", type="farm", name="Ekeby")
        fact = ResidenceFact(
            id="r1",
            person_id="p1",
            place_id="pl1",
            start=Endpoint(earliest="1840", latest="1840"),
            end=Endpoint(earliest="1870", latest="1870"),
        )
        data = ProjectData(
            persons=[_make_person()],
            places=[place],
            residences=[fact],
        )
        report = generate_ansedel(data, "p1", project_folder=None)
        section = _find_section(report, "Boenden")
        assert isinstance(section, ListBlock)
        assert section.items[0] == "Ekeby, 1840\u20131870"

    def test_ordering_by_start_earliest_ascending(self):
        """Residences are ordered by start.earliest ascending."""
        place = Place(id="pl1", type="farm", name="Gården")
        facts = [
            ResidenceFact(
                id="r1", person_id="p1", place_id="pl1",
                start=Endpoint(earliest="1860", latest="1860"),
                end=Endpoint(earliest="1870", latest="1870"),
            ),
            ResidenceFact(
                id="r2", person_id="p1", place_id="pl1",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1850", latest="1850"),
            ),
        ]
        data = ProjectData(
            persons=[_make_person()],
            places=[place],
            residences=facts,
        )
        report = generate_ansedel(data, "p1", project_folder=None)
        section = _find_section(report, "Boenden")
        assert isinstance(section, ListBlock)
        # r2 (1840) before r1 (1860)
        assert "1840" in section.items[0]
        assert "1860" in section.items[1]

    def test_absent_earliest_sorts_before_present(self):
        """An absent start.earliest sorts earlier than any present value."""
        place = Place(id="pl1", type="farm", name="Gården")
        facts = [
            ResidenceFact(
                id="r1", person_id="p1", place_id="pl1",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1850", latest="1850"),
            ),
            ResidenceFact(
                id="r2", person_id="p1", place_id="pl1",
                start=Endpoint(earliest=None, latest="1835"),
                end=Endpoint(earliest="1840", latest="1840"),
            ),
        ]
        data = ProjectData(
            persons=[_make_person()],
            places=[place],
            residences=facts,
        )
        report = generate_ansedel(data, "p1", project_folder=None)
        section = _find_section(report, "Boenden")
        assert isinstance(section, ListBlock)
        # r2 (absent earliest) comes first
        assert "senast 1835" in section.items[0]
        assert "1840" in section.items[1]

    def test_tie_on_earliest_breaks_on_latest(self):
        """When start.earliest ties, start.latest breaks the tie."""
        place = Place(id="pl1", type="farm", name="Gården")
        facts = [
            ResidenceFact(
                id="r1", person_id="p1", place_id="pl1",
                start=Endpoint(earliest="1840", latest="1845"),
                end=Endpoint(earliest="1870", latest="1870"),
            ),
            ResidenceFact(
                id="r2", person_id="p1", place_id="pl1",
                start=Endpoint(earliest="1840", latest="1842"),
                end=Endpoint(earliest="1860", latest="1860"),
            ),
        ]
        data = ProjectData(
            persons=[_make_person()],
            places=[place],
            residences=facts,
        )
        report = generate_ansedel(data, "p1", project_folder=None)
        section = _find_section(report, "Boenden")
        assert isinstance(section, ListBlock)
        # r2 (latest=1842) before r1 (latest=1845)
        assert "1842" in section.items[0]
        assert "1845" in section.items[1]

    def test_tie_on_dates_breaks_on_place_name_swedish_order(self):
        """When start.earliest and start.latest tie, place name in Swedish order breaks the tie."""
        places = [
            Place(id="pl1", type="farm", name="Östra"),
            Place(id="pl2", type="farm", name="Åkern"),
        ]
        facts = [
            ResidenceFact(
                id="r1", person_id="p1", place_id="pl1",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1850", latest="1850"),
            ),
            ResidenceFact(
                id="r2", person_id="p1", place_id="pl2",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1860", latest="1860"),
            ),
        ]
        data = ProjectData(
            persons=[_make_person()],
            places=places,
            residences=facts,
        )
        report = generate_ansedel(data, "p1", project_folder=None)
        section = _find_section(report, "Boenden")
        assert isinstance(section, ListBlock)
        # Swedish order: Å < Ö, so Åkern before Östra
        assert "Åkern" in section.items[0]
        assert "Östra" in section.items[1]

    def test_interval_rendered_through_formatter(self):
        """The interval comes from format_residence_interval (Requirement 11.7)."""
        place = Place(id="pl1", type="farm", name="Ekeby")
        # Open endpoint: only latest present on start → "senast 1840"
        fact = ResidenceFact(
            id="r1",
            person_id="p1",
            place_id="pl1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1870"),
            role_in_household="piga",
        )
        data = ProjectData(
            persons=[_make_person()],
            places=[place],
            residences=[fact],
        )
        report = generate_ansedel(data, "p1", project_folder=None)
        section = _find_section(report, "Boenden")
        assert isinstance(section, ListBlock)
        # format_residence_line produces: "Ekeby, senast 1840–tidigast 1870, piga"
        assert section.items[0] == "Ekeby, senast 1840\u2013tidigast 1870, piga"

    def test_other_person_residences_excluded(self):
        """Only the target person's residences appear."""
        place = Place(id="pl1", type="farm", name="Ekeby")
        facts = [
            ResidenceFact(
                id="r1", person_id="p1", place_id="pl1",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1850", latest="1850"),
            ),
            ResidenceFact(
                id="r2", person_id="p2", place_id="pl1",
                start=Endpoint(earliest="1830", latest="1830"),
                end=Endpoint(earliest="1840", latest="1840"),
            ),
        ]
        data = ProjectData(
            persons=[_make_person()],
            places=[place],
            residences=facts,
        )
        report = generate_ansedel(data, "p1", project_folder=None)
        section = _find_section(report, "Boenden")
        assert isinstance(section, ListBlock)
        assert len(section.items) == 1

    def test_unknown_both_endpoints(self):
        """A residence with both endpoints unknown renders 'okänd period'."""
        place = Place(id="pl1", type="farm", name="Ekeby")
        fact = ResidenceFact(
            id="r1",
            person_id="p1",
            place_id="pl1",
            start=Endpoint(),
            end=Endpoint(),
        )
        data = ProjectData(
            persons=[_make_person()],
            places=[place],
            residences=[fact],
        )
        report = generate_ansedel(data, "p1", project_folder=None)
        section = _find_section(report, "Boenden")
        assert isinstance(section, ListBlock)
        assert section.items[0] == "Ekeby, okänd period"

    def test_unresolved_place_uses_place_id(self):
        """When the place doesn't exist, the place_id is used as display name."""
        fact = ResidenceFact(
            id="r1",
            person_id="p1",
            place_id="missing_place",
            start=Endpoint(earliest="1840", latest="1840"),
            end=Endpoint(earliest="1850", latest="1850"),
        )
        data = ProjectData(
            persons=[_make_person()],
            residences=[fact],
        )
        report = generate_ansedel(data, "p1", project_folder=None)
        section = _find_section(report, "Boenden")
        assert isinstance(section, ListBlock)
        assert "missing_place" in section.items[0]
