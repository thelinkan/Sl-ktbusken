"""Unit tests for AncestryView derived-parentage rendering (task 6.2).

Covers routing the ancestry view through ``resolve_parent_display``:

* a one-parent foster Parent_Set draws a single ancestor box and NO
  second-parent placeholder, with a FOSTER connector (Req 3.8);
* a biological parent with one unknown parent still shows the placeholder,
  unchanged (Req 3.10);
* the "foster"/"adoptiv" badge text is present only when ``parentage_badge``
  is enabled (Req 3.6, 3.7).

The tests inspect scene items — PersonBoxItem, PlaceholderBoxItem, and
ConnectionLineItem.connection_type — following the existing test conventions
(session-scoped qapp fixture).
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QGraphicsScene

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.settings_io import DiagramSettings, PersonBoxConfig
from slaktbusken.ui.views.ancestry_view import AncestryView
from slaktbusken.ui.widgets.connection_line import ConnectionLineItem, ConnectionType
from slaktbusken.ui.widgets.person_box import PersonBoxItem
from slaktbusken.ui.widgets.placeholder_box import PlaceholderBoxItem


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _person(pid: str, given: str, sex: str = "U") -> Person:
    return Person(id=pid, sex=sex, names=[Name(type="birth", given=given, surname="Test")])


def _connection_types(scene: QGraphicsScene) -> list[ConnectionType]:
    return [
        item.connection_type
        for item in scene.items()
        if isinstance(item, ConnectionLineItem)
    ]


def _badges(scene: QGraphicsScene) -> list[str]:
    return [
        item.badge_text
        for item in scene.items()
        if isinstance(item, ConnectionLineItem) and item.badge_text
    ]


def _person_box_count(scene: QGraphicsScene) -> int:
    return sum(1 for item in scene.items() if isinstance(item, PersonBoxItem))


def _placeholder_count(scene: QGraphicsScene) -> int:
    return sum(1 for item in scene.items() if isinstance(item, PlaceholderBoxItem))


def _one_parent_foster_project() -> ProjectData:
    """Active child with a single foster parent via a derived family."""
    child = _person("p1", "Barn", "M")
    foster = _person("p2", "Foster", "F")
    foster_family = Family(
        id="f_foster",
        partners=[FamilyPartner(person_id="p2", role="partner")],
        children=["p1"],
        parent_child_links=[
            ParentChildLink(child_id="p1", parent_id="p2", parentage_type="foster"),
        ],
        event_ids=["ev1"],
    )
    return ProjectData(
        project=ProjectMetadata(title="Foster", main_person_id="p1"),
        persons=[child, foster],
        families=[foster_family],
    )


def _biological_one_unknown_project() -> ProjectData:
    """Active child with a father known and the mother unknown (biological)."""
    child = _person("p1", "Barn", "M")
    father = _person("p2", "Far", "M")
    bio_family = Family(
        id="f_bio",
        partners=[FamilyPartner(person_id="p2", role="father")],
        children=["p1"],
        parent_child_links=[
            ParentChildLink(child_id="p1", parent_id="p2", parentage_type="biological"),
        ],
    )
    return ProjectData(
        project=ProjectMetadata(title="Bio", main_person_id="p1"),
        persons=[child, father],
        families=[bio_family],
    )


class TestSingleParentFosterSet:
    """A one-parent foster set draws one box, no placeholder, FOSTER connector."""

    def test_single_foster_parent_no_second_placeholder(self) -> None:
        scene = QGraphicsScene()
        view = AncestryView()
        settings = DiagramSettings(parentage_show_level="non_biological")
        view.render(
            scene,
            _one_parent_foster_project(),
            "p1",
            PersonBoxConfig(name=True),
            depth=1,
            diagram_settings=settings,
        )

        # Active child + single foster parent = two person boxes.
        assert _person_box_count(scene) == 2
        # No second-parent placeholder is drawn for the absent partner.
        assert _placeholder_count(scene) == 0

    def test_single_foster_parent_uses_foster_connector(self) -> None:
        scene = QGraphicsScene()
        view = AncestryView()
        settings = DiagramSettings(parentage_show_level="non_biological")
        view.render(
            scene,
            _one_parent_foster_project(),
            "p1",
            PersonBoxConfig(name=True),
            depth=1,
            diagram_settings=settings,
        )

        conn_types = _connection_types(scene)
        assert conn_types, "expected at least one connector"
        # Every parent-child connector drawn for this child is FOSTER-styled;
        # no biological PARENT_CHILD connector is drawn.
        assert all(ct == ConnectionType.FOSTER for ct in conn_types)
        assert ConnectionType.PARENT_CHILD not in conn_types


class TestBiologicalUnknownParentUnchanged:
    """A biological parent with one unknown parent keeps its placeholder."""

    def test_biological_unknown_mother_shows_placeholder(self) -> None:
        scene = QGraphicsScene()
        view = AncestryView()
        view.render(
            scene,
            _biological_one_unknown_project(),
            "p1",
            PersonBoxConfig(name=True),
            depth=2,
        )

        # Active child + father = two boxes; the unknown mother is a placeholder.
        assert _person_box_count(scene) == 2
        assert _placeholder_count(scene) >= 1
        # Biological edges stay solid PARENT_CHILD; no FOSTER/ADOPTIVE styling.
        conn_types = _connection_types(scene)
        assert all(ct == ConnectionType.PARENT_CHILD for ct in conn_types)


class TestBadgeToggle:
    """Badge text appears only when parentage_badge is enabled."""

    def test_badge_present_when_enabled(self) -> None:
        scene = QGraphicsScene()
        view = AncestryView()
        settings = DiagramSettings(
            parentage_show_level="non_biological", parentage_badge=True
        )
        view.render(
            scene,
            _one_parent_foster_project(),
            "p1",
            PersonBoxConfig(name=True),
            depth=1,
            diagram_settings=settings,
        )

        badges = _badges(scene)
        assert badges == ["foster"]

    def test_badge_absent_when_disabled(self) -> None:
        scene = QGraphicsScene()
        view = AncestryView()
        settings = DiagramSettings(
            parentage_show_level="non_biological", parentage_badge=False
        )
        view.render(
            scene,
            _one_parent_foster_project(),
            "p1",
            PersonBoxConfig(name=True),
            depth=1,
            diagram_settings=settings,
        )

        assert _badges(scene) == []

    def test_biological_never_badged(self) -> None:
        scene = QGraphicsScene()
        view = AncestryView()
        settings = DiagramSettings(
            parentage_show_level="all", parentage_badge=True
        )
        view.render(
            scene,
            _biological_one_unknown_project(),
            "p1",
            PersonBoxConfig(name=True),
            depth=2,
            diagram_settings=settings,
        )

        assert _badges(scene) == []

