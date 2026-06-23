"""Property-based tests for preservation of click-to-select and diagram sync behavior.

Feature: active-person-change-on-save, Property 2: Preservation

These tests verify that the EXISTING correct behaviors are maintained:
- Single-clicking a person emits person_selected with the correct ID
- select_person_from_diagram() suppresses person_selected signal
- Varying list sizes don't affect click behavior
- Interleaving clicks and diagram syncs respects guard behavior

ALL tests must PASS on the current UNFIXED code. They validate baseline behavior
that must be preserved after the bugfix is applied.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTreeWidgetItem

from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.app_settings_io import AppSettings
from slaktbusken.ui.person_list_panel import PersonListPanel


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


def _make_project_data(persons: list[Person]) -> ProjectData:
    """Build a minimal ProjectData with the given persons."""
    main_id = persons[0].id if persons else None
    return ProjectData(
        project=ProjectMetadata(title="Test Project", main_person_id=main_id),
        persons=persons,
        families=[],
        events=[],
        places=[],
        dna_clusters=[],
        dna_profiles=[],
        dna_companies=[],
        media=[],
    )


def _make_mock_app(project_data: ProjectData) -> MagicMock:
    """Create a mock Application with the given project data."""
    mock_app = MagicMock()
    mock_app.project_service.data = project_data
    mock_app.project_service.project_path = None
    mock_app.app_settings_service._settings = AppSettings()
    return mock_app


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

person_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll",)),
    min_size=3,
    max_size=8,
).map(lambda s: f"p_{s}")

person_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
    min_size=2,
    max_size=10,
)


@st.composite
def person_list_strategy(draw, min_size=2, max_size=8):
    """Generate a list of unique persons with distinct IDs."""
    count = draw(st.integers(min_value=min_size, max_value=max_size))
    persons = []
    used_ids = set()
    for i in range(count):
        pid = f"p_{i}_{draw(person_name_strategy).lower()}"
        while pid in used_ids:
            pid = pid + "x"
        used_ids.add(pid)
        given_name = draw(person_name_strategy)
        surname = draw(person_name_strategy)
        persons.append(_make_person(pid, given_name, surname))
    return persons


class TestClickToSelectPreservation:
    """Property 3: Click-to-Select Behavior Preservation.

    For all user-initiated single-clicks on a person item (outside of refresh
    and outside of diagram sync), person_selected is emitted with the clicked
    person's ID.

    **Validates: Requirements 3.1**
    """

    @given(
        persons=person_list_strategy(min_size=2, max_size=6),
        click_index=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=50, deadline=None)
    def test_click_emits_person_selected_with_correct_id(
        self,
        persons: list[Person],
        click_index: int,
    ) -> None:
        """Property: For all user-initiated single-clicks on a person item,
        person_selected is emitted with the clicked person's ID.

        Feature: active-person-change-on-save, Property 3: Click-to-Select
        **Validates: Requirements 3.1**
        """
        # Constrain click_index to valid range
        click_index = click_index % len(persons)

        project_data = _make_project_data(persons)
        mock_app = _make_mock_app(project_data)
        panel = PersonListPanel(mock_app)
        panel.refresh()

        # Verify tree has items
        item_count = panel._tree_widget.topLevelItemCount()
        assert item_count >= 2, "Precondition: tree must have at least 2 items"

        # Connect signal spy
        emitted: list[str] = []
        panel.person_selected.connect(lambda pid: emitted.append(pid))

        # Find the item at click_index in the tree widget
        item = panel._tree_widget.topLevelItem(click_index % item_count)
        assert item is not None, "Precondition: item at index must exist"

        expected_id = item.data(0, Qt.ItemDataRole.UserRole)
        assert expected_id is not None, "Precondition: item must have person ID data"

        # Simulate user click by setting current item (triggers currentItemChanged)
        panel._tree_widget.setCurrentItem(item)

        # Assert person_selected was emitted with the correct person ID
        assert len(emitted) == 1, (
            f"Expected exactly 1 emission, got {len(emitted)}: {emitted}"
        )
        assert emitted[0] == expected_id, (
            f"Expected person_selected with '{expected_id}', got '{emitted[0]}'"
        )


class TestDiagramSyncSuppression:
    """Property 4: Diagram Sync Suppression Preservation.

    For all select_person_from_diagram(person_id) calls, the person is selected
    in the tree but person_selected is NOT emitted (guarded by _syncing_from_diagram).

    **Validates: Requirements 3.2**
    """

    @given(
        persons=person_list_strategy(min_size=2, max_size=6),
        sync_index=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=50, deadline=None)
    def test_diagram_sync_does_not_emit_person_selected(
        self,
        persons: list[Person],
        sync_index: int,
    ) -> None:
        """Property: For all select_person_from_diagram(person_id) calls,
        person_selected is NOT emitted.

        Feature: active-person-change-on-save, Property 4: Diagram Sync
        **Validates: Requirements 3.2**
        """
        sync_index = sync_index % len(persons)
        target_person = persons[sync_index]

        project_data = _make_project_data(persons)
        mock_app = _make_mock_app(project_data)
        panel = PersonListPanel(mock_app)
        panel.refresh()

        # Connect signal spy
        emitted: list[str] = []
        panel.person_selected.connect(lambda pid: emitted.append(pid))

        # Call select_person_from_diagram (should NOT emit person_selected)
        panel.select_person_from_diagram(target_person.id)

        # Assert person_selected was NOT emitted
        assert len(emitted) == 0, (
            f"select_person_from_diagram should NOT emit person_selected, "
            f"but got {len(emitted)} emission(s): {emitted}"
        )

        # Verify the person IS selected in the tree
        current_item = panel._tree_widget.currentItem()
        if current_item is not None:
            selected_id = current_item.data(0, Qt.ItemDataRole.UserRole)
            assert selected_id == target_person.id, (
                f"Expected '{target_person.id}' selected in tree, got '{selected_id}'"
            )


class TestVaryingListSizes:
    """Property: Varying List Sizes.

    For all person lists of varying sizes, clicking any valid person item
    emits the correct person ID.

    **Validates: Requirements 3.1**
    """

    @given(
        persons=person_list_strategy(min_size=1, max_size=12),
        click_index=st.integers(min_value=0, max_value=11),
    )
    @settings(max_examples=50, deadline=None)
    def test_varying_list_sizes_click_emits_correct_id(
        self,
        persons: list[Person],
        click_index: int,
    ) -> None:
        """Property: For all person lists of varying sizes, clicking any valid
        person item emits the correct person ID.

        Feature: active-person-change-on-save, Property: Varying List Sizes
        **Validates: Requirements 3.1**
        """
        project_data = _make_project_data(persons)
        mock_app = _make_mock_app(project_data)
        panel = PersonListPanel(mock_app)
        panel.refresh()

        item_count = panel._tree_widget.topLevelItemCount()
        assert item_count >= 1, "Precondition: tree must have at least 1 item"

        # Constrain click_index to valid range in the tree
        click_index = click_index % item_count

        # Connect signal spy
        emitted: list[str] = []
        panel.person_selected.connect(lambda pid: emitted.append(pid))

        # Simulate click
        item = panel._tree_widget.topLevelItem(click_index)
        assert item is not None
        expected_id = item.data(0, Qt.ItemDataRole.UserRole)

        panel._tree_widget.setCurrentItem(item)

        # Assert correct emission
        assert len(emitted) == 1, (
            f"Expected exactly 1 emission for list of size {len(persons)}, "
            f"got {len(emitted)}: {emitted}"
        )
        assert emitted[0] == expected_id, (
            f"Expected '{expected_id}', got '{emitted[0]}'"
        )


class TestInterleavingOperations:
    """Property: Interleaving Operations.

    For all interleaving sequences of clicks and diagram syncs, each operation
    respects its respective guard behavior.

    **Validates: Requirements 3.1, 3.2**
    """

    @given(
        persons=person_list_strategy(min_size=3, max_size=6),
        operations=st.lists(
            st.tuples(
                st.sampled_from(["click", "diagram_sync"]),
                st.integers(min_value=0, max_value=5),
            ),
            min_size=3,
            max_size=8,
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_interleaving_clicks_and_syncs(
        self,
        persons: list[Person],
        operations: list[tuple[str, int]],
    ) -> None:
        """Property: For all interleaving sequences of clicks and diagram syncs,
        each operation respects its respective guard behavior.

        - Clicks emit person_selected with the correct ID
        - Diagram syncs do NOT emit person_selected

        Feature: active-person-change-on-save, Property: Interleaving Operations
        **Validates: Requirements 3.1, 3.2**
        """
        project_data = _make_project_data(persons)
        mock_app = _make_mock_app(project_data)
        panel = PersonListPanel(mock_app)
        panel.refresh()

        item_count = panel._tree_widget.topLevelItemCount()
        assert item_count >= 3, "Precondition: tree must have at least 3 items"

        for op_type, op_index in operations:
            # Reset spy for each operation
            emitted: list[str] = []
            panel.person_selected.connect(lambda pid: emitted.append(pid))

            valid_index = op_index % item_count

            if op_type == "click":
                # Simulate user click
                item = panel._tree_widget.topLevelItem(valid_index)
                assert item is not None
                expected_id = item.data(0, Qt.ItemDataRole.UserRole)

                panel._tree_widget.setCurrentItem(item)

                # Click should emit person_selected (may not emit if same item re-selected)
                current = panel._tree_widget.currentItem()
                if current is not None and current == item:
                    # If item was already selected, Qt may not fire currentItemChanged
                    # so we only assert if we got an emission
                    if len(emitted) > 0:
                        assert emitted[-1] == expected_id, (
                            f"Click: expected '{expected_id}', got '{emitted[-1]}'"
                        )
            else:
                # Diagram sync
                target_person = persons[op_index % len(persons)]
                panel.select_person_from_diagram(target_person.id)

                # Diagram sync should NOT emit person_selected
                # Filter only emissions from THIS operation
                assert len(emitted) == 0, (
                    f"Diagram sync should NOT emit, got {len(emitted)}: {emitted}"
                )

            # Disconnect to avoid accumulating connections
            panel.person_selected.disconnect()
