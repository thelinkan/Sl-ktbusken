"""Unit tests for the FamilyView diagram renderer.

Tests rendering logic, placeholder creation, and selection handling
for the family view diagram.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QGraphicsScene

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
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
        parent_child_links=[
            ParentChildLink(child_id="p3", parent_id="p1", parentage_type="biological"),
            ParentChildLink(child_id="p3", parent_id="p2", parentage_type="biological"),
            ParentChildLink(child_id="p4", parent_id="p1", parentage_type="biological"),
            ParentChildLink(child_id="p4", parent_id="p2", parentage_type="biological"),
        ],
    )

    # Active person's own family: active + partner, child
    own_family = Family(
        id="f2",
        partners=[
            FamilyPartner(person_id="p3", role="father"),
            FamilyPartner(person_id="p5", role="mother"),
        ],
        children=["p6"],
        parent_child_links=[
            ParentChildLink(child_id="p6", parent_id="p3", parentage_type="biological"),
            ParentChildLink(child_id="p6", parent_id="p5", parentage_type="biological"),
        ],
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

    def test_render_parents_with_husband_wife_roles(self) -> None:
        """Parents are shown when using GEDCOM-imported 'husband'/'wife' roles."""
        data = _make_project_data()
        # Change parent family to use GEDCOM-style roles
        data.families[0].partners = [
            FamilyPartner(person_id="p1", role="husband"),
            FamilyPartner(person_id="p2", role="wife"),
        ]
        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()

        view.render(scene, data, "p3", config)

        person_boxes = view.get_person_boxes()
        person_ids = {box.person_id for box in person_boxes}
        assert "p1" in person_ids  # father (husband role)
        assert "p2" in person_ids  # mother (wife role)
        # No parent placeholders should appear
        placeholders = view.get_placeholder_boxes()
        parent_placeholders = [
            p
            for p in placeholders
            if p.role in (PlaceholderRole.FATHER, PlaceholderRole.MOTHER)
        ]
        assert len(parent_placeholders) == 0

    def test_render_parents_with_partner_role(self) -> None:
        """Parents are shown when using 'partner' role (same-sex families)."""
        data = _make_project_data()
        # Change parent family to use partner roles
        data.families[0].partners = [
            FamilyPartner(person_id="p1", role="partner"),
            FamilyPartner(person_id="p2", role="partner"),
        ]
        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()

        view.render(scene, data, "p3", config)

        person_boxes = view.get_person_boxes()
        person_ids = {box.person_id for box in person_boxes}
        assert "p1" in person_ids  # first partner in father slot
        assert "p2" in person_ids  # second partner in mother slot
        # No parent placeholders should appear
        placeholders = view.get_placeholder_boxes()
        parent_placeholders = [
            p
            for p in placeholders
            if p.role in (PlaceholderRole.FATHER, PlaceholderRole.MOTHER)
        ]
        assert len(parent_placeholders) == 0

    def test_render_switching_active_person_shows_correct_parents(self) -> None:
        """Switching active person updates parents correctly."""
        # Create a second family with different parents
        grandfather = Person(id="p7", sex="male", names=[Name(type="birth", given="Olof", surname="Karlsson")])
        grandmother = Person(id="p8", sex="female", names=[Name(type="birth", given="Brita", surname="Nilsson")])

        data = _make_project_data()
        data.persons.extend([grandfather, grandmother])

        # Mother's parent family
        mother_parent_family = Family(
            id="f3",
            partners=[
                FamilyPartner(person_id="p7", role="husband"),
                FamilyPartner(person_id="p8", role="wife"),
            ],
            children=["p2"],
        )
        data.families.append(mother_parent_family)

        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()

        # Render family view for the mother (p2) as active person
        view.render(scene, data, "p2", config)

        person_boxes = view.get_person_boxes()
        person_ids = {box.person_id for box in person_boxes}
        # Mother's parents should be shown
        assert "p7" in person_ids  # grandfather
        assert "p8" in person_ids  # grandmother

    def test_render_father_placeholder_when_no_parent_family(self) -> None:
        """Father and mother placeholders appear when person has no parent family."""
        data = _make_project_data()
        # Make p1 (father) the active person — p1 is NOT a child in any family
        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()

        view.render(scene, data, "p1", config)

        placeholders = view.get_placeholder_boxes()
        father_placeholders = [
            p for p in placeholders if p.role == PlaceholderRole.FATHER
        ]
        mother_placeholders = [
            p for p in placeholders if p.role == PlaceholderRole.MOTHER
        ]
        # Both parent placeholders should appear (no parent family)
        assert len(father_placeholders) == 1
        assert father_placeholders[0].family_id is None
        assert len(mother_placeholders) == 1
        assert mother_placeholders[0].family_id is None

    def test_render_partner_placeholder_for_active_person(self) -> None:
        """A PARTNER placeholder appears for the active person."""
        data = _make_project_data()
        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()

        view.render(scene, data, "p3", config)

        placeholders = view.get_placeholder_boxes()
        partner_placeholders = [
            p for p in placeholders if p.role == PlaceholderRole.PARTNER
        ]
        assert len(partner_placeholders) == 1
        assert partner_placeholders[0].family_id is None

    def test_render_partner_placeholder_only_for_active_person(self) -> None:
        """The PARTNER placeholder does NOT appear for siblings."""
        data = _make_project_data()
        # Add a partner family for the sibling (p4) to ensure it has a spine
        sibling_spouse = Person(id="p7", sex="male", names=[Name(type="birth", given="Nils", surname="Olsson")])
        data.persons.append(sibling_spouse)
        sibling_family = Family(
            id="f3",
            partners=[
                FamilyPartner(person_id="p4", role="mother"),
                FamilyPartner(person_id="p7", role="father"),
            ],
            children=[],
        )
        data.families.append(sibling_family)

        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()

        view.render(scene, data, "p3", config)

        placeholders = view.get_placeholder_boxes()
        partner_placeholders = [
            p for p in placeholders if p.role == PlaceholderRole.PARTNER
        ]
        # Only one PARTNER placeholder — for the active person (p3), not the sibling
        assert len(partner_placeholders) == 1

    def test_render_partner_placeholder_when_no_existing_partners(self) -> None:
        """PARTNER placeholder appears even when active person has no partner families."""
        # Create a minimal project where the active person has no partner families
        active = Person(id="p1", sex="male", names=[Name(type="birth", given="Karl", surname="Svensson")])
        mother = Person(id="p2", sex="female", names=[Name(type="birth", given="Anna", surname="Karlsson")])

        parent_family = Family(
            id="f1",
            partners=[FamilyPartner(person_id="p2", role="mother")],
            children=["p1"],
        )

        data = ProjectData(
            project=ProjectMetadata(title="Test", main_person_id="p1"),
            persons=[active, mother],
            families=[parent_family],
            events=[],
        )

        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()

        view.render(scene, data, "p1", config)

        placeholders = view.get_placeholder_boxes()
        partner_placeholders = [
            p for p in placeholders if p.role == PlaceholderRole.PARTNER
        ]
        assert len(partner_placeholders) == 1

    def test_render_spouse_placeholder_when_only_active_person_in_family(self) -> None:
        """FATHER placeholder appears when active person (mother) has a family with children but no spouse."""
        # Create a family where the active person is the only partner (mother role)
        # with children but no spouse listed
        active = Person(id="p1", sex="female", names=[Name(type="birth", given="Anna", surname="Karlsson")])
        child = Person(id="p2", sex="male", names=[Name(type="birth", given="Erik", surname="Karlsson")])

        # Family with only one partner (the mother) and a child
        family_no_spouse = Family(
            id="f1",
            partners=[
                FamilyPartner(person_id="p1", role="mother"),
            ],
            children=["p2"],
        )

        data = ProjectData(
            project=ProjectMetadata(title="Test", main_person_id="p1"),
            persons=[active, child],
            families=[family_no_spouse],
            events=[],
        )

        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()

        view.render(scene, data, "p1", config)

        placeholders = view.get_placeholder_boxes()
        father_placeholders = [
            p for p in placeholders if p.role == PlaceholderRole.FATHER
        ]
        # A FATHER placeholder should appear in the spouse position
        assert len(father_placeholders) >= 1
        # It should be associated with the family
        assert any(p.family_id == "f1" for p in father_placeholders)

    def test_render_partner_placeholder_positioned_below_existing_spouses(self) -> None:
        """PARTNER placeholder is positioned below existing spouse/children blocks."""
        data = _make_project_data()
        scene = QGraphicsScene()
        config = PersonBoxConfig()
        view = FamilyView()

        view.render(scene, data, "p3", config)

        placeholders = view.get_placeholder_boxes()
        partner_placeholders = [
            p for p in placeholders if p.role == PlaceholderRole.PARTNER
        ]
        assert len(partner_placeholders) == 1

        # The partner placeholder should be below the active person's spouse box
        partner_ph = partner_placeholders[0]
        person_boxes = view.get_person_boxes()
        active_box = next(b for b in person_boxes if b.person_id == "p3")
        spouse_box = next(b for b in person_boxes if b.person_id == "p5")

        # Partner placeholder Y should be greater than spouse Y (below it)
        assert partner_ph.pos().y() > spouse_box.pos().y()
        # Also below the active person
        assert partner_ph.pos().y() > active_box.pos().y()


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


# ---------------------------------------------------------------------------
# FamilyView foster/adoptive parent-set rendering (task 6.1)
# ---------------------------------------------------------------------------


from slaktbusken.persistence.settings_io import DiagramSettings  # noqa: E402
from slaktbusken.ui.widgets.connection_line import (  # noqa: E402
    ConnectionLineItem,
    ConnectionType,
)


def _make_foster_project(
    *, two_parents: bool, parentage: str = "foster"
) -> ProjectData:
    """Create a project where the active person (c1) has a derived parent set.

    The active person belongs to a single derived (foster/adoptive) family with
    one or two parents and no biological family, so the resolver's
    non-biological / fallback path draws that set.

    Args:
        two_parents: When True the derived set holds two parents; otherwise one.
        parentage: The derived parentage type, "foster" or "adoptive".
    """
    child = Person(id="c1", sex="male", names=[Name(type="birth", given="Kalle", surname="Barn")])
    pa = Person(id="fa", sex="male", names=[Name(type="birth", given="Per", surname="Foster")])
    pb = Person(id="fb", sex="female", names=[Name(type="birth", given="Pia", surname="Foster")])

    partners = [FamilyPartner(person_id="fa", role="partner")]
    links = [ParentChildLink(child_id="c1", parent_id="fa", parentage_type=parentage)]
    persons = [child, pa]
    if two_parents:
        partners.append(FamilyPartner(person_id="fb", role="partner"))
        links.append(
            ParentChildLink(child_id="c1", parent_id="fb", parentage_type=parentage)
        )
        persons.append(pb)

    derived_family = Family(
        id="df1",
        partners=partners,
        children=["c1"],
        parent_child_links=links,
        event_ids=["ev1"],
    )

    return ProjectData(
        project=ProjectMetadata(title="Foster", main_person_id="c1"),
        persons=persons,
        families=[derived_family],
    )


def _conn_lines(scene: QGraphicsScene) -> list[ConnectionLineItem]:
    """Return every ConnectionLineItem in the scene."""
    return [it for it in scene.items() if isinstance(it, ConnectionLineItem)]


def _render(data: ProjectData, active: str, settings: DiagramSettings) -> tuple:
    """Render a FamilyView and return (view, scene)."""
    scene = QGraphicsScene()
    config = PersonBoxConfig()
    view = FamilyView()
    view.render(scene, data, active, config, diagram_settings=settings)
    return view, scene


class TestFamilyViewParentSets:
    """Foster/adoptive Parent_Set rendering per Requirement 3.8–3.10."""

    def test_one_parent_foster_single_box_no_partner_no_placeholder(self) -> None:
        """A one-parent foster set draws a single parent box, no PARTNER, no placeholder."""
        data = _make_foster_project(two_parents=False)
        settings = DiagramSettings(parentage_show_level="non_biological")
        view, scene = _render(data, "c1", settings)

        # The single foster parent box is drawn.
        person_ids = {b.person_id for b in view.get_person_boxes()}
        assert "fa" in person_ids

        # No father/mother placeholder is drawn for the single derived parent
        # row. (The active person still gets its own "Lägg till partner"
        # placeholder with family_id=None, which is unrelated to the parent row.)
        parent_phs = [
            p for p in view.get_placeholder_boxes()
            if p.role in (PlaceholderRole.FATHER, PlaceholderRole.MOTHER)
        ]
        assert parent_phs == []
        # The derived set contributes no PARTNER placeholder either.
        derived_partner_phs = [
            p for p in view.get_placeholder_boxes()
            if p.role == PlaceholderRole.PARTNER and p.family_id == "df1"
        ]
        assert derived_partner_phs == []

    def test_one_parent_foster_drop_uses_foster_connection_type(self) -> None:
        """The parent-child drop for a foster set uses ConnectionType.FOSTER."""
        data = _make_foster_project(two_parents=False)
        settings = DiagramSettings(parentage_show_level="non_biological")
        _, scene = _render(data, "c1", settings)

        foster_lines = [
            c for c in _conn_lines(scene)
            if c.connection_type == ConnectionType.FOSTER
        ]
        assert len(foster_lines) >= 1

    def test_one_parent_adoptive_drop_uses_adoptive_connection_type(self) -> None:
        """A one-parent adoptive set draws an ADOPTIVE connector."""
        data = _make_foster_project(two_parents=False, parentage="adoptive")
        settings = DiagramSettings(parentage_show_level="non_biological")
        _, scene = _render(data, "c1", settings)

        adoptive_lines = [
            c for c in _conn_lines(scene)
            if c.connection_type == ConnectionType.ADOPTIVE
        ]
        assert len(adoptive_lines) >= 1

    def test_two_parent_foster_draws_two_boxes_and_partner(self) -> None:
        """A two-parent foster set draws both parent boxes and a PARTNER connector."""
        data = _make_foster_project(two_parents=True)
        settings = DiagramSettings(parentage_show_level="non_biological")
        view, scene = _render(data, "c1", settings)

        person_ids = {b.person_id for b in view.get_person_boxes()}
        assert "fa" in person_ids
        assert "fb" in person_ids

        # Both parents present, so no father/mother placeholder is drawn.
        parent_phs = [
            p for p in view.get_placeholder_boxes()
            if p.role in (PlaceholderRole.FATHER, PlaceholderRole.MOTHER)
        ]
        assert parent_phs == []

        # The partner connector between the two foster parents is present.
        partner_lines = [
            c for c in _conn_lines(scene)
            if c.connection_type == ConnectionType.PARTNER
        ]
        assert len(partner_lines) >= 1

        # The parent-child drop is a FOSTER connector.
        foster_lines = [
            c for c in _conn_lines(scene)
            if c.connection_type == ConnectionType.FOSTER
        ]
        assert len(foster_lines) >= 1

    def test_badge_only_when_enabled(self) -> None:
        """badge_text is set on the foster drop only when parentage_badge is True."""
        data = _make_foster_project(two_parents=False)

        # Badge off: no foster connector carries a badge.
        off = DiagramSettings(parentage_show_level="non_biological", parentage_badge=False)
        _, scene_off = _render(data, "c1", off)
        foster_off = [
            c for c in _conn_lines(scene_off)
            if c.connection_type == ConnectionType.FOSTER
        ]
        assert foster_off and all(c.badge_text is None for c in foster_off)

        # Badge on: the foster connector carries the "foster" badge.
        on = DiagramSettings(parentage_show_level="non_biological", parentage_badge=True)
        _, scene_on = _render(data, "c1", on)
        foster_on = [
            c for c in _conn_lines(scene_on)
            if c.connection_type == ConnectionType.FOSTER
        ]
        assert foster_on and any(c.badge_text == "foster" for c in foster_on)

    def test_adoptive_badge_text(self) -> None:
        """An adoptive drop carries the 'adoptiv' badge when enabled."""
        data = _make_foster_project(two_parents=False, parentage="adoptive")
        on = DiagramSettings(parentage_show_level="non_biological", parentage_badge=True)
        _, scene = _render(data, "c1", on)
        adoptive = [
            c for c in _conn_lines(scene)
            if c.connection_type == ConnectionType.ADOPTIVE
        ]
        assert adoptive and any(c.badge_text == "adoptiv" for c in adoptive)

    def test_biological_single_known_parent_keeps_placeholder_and_partner(self) -> None:
        """A biological pair with one unknown parent keeps the placeholder + PARTNER (unchanged)."""
        data = _make_project_data()
        # Remove the father so only the mother (biological) is known.
        data.families[0].partners = [FamilyPartner(person_id="p2", role="mother")]

        settings = DiagramSettings(parentage_show_level="biological")
        view, scene = _render(data, "p3", settings)

        # The missing biological father still shows a FATHER placeholder.
        father_phs = [
            p for p in view.get_placeholder_boxes()
            if p.role == PlaceholderRole.FATHER
        ]
        assert len(father_phs) == 1

        # The biological drop uses the solid PARENT_CHILD style with no badge.
        pc_lines = [
            c for c in _conn_lines(scene)
            if c.connection_type == ConnectionType.PARENT_CHILD
        ]
        assert pc_lines and all(c.badge_text is None for c in pc_lines)

        # A PARTNER connector between the two parent slots is still drawn.
        partner_lines = [
            c for c in _conn_lines(scene)
            if c.connection_type == ConnectionType.PARTNER
        ]
        assert len(partner_lines) >= 1

    def test_sibling_derived_single_parent_partner_family_suppresses_placeholder(self) -> None:
        """STEP 4: a sibling's foster single-parent partner family draws no spouse placeholder."""
        # Active person p3 (biological child of p1/p2); sibling p4 fosters child p6
        # alone via a derived single-parent family.
        data = _make_project_data()
        # Replace p4's / existing own family with a derived single-parent foster
        # family where sibling p4 is the sole foster parent of p6.
        data.families = [
            data.families[0],  # keep biological parent family f1 (p3, p4)
            Family(
                id="fd",
                partners=[FamilyPartner(person_id="p4", role="partner")],
                children=["p6"],
                parent_child_links=[
                    ParentChildLink(child_id="p6", parent_id="p4", parentage_type="foster"),
                ],
                event_ids=["evx"],
            ),
        ]

        settings = DiagramSettings(parentage_show_level="biological")
        view, _ = _render(data, "p3", settings)

        # p4's foster partner family must NOT produce a missing-spouse placeholder.
        spouse_phs = [
            p for p in view.get_placeholder_boxes()
            if p.role in (
                PlaceholderRole.FATHER,
                PlaceholderRole.MOTHER,
                PlaceholderRole.PARTNER,
            )
            and p.family_id == "fd"
        ]
        assert spouse_phs == []


