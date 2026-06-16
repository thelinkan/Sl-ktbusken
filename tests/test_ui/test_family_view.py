"""Unit tests for the FamilyView diagram renderer.

Tests rendering logic, placeholder creation, and selection handling
for the family view diagram.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QGraphicsScene

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.views.family_view import (
    FamilyView,
    _build_display_data,
    _find_parent_family,
    _find_partner_families,
    _find_person,
    _get_display_name,
)
from slaktbusken.ui.widgets.person_box import PersonBoxItem
from slaktbusken.ui.widgets.placeholder_box import PlaceholderBoxItem, PlaceholderRole


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_project_data() -> ProjectData:
    """Create a sample project with a family structure for testing."""
    father = Person(id="p1", sex="male", names=[Name(type="birth", given="Erik", surname="Svensson")])
    mother = Person(id="p2", sex="female", names=[Name(type="birth", given="Anna", surname="Karlsson")])
    active = Person(id="p3", sex="male", names=[Name(type="birth", given="Karl", surname="Svensson")])
    sibling = Person(id="p4", sex="female", names=[Name(type="birth", given="Lisa", surname="Svensson")])
    partner = Person(id="p5", sex="female", names=[Name(type="birth", given="Maria", surname="Johansson")])
    child = Person(id="p6", sex="male", names=[Name(type="birth", given="Sven", surname="Svensson")])

    # Parent family: father + mother, children: active + sibling
    parent_family = Family(
        id="f1",
        partners=[
            FamilyPartner(person_id="p1", role="father"),
            FamilyPartner(person_id="p2", role="mother"),
        ],
        children=["p3", "p4"],
    )

    # Active person's own family: active + partner, child
    own_family = Family(
        id="f2",
        partners=[
            FamilyPartner(person_id="p3", role="father"),
            FamilyPartner(person_id="p5", role="mother"),
        ],
        children=["p6"],
    )

    birth_event = Event(
        id="e1",
        type="birth",
        participants=[Participant(person_id="p3", role="subject")],
        date=DateValue(value="1875-04-12", precision="exact"),
    )

    return ProjectData(
        project=ProjectMetadata(title="Test", main_person_id="p3"),
        persons=[father, mother, active, sibling, partner, child],
        families=[parent_family, own_family],
        events=[birth_event],
    )


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_find_person_found(self) -> None:
        """_find_person returns the person with matching ID."""
        data = _make_project_data()
        person = _find_person(data, "p3")
        assert person is not None
        assert person.id == "p3"

    def test_find_person_not_found(self) -> None:
        """_find_person returns None for unknown ID."""
        data = _make_project_data()
        assert _find_person(data, "nonexistent") is None

    def test_find_parent_family(self) -> None:
        """_find_parent_family returns the family where person is a child."""
        data = _make_project_data()
        family = _find_parent_family(data, "p3")
        assert family is not None
        assert family.id == "f1"

    def test_find_parent_family_none(self) -> None:
        """_find_parent_family returns None for a root ancestor."""
        data = _make_project_data()
        family = _find_parent_family(data, "p1")
        assert family is None

    def test_find_partner_families(self) -> None:
        """_find_partner_families returns families where person is partner."""
        data = _make_project_data()
        families = _find_partner_families(data, "p3")
        assert len(families) == 1
        assert families[0].id == "f2"

    def test_find_partner_families_none(self) -> None:
        """_find_partner_families returns empty list if no partner family."""
        data = _make_project_data()
        families = _find_partner_families(data, "p6")  # child only
        assert families == []

    def test_get_display_name(self) -> None:
        """_get_display_name formats given + surname."""
        person = Person(id="p1", sex="male", names=[Name(type="birth", given="Erik", surname="Svensson")])
        assert _get_display_name(person) == "Erik Svensson"

    def test_get_display_name_no_names(self) -> None:
        """_get_display_name returns (okänd) when no names."""
        person = Person(id="p1", sex="male", names=[])
        assert _get_display_name(person) == "(okänd)"

    def test_build_display_data_with_birth(self) -> None:
        """_build_display_data extracts birth date from events."""
        data = _make_project_data()
        person = _find_person(data, "p3")
        display = _build_display_data(person, data)
        assert display["name"] == "Karl Svensson"
        assert display["birth_date"] == "1875-04-12"


# ---------------------------------------------------------------------------
# FamilyView render tests
# ---------------------------------------------------------------------------


class TestFamilyViewRender:
    """Tests for FamilyView.render() diagram population."""

    def test_render_populates_scene(self) -> None:
        """Rendering adds items to the scene."""
        data = _make_project_data()
        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()

        view.render(scene, data, "p3", config)

        # Should have person boxes and connection lines
        items = scene.items()
        assert len(items) > 0

    def test_render_creates_person_boxes(self) -> None:
        """Rendering creates PersonBoxItems for family members."""
        data = _make_project_data()
        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()

        view.render(scene, data, "p3", config)

        person_boxes = view.get_person_boxes()
        person_ids = {box.person_id for box in person_boxes}
        # Active person, father, mother, sibling, partner, child
        assert "p3" in person_ids  # active
        assert "p1" in person_ids  # father
        assert "p2" in person_ids  # mother
        assert "p4" in person_ids  # sibling
        assert "p5" in person_ids  # partner
        assert "p6" in person_ids  # child

    def test_render_creates_child_placeholder(self) -> None:
        """Rendering adds a CHILD placeholder for adding new children."""
        data = _make_project_data()
        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()

        view.render(scene, data, "p3", config)

        placeholders = view.get_placeholder_boxes()
        child_placeholders = [
            p for p in placeholders if p.role == PlaceholderRole.CHILD
        ]
        assert len(child_placeholders) >= 1
        assert child_placeholders[0].family_id == "f2"

    def test_render_no_parent_placeholders_when_both_present(self) -> None:
        """No parent placeholders when both father and mother exist."""
        data = _make_project_data()
        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()

        view.render(scene, data, "p3", config)

        placeholders = view.get_placeholder_boxes()
        parent_placeholders = [
            p
            for p in placeholders
            if p.role in (PlaceholderRole.FATHER, PlaceholderRole.MOTHER)
        ]
        assert len(parent_placeholders) == 0

    def test_render_father_placeholder_when_missing(self) -> None:
        """Father placeholder appears when no father in parent family."""
        data = _make_project_data()
        # Remove father from parent family
        data.families[0].partners = [
            FamilyPartner(person_id="p2", role="mother"),
        ]
        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()

        view.render(scene, data, "p3", config)

        placeholders = view.get_placeholder_boxes()
        father_placeholders = [
            p for p in placeholders if p.role == PlaceholderRole.FATHER
        ]
        assert len(father_placeholders) == 1

    def test_render_mother_placeholder_when_missing(self) -> None:
        """Mother placeholder appears when no mother in parent family."""
        data = _make_project_data()
        # Remove mother from parent family
        data.families[0].partners = [
            FamilyPartner(person_id="p1", role="father"),
        ]
        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()

        view.render(scene, data, "p3", config)

        placeholders = view.get_placeholder_boxes()
        mother_placeholders = [
            p for p in placeholders if p.role == PlaceholderRole.MOTHER
        ]
        assert len(mother_placeholders) == 1

    def test_render_nonexistent_person_does_nothing(self) -> None:
        """Rendering with a non-existent person ID adds nothing."""
        data = _make_project_data()
        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()

        view.render(scene, data, "nonexistent", config)

        assert len(scene.items()) == 0


# ---------------------------------------------------------------------------
# FamilyView selection tests
# ---------------------------------------------------------------------------


class TestFamilyViewSelection:
    """Tests for FamilyView click and selection handling."""

    def test_handle_click_selects_person(self) -> None:
        """handle_click selects the clicked person's box."""
        data = _make_project_data()
        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()
        view.render(scene, data, "p3", config)

        view.handle_click("p1")

        assert view.selected_person_id == "p1"
        for box in view.get_person_boxes():
            if box.person_id == "p1":
                assert box.is_selected
            else:
                assert not box.is_selected

    def test_handle_click_deselects_previous(self) -> None:
        """handle_click deselects previously selected person."""
        data = _make_project_data()
        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()
        view.render(scene, data, "p3", config)

        view.handle_click("p1")
        view.handle_click("p2")

        assert view.selected_person_id == "p2"
        for box in view.get_person_boxes():
            if box.person_id == "p2":
                assert box.is_selected
            else:
                assert not box.is_selected

    def test_deselect_all(self) -> None:
        """deselect_all clears all selections."""
        data = _make_project_data()
        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()
        view.render(scene, data, "p3", config)

        view.handle_click("p1")
        view.deselect_all()

        assert view.selected_person_id is None
        for box in view.get_person_boxes():
            assert not box.is_selected
