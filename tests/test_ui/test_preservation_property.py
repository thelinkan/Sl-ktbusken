"""Property-based tests for preservation: Selection and deselect behavior unchanged for valid person boxes.

Feature: deleted-person-box-crash, Property 2: Preservation

These tests verify that the existing selection/deselection behavior works correctly
for valid (non-deleted) person boxes across all three view types. They are written
BEFORE the fix is implemented and should PASS on unfixed code, confirming the
baseline behavior to preserve.

The tests cover the non-bug-condition cases: interactions with currently-rendered,
valid person boxes (where `isBugCondition` returns false).

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from PySide6.QtWidgets import QApplication, QGraphicsScene

from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.views.ancestry_view import AncestryView
from slaktbusken.ui.views.descendants_view import DescendantsView
from slaktbusken.ui.views.family_view import FamilyView


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Generate person IDs as short alphabetic strings with a prefix
person_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll",)),
    min_size=2,
    max_size=6,
).map(lambda s: f"p_{s}")

person_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
    min_size=2,
    max_size=8,
)


@st.composite
def person_list_strategy(draw, min_size=2, max_size=6):
    """Generate a list of unique persons with valid IDs and names.

    Returns a tuple of (persons, person_ids) where person_ids is the list of IDs.
    """
    count = draw(st.integers(min_value=min_size, max_value=max_size))
    persons = []
    ids = []
    for i in range(count):
        # Use index-based IDs to guarantee uniqueness
        pid = f"p_{i}"
        given_name = draw(person_name_strategy)
        surname = draw(person_name_strategy)
        sex = draw(st.sampled_from(["male", "female"]))
        person = Person(
            id=pid,
            sex=sex,
            names=[Name(type="birth", given=given_name, surname=surname)],
        )
        persons.append(person)
        ids.append(pid)
    return persons, ids


@st.composite
def family_view_data_strategy(draw):
    """Generate project data suitable for FamilyView rendering.

    Creates a family with at least 2 partners and possibly children,
    ensuring valid data for FamilyView.render().
    """
    persons, ids = draw(person_list_strategy(min_size=3, max_size=6))

    # First two persons form a couple, rest are children
    father_id = ids[0]
    mother_id = ids[1]
    active_id = ids[2]  # active person is a child
    children_ids = ids[2:]

    family = Family(
        id="fam_1",
        partners=[
            FamilyPartner(person_id=father_id, role="father"),
            FamilyPartner(person_id=mother_id, role="mother"),
        ],
        children=children_ids,
    )

    project_data = ProjectData(
        project=ProjectMetadata(title="Test", main_person_id=active_id),
        persons=persons,
        families=[family],
    )

    return project_data, active_id, ids


# ---------------------------------------------------------------------------
# Test Class: deselect_all preservation
# ---------------------------------------------------------------------------


class TestDeselectAllPreservation:
    """Property 2: Preservation - deselect_all() on valid person boxes.

    For all valid (non-deleted) person box lists, `deselect_all()` sets
    all boxes to unselected state without error.

    **Validates: Requirements 3.4**
    """

    @given(data=family_view_data_strategy())
    @settings(max_examples=30, deadline=None)
    def test_deselect_all_family_view(self, data) -> None:
        """For all valid person box lists in FamilyView, deselect_all() sets
        all boxes to unselected state.

        **Validates: Requirements 3.4**
        """
        project_data, active_id, all_ids = data

        scene = QGraphicsScene()
        config = PersonBoxConfig(name=True)
        view = FamilyView()
        view.render(scene, project_data, active_id, config)

        # Precondition: there are person boxes rendered
        boxes = view.get_person_boxes()
        assume(len(boxes) > 0)

        # First select a box to ensure deselect_all has something to deselect
        first_box_id = boxes[0].person_id
        view.handle_click(first_box_id)

        # Now deselect all
        view.deselect_all()

        # Property: all boxes should be unselected
        assert view.selected_person_id is None
        for box in view.get_person_boxes():
            assert not box.is_selected, (
                f"Box {box.person_id} should be deselected after deselect_all()"
            )

    @given(data=family_view_data_strategy())
    @settings(max_examples=30, deadline=None)
    def test_deselect_all_ancestry_view(self, data) -> None:
        """For all valid person box lists in AncestryView, deselect_all() sets
        all boxes to unselected state.

        **Validates: Requirements 3.4**
        """
        project_data, active_id, all_ids = data

        scene = QGraphicsScene()
        config = PersonBoxConfig(name=True)
        view = AncestryView()
        view.render(scene, project_data, active_id, config, depth=2)

        boxes = view.get_person_boxes()
        assume(len(boxes) > 0)

        # Select a box then deselect all
        first_box_id = boxes[0].person_id
        view.handle_click(first_box_id)
        view.deselect_all()

        # Property: all boxes should be unselected
        assert view.selected_person_id is None
        for box in view.get_person_boxes():
            assert not box.is_selected, (
                f"Box {box.person_id} should be deselected after deselect_all()"
            )

    @given(data=family_view_data_strategy())
    @settings(max_examples=30, deadline=None)
    def test_deselect_all_descendants_view(self, data) -> None:
        """For all valid person box lists in DescendantsView, deselect_all() sets
        all boxes to unselected state.

        **Validates: Requirements 3.4**
        """
        project_data, active_id, all_ids = data

        scene = QGraphicsScene()
        config = PersonBoxConfig(name=True)
        view = DescendantsView()
        # Use first person (a parent) to get descendants
        parent_id = all_ids[0]
        view.render(scene, project_data, parent_id, config, depth=2)

        boxes = view.get_person_boxes()
        assume(len(boxes) > 0)

        # Select a box then deselect all
        first_box_id = boxes[0].person_id
        view.handle_click(first_box_id)
        view.deselect_all()

        # Property: all boxes should be unselected
        assert view.selected_person_id is None
        for box in view.get_person_boxes():
            assert not box.is_selected, (
                f"Box {box.person_id} should be deselected after deselect_all()"
            )


# ---------------------------------------------------------------------------
# Test Class: handle_click preservation
# ---------------------------------------------------------------------------


class TestHandleClickPreservation:
    """Property 2: Preservation - handle_click() selects exactly the matching box.

    For all valid person box lists and any person_id present in the list,
    handle_click(person_id) selects exactly the matching box and deselects others.

    **Validates: Requirements 3.1**
    """

    @given(data=family_view_data_strategy())
    @settings(max_examples=30, deadline=None)
    def test_handle_click_selects_exactly_one_family_view(self, data) -> None:
        """For all valid person box lists in FamilyView and any person_id,
        handle_click(person_id) selects exactly the matching box.

        **Validates: Requirements 3.1**
        """
        project_data, active_id, all_ids = data

        scene = QGraphicsScene()
        config = PersonBoxConfig(name=True)
        view = FamilyView()
        view.render(scene, project_data, active_id, config)

        boxes = view.get_person_boxes()
        assume(len(boxes) > 0)

        # Pick a random box to click (use the last one to vary from deselect tests)
        target_id = boxes[-1].person_id

        view.handle_click(target_id)

        # Property: exactly the target box is selected
        assert view.selected_person_id == target_id
        for box in view.get_person_boxes():
            if box.person_id == target_id:
                assert box.is_selected, (
                    f"Box {box.person_id} should be selected after handle_click"
                )
            else:
                assert not box.is_selected, (
                    f"Box {box.person_id} should NOT be selected after "
                    f"handle_click({target_id})"
                )

    @given(data=family_view_data_strategy())
    @settings(max_examples=30, deadline=None)
    def test_handle_click_selects_exactly_one_ancestry_view(self, data) -> None:
        """For all valid person box lists in AncestryView and any person_id,
        handle_click(person_id) selects exactly the matching box.

        **Validates: Requirements 3.1**
        """
        project_data, active_id, all_ids = data

        scene = QGraphicsScene()
        config = PersonBoxConfig(name=True)
        view = AncestryView()
        view.render(scene, project_data, active_id, config, depth=2)

        boxes = view.get_person_boxes()
        assume(len(boxes) > 0)

        target_id = boxes[-1].person_id

        view.handle_click(target_id)

        assert view.selected_person_id == target_id
        for box in view.get_person_boxes():
            if box.person_id == target_id:
                assert box.is_selected
            else:
                assert not box.is_selected

    @given(data=family_view_data_strategy())
    @settings(max_examples=30, deadline=None)
    def test_handle_click_selects_exactly_one_descendants_view(self, data) -> None:
        """For all valid person box lists in DescendantsView and any person_id,
        handle_click(person_id) selects exactly the matching box.

        **Validates: Requirements 3.1**
        """
        project_data, active_id, all_ids = data

        scene = QGraphicsScene()
        config = PersonBoxConfig(name=True)
        view = DescendantsView()
        parent_id = all_ids[0]
        view.render(scene, project_data, parent_id, config, depth=2)

        boxes = view.get_person_boxes()
        assume(len(boxes) > 0)

        target_id = boxes[-1].person_id

        view.handle_click(target_id)

        assert view.selected_person_id == target_id
        for box in view.get_person_boxes():
            if box.person_id == target_id:
                assert box.is_selected
            else:
                assert not box.is_selected

    @given(data=family_view_data_strategy())
    @settings(max_examples=30, deadline=None)
    def test_handle_click_then_different_deselects_previous(self, data) -> None:
        """Clicking one box then another deselects the first — preserved across views.

        **Validates: Requirements 3.1**
        """
        project_data, active_id, all_ids = data

        scene = QGraphicsScene()
        config = PersonBoxConfig(name=True)
        view = FamilyView()
        view.render(scene, project_data, active_id, config)

        boxes = view.get_person_boxes()
        assume(len(boxes) >= 2)

        first_id = boxes[0].person_id
        second_id = boxes[1].person_id
        assume(first_id != second_id)

        # Click first, then second
        view.handle_click(first_id)
        view.handle_click(second_id)

        # Property: only second is selected
        assert view.selected_person_id == second_id
        for box in view.get_person_boxes():
            if box.person_id == second_id:
                assert box.is_selected
            else:
                assert not box.is_selected


# ---------------------------------------------------------------------------
# Test Class: View switching preservation
# ---------------------------------------------------------------------------


class TestViewSwitchingPreservation:
    """Property 2: Preservation - View switching renders correctly.

    For all view types (FamilyView, AncestryView, DescendantsView),
    selection/deselection on valid boxes works identically across views.

    **Validates: Requirements 3.2**
    """

    @given(data=family_view_data_strategy())
    @settings(max_examples=30, deadline=None)
    def test_selection_works_identically_across_views(self, data) -> None:
        """Selection and deselection works identically across all three view types.

        For any valid project data, rendering in each view and performing
        handle_click + deselect_all produces consistent results.

        **Validates: Requirements 3.2**
        """
        project_data, active_id, all_ids = data
        config = PersonBoxConfig(name=True)

        # Render in all three view types — just verify no errors and
        # that selection semantics are consistent
        views_and_scenes = []

        # FamilyView
        scene1 = QGraphicsScene()
        family_view = FamilyView()
        family_view.render(scene1, project_data, active_id, config)
        views_and_scenes.append(("FamilyView", family_view, scene1))

        # AncestryView
        scene2 = QGraphicsScene()
        ancestry_view = AncestryView()
        ancestry_view.render(scene2, project_data, active_id, config, depth=2)
        views_and_scenes.append(("AncestryView", ancestry_view, scene2))

        # DescendantsView — use first person (parent) so there are descendants
        scene3 = QGraphicsScene()
        descendants_view = DescendantsView()
        descendants_view.render(scene3, project_data, all_ids[0], config, depth=2)
        views_and_scenes.append(("DescendantsView", descendants_view, scene3))

        # For each view, verify the selection contract:
        # 1. After handle_click(id), only matching boxes are selected
        # 2. After deselect_all(), no boxes are selected
        for view_name, view, scene in views_and_scenes:
            boxes = view.get_person_boxes()
            if not boxes:
                continue

            target_id = boxes[0].person_id

            # handle_click selects target
            view.handle_click(target_id)
            assert view.selected_person_id == target_id, (
                f"{view_name}: selected_person_id should be {target_id}"
            )
            for box in view.get_person_boxes():
                if box.person_id == target_id:
                    assert box.is_selected, (
                        f"{view_name}: target box should be selected"
                    )
                else:
                    assert not box.is_selected, (
                        f"{view_name}: non-target box should not be selected"
                    )

            # deselect_all clears selection
            view.deselect_all()
            assert view.selected_person_id is None, (
                f"{view_name}: selected_person_id should be None after deselect_all"
            )
            for box in view.get_person_boxes():
                assert not box.is_selected, (
                    f"{view_name}: all boxes should be deselected"
                )

    @given(data=family_view_data_strategy())
    @settings(max_examples=20, deadline=None)
    def test_re_render_clears_previous_state(self, data) -> None:
        """Re-rendering a view resets person boxes, preserving clean state.

        **Validates: Requirements 3.2**
        """
        project_data, active_id, all_ids = data
        config = PersonBoxConfig(name=True)

        scene = QGraphicsScene()
        view = FamilyView()

        # First render
        view.render(scene, project_data, active_id, config)
        boxes_first = view.get_person_boxes()
        assume(len(boxes_first) > 0)

        # Select something
        view.handle_click(boxes_first[0].person_id)

        # Clear scene and re-render (simulates view switch)
        scene.clear()
        view.render(scene, project_data, active_id, config)

        # After re-render, the new boxes should all be unselected
        # (render() resets _person_boxes)
        for box in view.get_person_boxes():
            assert not box.is_selected, (
                "After re-render, all boxes should start unselected"
            )
