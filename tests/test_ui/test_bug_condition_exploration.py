"""Property-based test for bug condition: RuntimeError on scene clear with stale PersonBoxItem references.

Feature: deleted-person-box-crash, Property 1: Bug Condition

This test encodes the EXPECTED behavior: calling set_active_person() after an initial
render (with a selected item) should NOT raise RuntimeError. When run on UNFIXED code,
this test is expected to FAIL, confirming the bug exists.

Bug flow:
1. DiagramPanel renders with person A → FamilyView._person_boxes populated
2. User clicks/selects a person box (item becomes selected in scene)
3. set_active_person("B") → _refresh_diagram() → scene.clear()
4. scene.clear() deselects items → selectionChanged fires
5. _on_scene_selection_changed() → deselect_all() → iterates stale _person_boxes
6. box.set_selected(False) → calls self.update() on deleted C++ object → RuntimeError

The RuntimeError is raised inside a Qt signal slot. The pytest-qt plugin captures
exceptions from Qt event loops and reports them as test errors at teardown.
This test additionally uses a direct shiboken6.isValid() check to assert the
bug condition: after scene.clear(), the _person_boxes references become stale.

**Validates: Requirements 1.1, 1.2**
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtWidgets import QApplication

from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.diagram_panel import DiagramPanel
from slaktbusken.ui.main_window import ViewType


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_person(person_id: str, given_name: str, surname: str) -> Person:
    """Create a Person with a single birth name."""
    return Person(
        id=person_id,
        sex="M",
        names=[Name(type="birth", given=given_name, surname=surname)],
    )


def _make_project_data(persons: list[Person], families: list[Family]) -> ProjectData:
    """Build a minimal ProjectData with the given persons and families."""
    main_id = persons[0].id if persons else None
    return ProjectData(
        project=ProjectMetadata(title="Test Project", main_person_id=main_id),
        persons=persons,
        families=families,
    )


# Strategy: generate simple person IDs as short alphabetic strings
person_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll",), whitelist_characters=""),
    min_size=3,
    max_size=8,
).map(lambda s: f"p_{s}")

person_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
    min_size=2,
    max_size=10,
)


class TestBugConditionExploration:
    """Property 1: Bug Condition - RuntimeError on scene clear with stale PersonBoxItem references.

    Tests that calling set_active_person() after an initial render (with a selected
    item in the scene) does NOT raise RuntimeError. On unfixed code, this WILL fail
    because scene.clear() triggers selectionChanged which calls deselect_all() on
    stale _person_boxes references.

    The bug requires that an item is SELECTED in the scene before scene.clear() is
    called. When scene.clear() deselects items, the selectionChanged signal fires,
    which calls deselect_all() on the stale _person_boxes list.

    **Validates: Requirements 1.1, 1.2**
    """

    @given(
        person_a_id=person_id_strategy,
        person_b_id=person_id_strategy,
        name_a=person_name_strategy,
        name_b=person_name_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_no_runtime_error_on_active_person_change(
        self,
        person_a_id: str,
        person_b_id: str,
        name_a: str,
        name_b: str,
    ) -> None:
        """Property 1: Changing the active person after initial render SHALL NOT
        raise RuntimeError from stale PersonBoxItem references.

        Flow: render diagram with person A → select a person box → change active
        person to person B → assert no RuntimeError is raised.

        The test monitors for RuntimeError by wrapping deselect_all() to detect
        calls on invalid C++ objects. On UNFIXED code, deselect_all() is called
        with stale _person_boxes references, triggering the RuntimeError.

        Feature: deleted-person-box-crash, Property 1: Bug Condition
        **Validates: Requirements 1.1, 1.2**
        """
        import shiboken6

        # Ensure person A and B have distinct IDs
        if person_a_id == person_b_id:
            person_b_id = person_b_id + "_2"

        # Create two persons
        person_a = _make_person(person_a_id, name_a, "Testsson")
        person_b = _make_person(person_b_id, name_b, "Testsson")

        # Create a family so the diagram has something to render
        family = Family(
            id="fam_1",
            partners=[
                FamilyPartner(person_id=person_a_id, role="husband"),
                FamilyPartner(person_id=person_b_id, role="wife"),
            ],
            children=[],
        )

        project_data = _make_project_data([person_a, person_b], [family])

        # Set up DiagramPanel with project data and config
        panel = DiagramPanel()
        panel.set_person_box_config(PersonBoxConfig(name=True))
        panel.switch_view(ViewType.FAMILY)
        panel.set_project_data(project_data)

        # Initial render: set active person to person A
        # This populates _person_boxes in FamilyView
        panel.set_active_person(person_a_id)

        # Verify that person boxes were actually created (precondition)
        assert len(panel._family_view._person_boxes) > 0, (
            "Precondition failed: FamilyView._person_boxes should be populated "
            "after initial render"
        )

        # Capture references to the current person boxes BEFORE the refresh.
        # These will become stale after scene.clear().
        stale_box_refs = list(panel._family_view._person_boxes)

        # Simulate user interaction: select a person box in the scene.
        # This is the critical precondition — the bug only manifests when an item
        # is SELECTED before scene.clear() is called, because scene.clear()
        # deselects items before destroying them, which fires selectionChanged.
        stale_box_refs[0].setSelected(True)

        # Track RuntimeErrors raised during deselect_all via monkeypatch
        runtime_errors: list[RuntimeError] = []
        original_deselect_all = panel._family_view.deselect_all

        def _capturing_deselect_all() -> None:
            """Wrapper that captures RuntimeError from deselect_all."""
            try:
                original_deselect_all()
            except RuntimeError as e:
                runtime_errors.append(e)
                raise

        panel._family_view.deselect_all = _capturing_deselect_all

        # NOW trigger the bug: change active person to person B
        # This calls _refresh_diagram() → scene.clear() → selectionChanged →
        # deselect_all() on stale _person_boxes → RuntimeError on unfixed code
        panel.set_active_person(person_b_id)

        # After scene.clear(), the old person box C++ objects are destroyed.
        # On UNFIXED code, _person_boxes still held stale refs DURING the clear,
        # and deselect_all() was called on them, triggering RuntimeError.
        #
        # Verify the property: no stale references should have been accessed
        # during the refresh cycle. We check this two ways:
        #
        # 1. No RuntimeError was captured during deselect_all
        assert len(runtime_errors) == 0, (
            f"RuntimeError raised during active person change — "
            f"deselect_all() accessed stale PersonBoxItem references after "
            f"scene.clear(): {runtime_errors[0]}"
        )

        # 2. The old references are now invalid (C++ objects destroyed),
        #    confirming that accessing them WOULD have caused RuntimeError
        #    if deselect_all() had been called with them still in _person_boxes.
        for old_box in stale_box_refs:
            assert not shiboken6.isValid(old_box), (
                "Expected old PersonBoxItem C++ objects to be destroyed after "
                "scene.clear(), but they are still valid"
            )
