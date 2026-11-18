"""Tests for foster/adoptive-aware edge rendering in the descendants view.

Task 6.3: route ``descendants_view.py`` through the shared
``resolve_parent_display`` resolver so that a parent→child connector reflects
the child's parentage relationship to *this* parent, and so that
Show_Level / override / fallback gate which children are drawn consistently
with the other diagram views (Req 3.5, 3.8–3.10, 4.6).

These are Qt-scene tests: they build a tiny project, render it into a real
``QGraphicsScene``, and assert on the ``ConnectionLineItem`` connection types
(and badge text) present in the scene.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QGraphicsScene

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.settings_io import DiagramSettings, PersonBoxConfig
from slaktbusken.ui.views.descendants_view import DescendantsView
from slaktbusken.ui.widgets.connection_line import ConnectionLineItem, ConnectionType


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _person(pid: str, sex: str = "U") -> Person:
    return Person(id=pid, sex=sex, names=[Name(type="birth", given=pid, surname="T")])


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


def _project_with_child(parentage_type: str) -> ProjectData:
    """Parent ``parent`` with one child linked by ``parentage_type``."""
    parent = _person("parent", "M")
    child = _person("child", "F")
    family = Family(
        id="f1",
        partners=[FamilyPartner(person_id="parent", role="father")],
        children=["child"],
        parent_child_links=[
            ParentChildLink(
                child_id="child", parent_id="parent", parentage_type=parentage_type
            )
        ],
    )
    return ProjectData(
        project=ProjectMetadata(title="T"),
        persons=[parent, child],
        families=[family],
    )


def _render(
    project: ProjectData,
    settings: DiagramSettings | None = None,
) -> QGraphicsScene:
    scene = QGraphicsScene()
    view = DescendantsView()
    view.render(
        scene,
        project,
        "parent",
        PersonBoxConfig(),
        depth=3,
        diagram_settings=settings,
    )
    return scene


# ---------------------------------------------------------------------------
# Biological descendants unchanged
# ---------------------------------------------------------------------------


def test_biological_child_drawn_with_parent_child_connector(qapp):
    """A biological child is drawn with the solid PARENT_CHILD connector and no
    badge, exactly as before (Req 3.4)."""
    scene = _render(_project_with_child("biological"))

    types = _connection_types(scene)
    assert types, "biological child should produce connector segments"
    assert all(t == ConnectionType.PARENT_CHILD for t in types)
    assert ConnectionType.FOSTER not in types
    assert ConnectionType.ADOPTIVE not in types
    assert _badges(scene) == []


def test_biological_child_default_settings_matches_none(qapp):
    """Passing no DiagramSettings keeps biological behaviour (safe default)."""
    scene_none = _render(_project_with_child("biological"), settings=None)
    scene_bio = _render(
        _project_with_child("biological"),
        settings=DiagramSettings(parentage_show_level="biological"),
    )
    assert _connection_types(scene_none) == _connection_types(scene_bio)


# ---------------------------------------------------------------------------
# Foster child under its foster parent
# ---------------------------------------------------------------------------


def test_foster_child_drawn_with_foster_connector_under_all(qapp):
    """Under Show_Level 'all', a foster child under its foster parent draws a
    FOSTER connector (Req 3.5)."""
    scene = _render(
        _project_with_child("foster"),
        settings=DiagramSettings(parentage_show_level="all"),
    )
    types = _connection_types(scene)
    assert ConnectionType.FOSTER in types
    assert ConnectionType.PARENT_CHILD not in types


def test_foster_child_badge_when_enabled(qapp):
    """With the badge setting on, the foster connector carries a 'foster'
    badge (Req 3.6)."""
    scene = _render(
        _project_with_child("foster"),
        settings=DiagramSettings(
            parentage_show_level="all", parentage_badge=True
        ),
    )
    assert "foster" in _badges(scene)


def test_foster_child_no_badge_when_disabled(qapp):
    """With the badge setting off, no badge is painted (Req 3.7)."""
    scene = _render(
        _project_with_child("foster"),
        settings=DiagramSettings(
            parentage_show_level="all", parentage_badge=False
        ),
    )
    assert _badges(scene) == []


def test_adoptive_child_drawn_with_adoptive_connector_and_badge(qapp):
    """An adoptive child draws an ADOPTIVE connector; badge reads 'adoptiv'."""
    scene = _render(
        _project_with_child("adoptive"),
        settings=DiagramSettings(
            parentage_show_level="all", parentage_badge=True
        ),
    )
    types = _connection_types(scene)
    assert ConnectionType.ADOPTIVE in types
    assert "adoptiv" in _badges(scene)


# ---------------------------------------------------------------------------
# Show-level / override gating (Req 4.6)
# ---------------------------------------------------------------------------


def test_pure_foster_child_not_drawn_under_biological(qapp):
    """Under Show_Level 'biological' with fallback off, a purely-foster child
    is NOT shown as a descendant through its foster parent — no connector at
    all (Req 4.6)."""
    scene = _render(
        _project_with_child("foster"),
        settings=DiagramSettings(
            parentage_show_level="biological", parentage_fallback=False
        ),
    )
    assert _connection_types(scene) == []
    # The "no descendants" fallback message is shown instead.
    from PySide6.QtWidgets import QGraphicsTextItem

    assert any(isinstance(i, QGraphicsTextItem) for i in scene.items())


def test_foster_child_shown_under_biological_with_fallback(qapp):
    """With fallback on and no biological parents, a foster child surfaces even
    under Show_Level 'biological' (Req 6.2)."""
    scene = _render(
        _project_with_child("foster"),
        settings=DiagramSettings(
            parentage_show_level="biological", parentage_fallback=True
        ),
    )
    assert ConnectionType.FOSTER in _connection_types(scene)


def test_override_forces_foster_edge_under_biological(qapp):
    """A per-child override of 'foster' makes the foster edge draw even under
    Show_Level 'biological' (Req 5.2)."""
    project = _project_with_child("foster")
    project.connection_overrides["child"] = "foster"
    scene = _render(
        project, settings=DiagramSettings(parentage_show_level="biological")
    )
    assert ConnectionType.FOSTER in _connection_types(scene)


def test_mixed_parents_biological_only_under_biological(qapp):
    """A child with both a biological and a foster parent under Show_Level
    'biological' draws only the biological edge (to the bio parent)."""
    bio_parent = _person("bio", "M")
    foster_parent = _person("fos", "F")
    child = _person("child", "F")
    bio_family = Family(
        id="f_bio",
        partners=[FamilyPartner(person_id="bio", role="father")],
        children=["child"],
        parent_child_links=[
            ParentChildLink(
                child_id="child", parent_id="bio", parentage_type="biological"
            )
        ],
    )
    foster_family = Family(
        id="f_fos",
        partners=[FamilyPartner(person_id="fos", role="mother")],
        children=["child"],
        parent_child_links=[
            ParentChildLink(
                child_id="child", parent_id="fos", parentage_type="foster"
            )
        ],
    )
    project = ProjectData(
        project=ProjectMetadata(title="T"),
        persons=[bio_parent, foster_parent, child],
        families=[bio_family, foster_family],
    )

    # Render from the biological parent: child is drawn (biological edge).
    scene_bio = QGraphicsScene()
    DescendantsView().render(
        scene_bio,
        project,
        "bio",
        PersonBoxConfig(),
        depth=3,
        diagram_settings=DiagramSettings(parentage_show_level="biological"),
    )
    types_bio = _connection_types(scene_bio)
    assert types_bio and all(t == ConnectionType.PARENT_CHILD for t in types_bio)

    # Render from the foster parent: under 'biological' the child is NOT a
    # descendant through the foster edge (fallback does not apply — the child
    # has a biological parent), so no connector is drawn.
    scene_fos = QGraphicsScene()
    DescendantsView().render(
        scene_fos,
        project,
        "fos",
        PersonBoxConfig(),
        depth=3,
        diagram_settings=DiagramSettings(parentage_show_level="biological"),
    )
    assert _connection_types(scene_fos) == []
