"""Tests for foster/adoptive styling of the relationship dialog mini-diagram.

The Släktskapsberäknare mini-diagram draws parent→child "drop" connectors.
These tests verify that foster and adoptive drops are rendered DASHED in
their own colour (mirroring the main diagram views), while biological
drops stay solid grey.

Validates: Requirements 3 (dashed foster/adoptive styling)
"""

from __future__ import annotations

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsPathItem

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.dialogs.relationship_dialog import RelationshipDialog
from slaktbusken.ui.widgets.connection_line import _ADOPTIVE_COLOR, _FOSTER_COLOR


def _make_person(person_id: str, given: str, surname: str, sex: str = "M") -> Person:
    """Create a minimal person with a single birth name."""
    return Person(
        id=person_id,
        sex=sex,
        names=[Name(type="birth", given=given, surname=surname)],
    )


def _dashed_path_items(dialog: RelationshipDialog) -> list[QGraphicsPathItem]:
    """Return every QGraphicsPathItem in the scene drawn with a dashed pen."""
    return [
        item
        for item in dialog._scene.items()
        if isinstance(item, QGraphicsPathItem)
        and item.pen().style() == Qt.PenStyle.DashLine
    ]


def _solid_connector_path_items(
    dialog: RelationshipDialog,
) -> list[QGraphicsPathItem]:
    """Return solid-grey connector path items (the structural/biological pen).

    Node boxes are also QGraphicsPathItems but use blue/green/orange pens,
    so we filter on the grey connector colour (#555555) to isolate
    parent-child connectors and structural bars.
    """
    grey = Qt.PenStyle.SolidLine
    items = []
    for item in dialog._scene.items():
        if not isinstance(item, QGraphicsPathItem):
            continue
        pen = item.pen()
        if pen.style() != grey:
            continue
        if pen.color().getRgb()[:3] == (0x55, 0x55, 0x55):
            items.append(item)
    return items


def _foster_scenario() -> ProjectData:
    """Project mirroring the screenshot: Bertil is Janne's foster child.

    Janne has a biological child Rut; Rut has a biological child Anders.
    Thus Anders is foster-brorson/systerson to Bertil via Janne.
    """
    persons = [
        _make_person("janne", "Janne", "Svensson"),
        _make_person("bertil", "Bertil", "Svensson"),
        _make_person("rut", "Rut", "Svensson", sex="F"),
        _make_person("anders", "Anders", "Svensson"),
    ]
    family_janne = Family(
        id="fam_janne",
        partners=[FamilyPartner(person_id="janne", role="father")],
        children=["bertil", "rut"],
        parent_child_links=[
            ParentChildLink(child_id="bertil", parent_id="janne",
                            parentage_type="foster"),
            ParentChildLink(child_id="rut", parent_id="janne",
                            parentage_type="biological"),
        ],
    )
    family_rut = Family(
        id="fam_rut",
        partners=[FamilyPartner(person_id="rut", role="mother")],
        children=["anders"],
        parent_child_links=[
            ParentChildLink(child_id="anders", parent_id="rut",
                            parentage_type="biological"),
        ],
    )
    return ProjectData(persons=persons, families=[family_janne, family_rut])


def _adoptive_scenario() -> ProjectData:
    """Janne adopts Bertil; Rut is Janne's biological child with child Anders."""
    persons = [
        _make_person("janne", "Janne", "Svensson"),
        _make_person("bertil", "Bertil", "Svensson"),
        _make_person("rut", "Rut", "Svensson", sex="F"),
        _make_person("anders", "Anders", "Svensson"),
    ]
    family_janne = Family(
        id="fam_janne",
        partners=[FamilyPartner(person_id="janne", role="father")],
        children=["bertil", "rut"],
        parent_child_links=[
            ParentChildLink(child_id="bertil", parent_id="janne",
                            parentage_type="adoptive"),
            ParentChildLink(child_id="rut", parent_id="janne",
                            parentage_type="biological"),
        ],
    )
    family_rut = Family(
        id="fam_rut",
        partners=[FamilyPartner(person_id="rut", role="mother")],
        children=["anders"],
        parent_child_links=[
            ParentChildLink(child_id="anders", parent_id="rut",
                            parentage_type="biological"),
        ],
    )
    return ProjectData(persons=persons, families=[family_janne, family_rut])