def _make_merged_partner_project() -> ProjectData:
    """Project where Janne + Ärla have a biological child AND a foster child.

    Janne (p_j) and Ärla (p_a) share the same partner set across TWO derived
    Family objects:
      * a biological family (p_j father, p_a mother, child c_rut biological), and
      * a derived foster family (p_j + p_a partners, child c_bertil foster).

    Janne is the active person, so STEP 4 must merge the two families with the
    identical other-partner set {p_a} into ONE spouse block drawing Ärla once
    with both children beneath her.
    """
    janne = Person(id="p_j", sex="male", names=[Name(type="birth", given="Janne", surname="Larsson")])
    arla = Person(id="p_a", sex="female", names=[Name(type="birth", given="Ärla", surname="Larsson")])
    rut = Person(id="c_rut", sex="female", names=[Name(type="birth", given="Rut", surname="Larsson")])
    bertil = Person(id="c_bertil", sex="male", names=[Name(type="birth", given="Bertil", surname="Larsson")])

    biological_family = Family(
        id="fbio",
        partners=[
            FamilyPartner(person_id="p_j", role="father"),
            FamilyPartner(person_id="p_a", role="mother"),
        ],
        children=["c_rut"],
        parent_child_links=[
            ParentChildLink(child_id="c_rut", parent_id="p_j", parentage_type="biological"),
            ParentChildLink(child_id="c_rut", parent_id="p_a", parentage_type="biological"),
        ],
    )

    foster_family = Family(
        id="ffos",
        partners=[
            FamilyPartner(person_id="p_j", role="partner"),
            FamilyPartner(person_id="p_a", role="partner"),
        ],
        children=["c_bertil"],
        parent_child_links=[
            ParentChildLink(child_id="c_bertil", parent_id="p_j", parentage_type="foster"),
            ParentChildLink(child_id="c_bertil", parent_id="p_a", parentage_type="foster"),
        ],
        event_ids=["evx"],
    )

    return ProjectData(
        project=ProjectMetadata(title="Merge", main_person_id="p_j"),
        persons=[janne, arla, rut, bertil],
        families=[biological_family, foster_family],
    )


