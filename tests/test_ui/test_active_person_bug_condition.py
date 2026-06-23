"""Property-based test for bug condition: person_selected emitted during refresh().

Feature: active-person-change-on-save, Property 1: Bug Condition

This test encodes the EXPECTED behavior: calling refresh() on a PersonListPanel
that has an active selection should NOT emit person_selected. When run on UNFIXED
code, this test is expected to FAIL, confirming the bug exists.

Bug flow:
1. PersonListPanel is populated with persons via refresh()
2. User selects person B (setting it as current item in the tree widget)
3. A save operation triggers refresh() again
4. refresh() → _apply_current_view() → _update_list_widget() → _tree_widget.clear()
5. _tree_widget.clear() triggers currentItemChanged signal
6. _on_item_clicked() checks only _syncing_from_diagram (not any _refreshing guard)
7. person_selected is emitted with an unintended person ID
8. diagram_panel.set_active_person() is called, changing the active person

The bug mechanism: During refresh(), `_tree_widget.clear()` fires
`currentItemChanged(None, previous)`. While the handler guards against `current=None`,
the real application's event loop can cause deferred auto-selection of the first item
after tree rebuild (platform/timing dependent). More critically, the `_on_item_clicked`
handler has NO guard against being called during a refresh cycle — if ANY tree item
change occurs during refresh (e.g., from platform-specific auto-focus behavior or
future code changes), `person_selected` will be emitted.

This test directly validates the bug condition by intercepting the `currentItemChanged`
signal processing during refresh. It demonstrates that `_on_item_clicked` will emit
`person_selected` if called with a non-None item during a refresh cycle, because
there is no `_refreshing` guard to prevent it.

**Validates: Requirements 1.1, 1.2, 2.1, 2.2**
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTreeWidgetItem

from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.app_settings_io import AppSettings, AppSettingsService
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
    """Create a mock Application with the given project data.

    The mock provides the minimum attributes needed by PersonListPanel:
    - app.project_service.data → ProjectData
    - app.project_service.project_path → None
    - app.app_settings_service._settings → AppSettings with defaults
    """
    mock_app = MagicMock()
    mock_app.project_service.data = project_data
    mock_app.project_service.project_path = None
    mock_app.app_settings_service._settings = AppSettings()
    return mock_app


# Strategy: generate simple person IDs
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


class TestBugConditionExploration:
    """Property 1: Bug Condition - Refresh Emits person_selected During Save.

    Tests that refresh() on a PersonListPanel with an active selection does NOT
    emit person_selected. On unfixed code, this WILL fail because the
    `_on_item_clicked` handler has no `_refreshing` guard — it only checks
    `_syncing_from_diagram`. When `currentItemChanged` fires during refresh
    (which it does — `clear()` fires it with None, and platform-specific
    auto-focus behavior can fire it with the first item), any non-None current
    item will cause person_selected to be emitted.

    The test simulates the exact bug condition: during refresh(), a
    currentItemChanged signal fires with a valid tree item (as happens in the
    real application), and _on_item_clicked has no guard to prevent emission.

    **Validates: Requirements 1.1, 1.2, 2.1, 2.2**
    """

    @given(
        person_a_id=person_id_strategy,
        person_b_id=person_id_strategy,
        name_a_given=person_name_strategy,
        name_a_surname=person_name_strategy,
        name_b_given=person_name_strategy,
        name_b_surname=person_name_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_refresh_does_not_emit_person_selected(
        self,
        person_a_id: str,
        person_b_id: str,
        name_a_given: str,
        name_a_surname: str,
        name_b_given: str,
        name_b_surname: str,
    ) -> None:
        """Property 1: refresh() SHALL NOT emit person_selected when called
        on a PersonListPanel that has an active selection.

        This test intercepts the refresh cycle to simulate the bug condition:
        during refresh(), `currentItemChanged` fires (triggered by `clear()`
        and/or platform-specific auto-selection after rebuild). Without a
        `_refreshing` guard, `_on_item_clicked` will emit `person_selected`.

        The test hooks into refresh() to call `_on_item_clicked` with a valid
        tree item (simulating what the real Qt event loop does when
        currentItemChanged fires with a non-None item during tree rebuild).
        On UNFIXED code, this will emit person_selected, proving the bug.

        Feature: active-person-change-on-save, Property 1: Bug Condition
        **Validates: Requirements 1.1, 1.2, 2.1, 2.2**
        """
        # Ensure distinct IDs
        if person_a_id == person_b_id:
            person_b_id = person_b_id + "_2"

        # Create two persons
        person_a = _make_person(person_a_id, name_a_given, name_a_surname)
        person_b = _make_person(person_b_id, name_b_given, name_b_surname)

        project_data = _make_project_data([person_a, person_b])
        mock_app = _make_mock_app(project_data)

        # Create PersonListPanel with the mock app
        panel = PersonListPanel(mock_app)

        # Initial refresh to populate the list
        panel.refresh()

        # Verify the tree has items (precondition)
        assert panel._tree_widget.topLevelItemCount() >= 2, (
            "Precondition failed: tree widget should have at least 2 items after refresh"
        )

        # Find person B's item in the tree
        person_b_item = None
        for i in range(panel._tree_widget.topLevelItemCount()):
            item = panel._tree_widget.topLevelItem(i)
            if item and item.data(0, Qt.ItemDataRole.UserRole) == person_b_id:
                person_b_item = item
                break

        assert person_b_item is not None, (
            f"Precondition failed: person B ({person_b_id}) not found in tree widget"
        )

        # Set person B as the current (selected) item
        panel._tree_widget.setCurrentItem(person_b_item)

        # Connect a signal spy to track person_selected emissions
        emitted_signals: list[str] = []
        panel.person_selected.connect(lambda pid: emitted_signals.append(pid))
        emitted_signals.clear()

        # Hook into _update_list_widget to simulate the bug condition:
        # During refresh, after the tree is rebuilt, we simulate the
        # currentItemChanged signal firing with the first item (this is
        # what happens in the real application due to Qt's deferred
        # auto-selection behavior when the tree has focus).
        original_update = panel._update_list_widget

        def _update_with_simulated_signal() -> None:
            """Call original _update_list_widget then simulate currentItemChanged."""
            original_update()
            # After rebuild, simulate Qt's auto-selection of first item
            # (this is the mechanism that causes the bug in the real app)
            first_item = panel._tree_widget.topLevelItem(0)
            if first_item is not None:
                # Simulate currentItemChanged firing with first item
                # This is what Qt does in the real app when the tree is
                # focused and items are repopulated after clear()
                panel._on_item_clicked(first_item, None)

        panel._update_list_widget = _update_with_simulated_signal

        # NOW trigger the bug condition: call refresh() (simulates save)
        panel.refresh()

        # ASSERTION: person_selected should NOT have been emitted during refresh()
        #
        # On UNFIXED code, this WILL FAIL because:
        # - _on_item_clicked is called during refresh with a valid item
        # - It only checks _syncing_from_diagram (which is False)
        # - There is no _refreshing guard to prevent emission
        # - person_selected.emit() is called with the first person's ID
        #
        # After fix: _on_item_clicked will check _refreshing flag and return early
        assert len(emitted_signals) == 0, (
            f"Bug confirmed: person_selected was emitted {len(emitted_signals)} time(s) "
            f"during refresh() with person ID(s): {emitted_signals}. "
            f"Expected: no emission during refresh. "
            f"Root cause: _on_item_clicked has no _refreshing guard — "
            f"currentItemChanged during refresh causes person_selected emission."
        )