def _biological_scenario() -> ProjectData:
    """All-biological: Janne → Rut → Anders, and Janne → Bertil."""
    persons = [
        _make_person("janne", "Janne", "Svensson"),
        _make_person("bertil", "Bertil", "Svensson"),
        _make_person("rut", "Rut", "Svensson", sex="F"),
        _make_person("anders", "Anders", "Svensson"),
    ]
    family_janne = Family(
        id="fam_janne",
        partners=[FamilyPartner(person_id="janne", role="father")],
        children=["bertil", "rut"],
        parent_child_links=[
            ParentChildLink(child_id="bertil", parent_id="janne",
                            parentage_type="biological"),
            ParentChildLink(child_id="rut", parent_id="janne",
                            parentage_type="biological"),
        ],
    )
    family_rut = Family(
        id="fam_rut",
        partners=[FamilyPartner(person_id="rut", role="mother")],
        children=["anders"],
        parent_child_links=[
            ParentChildLink(child_id="anders", parent_id="rut",
                            parentage_type="biological"),
        ],
    )
    return ProjectData(persons=persons, families=[family_janne, family_rut])


class TestRelationshipDiagramParentageStyling:
    """Foster/adoptive drops dashed in colour; biological drops solid."""

    def test_foster_drop_is_dashed_in_foster_colour(self, qtbot) -> None:
        """A foster parent→child drop renders dashed in the foster colour."""
        data = _foster_scenario()
        dialog = RelationshipDialog(data)
        qtbot.addWidget(dialog)

        paths = dialog._calculator.find_relationships("bertil", "anders")
        assert paths, "Expected at least one relationship path"

        dialog._draw_generational_diagram(paths)

        dashed = _dashed_path_items(dialog)
        foster_rgb = _FOSTER_COLOR.getRgb()[:3]
        foster_dashed = [
            item for item in dashed
            if item.pen().color().getRgb()[:3] == foster_rgb
        ]
        assert foster_dashed, (
            "Expected at least one dashed foster-coloured connector"
        )

    def test_adoptive_drop_is_dashed_in_adoptive_colour(self, qtbot) -> None:
        """An adoptive parent→child drop renders dashed in adoptive colour."""
        data = _adoptive_scenario()
        dialog = RelationshipDialog(data)
        qtbot.addWidget(dialog)

        paths = dialog._calculator.find_relationships("bertil", "anders")
        assert paths, "Expected at least one relationship path"

        dialog._draw_generational_diagram(paths)

        dashed = _dashed_path_items(dialog)
        adoptive_rgb = _ADOPTIVE_COLOR.getRgb()[:3]
        adoptive_dashed = [
            item for item in dashed
            if item.pen().color().getRgb()[:3] == adoptive_rgb
        ]
        assert adoptive_dashed, (
            "Expected at least one dashed adoptive-coloured connector"
        )

    def test_biological_only_has_no_dashed_connectors(self, qtbot) -> None:
        """A fully biological relationship draws only solid connectors."""
        data = _biological_scenario()
        dialog = RelationshipDialog(data)
        qtbot.addWidget(dialog)

        paths = dialog._calculator.find_relationships("bertil", "anders")
        assert paths, "Expected at least one relationship path"

        dialog._draw_generational_diagram(paths)

        dashed = _dashed_path_items(dialog)
        assert dashed == [], (
            "Biological-only relationship should not draw dashed drops"
        )
        # Sanity: solid grey connectors ARE present (the drops/trunk/bars).
        assert _solid_connector_path_items(dialog), (
            "Expected solid connector segments for a biological relationship"
        )