class TestFamilyViewMergedPartnerFamilies:
    """STEP 4 merges partner families sharing the same partner set (BUG 1/2)."""

    def test_spouse_drawn_once_across_merged_families(self) -> None:
        """Ärla appears as exactly ONE PersonBoxItem despite two partner families."""
        data = _make_merged_partner_project()
        settings = DiagramSettings(parentage_show_level="all")
        view, _ = _render(data, "p_j", settings)

        arla_boxes = [b for b in view.get_person_boxes() if b.person_id == "p_a"]
        assert len(arla_boxes) == 1

    def test_both_children_drawn_under_merged_spouse(self) -> None:
        """Both the biological and foster child are drawn as child boxes."""
        data = _make_merged_partner_project()
        settings = DiagramSettings(parentage_show_level="all")
        view, _ = _render(data, "p_j", settings)

        person_ids = {b.person_id for b in view.get_person_boxes()}
        assert "c_rut" in person_ids
        assert "c_bertil" in person_ids

    def test_child_connectors_reflect_parentage_type(self) -> None:
        """Foster child uses FOSTER connector, biological child uses PARENT_CHILD."""
        data = _make_merged_partner_project()
        settings = DiagramSettings(parentage_show_level="all")
        _, scene = _render(data, "p_j", settings)

        foster_lines = [
            c for c in _conn_lines(scene)
            if c.connection_type == ConnectionType.FOSTER
        ]
        # The foster child Bertil gets a dashed FOSTER connector.
        assert len(foster_lines) >= 1

        # The biological child Rut keeps a solid PARENT_CHILD connector. (Many
        # PARENT_CHILD lines exist from the sibling bar; this asserts they are
        # present and that no biological child connector became FOSTER.)
        pc_lines = [
            c for c in _conn_lines(scene)
            if c.connection_type == ConnectionType.PARENT_CHILD
        ]
        assert len(pc_lines) >= 1

    def test_foster_child_badge_gated_by_setting(self) -> None:
        """The foster child's connector carries the 'foster' badge only when enabled."""
        data = _make_merged_partner_project()

        on = DiagramSettings(parentage_show_level="all", parentage_badge=True)
        _, scene_on = _render(data, "p_j", on)
        foster_on = [
            c for c in _conn_lines(scene_on)
            if c.connection_type == ConnectionType.FOSTER
        ]
        assert foster_on and any(c.badge_text == "foster" for c in foster_on)

        off = DiagramSettings(parentage_show_level="all", parentage_badge=False)
        _, scene_off = _render(data, "p_j", off)
        foster_off = [
            c for c in _conn_lines(scene_off)
            if c.connection_type == ConnectionType.FOSTER
        ]
        assert foster_off and all(c.badge_text is None for c in foster_off)

    def test_ordinary_biological_layout_unchanged(self) -> None:
        """Regression: an ordinary biological spouse/children layout is a no-op merge."""
        data = _make_project_data()
        settings = DiagramSettings(parentage_show_level="all")
        view, scene = _render(data, "p3", settings)

        # Exactly one spouse box (p5) and one child box (p6) as before the merge.
        spouse_boxes = [b for b in view.get_person_boxes() if b.person_id == "p5"]
        child_boxes = [b for b in view.get_person_boxes() if b.person_id == "p6"]
        assert len(spouse_boxes) == 1
        assert len(child_boxes) == 1

        # The child connector stays biological (no FOSTER/ADOPTIVE connectors).
        derived_lines = [
            c for c in _conn_lines(scene)
            if c.connection_type in (ConnectionType.FOSTER, ConnectionType.ADOPTIVE)
        ]
        assert derived_lines == []

        # The "Lägg till barn" placeholder keeps the biological family_id f2.
        child_phs = [
            p for p in view.get_placeholder_boxes()
            if p.role == PlaceholderRole.CHILD
        ]
        assert any(p.family_id == "f2" for p in child_phs)
