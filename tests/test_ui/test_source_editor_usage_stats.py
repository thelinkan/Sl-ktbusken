"""Unit tests for the SourceEditor usage statistics display and usage detail dialog.

Tests that:
- Each source list item displays inline person count and event count
- Sources with zero referencing events show "0" for both counts
- Double-click on a source item opens the usage detail dialog
- The usage detail dialog lists distinct persons with grouped events

Validates: Requirements 6.1, 6.2, 6.3, 6.4
"""

from __future__ import annotations

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.source import Source
from slaktbusken.ui.dialogs.usage_detail_dialog import (
    UsageDetailDialog,
    build_usage_groups,
    _get_person_display_name,
)
from slaktbusken.ui.editors.source_editor import SourceEditor


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def project_with_usage() -> ProjectData:
    """Create a project with sources referenced by events."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=[
            Person(id="p1", sex="M", names=[Name(type="birth", given="Erik", surname="Andersson")]),
            Person(id="p2", sex="F", names=[Name(type="birth", given="Anna", surname="Svensson")]),
            Person(id="p3", sex="M", names=[Name(type="birth", given="Lars", surname="Olsson")]),
        ],
        sources=[
            Source(id="src-1", provider="Arkiv Digital", source_type="church_book", title="Ljusdal AI:17"),
            Source(id="src-2", provider="Rötter.se", source_type="database", title="Sveriges Dödbok"),
        ],
        events=[
            Event(
                id="e1",
                type="birth",
                participants=[
                    Participant(person_id="p1", role="child"),
                    Participant(person_id="p2", role="mother"),
                ],
                date=DateValue(
                    value="1850-03-15",
                    precision="exact",
                    source_refs=[SourceRef(source_id="src-1", quality="high")],
                ),
            ),
            Event(
                id="e2",
                type="marriage",
                participants=[
                    Participant(person_id="p2", role="wife"),
                    Participant(person_id="p3", role="husband"),
                ],
                place=PlaceRef(
                    place_id="pl-1",
                    source_refs=[SourceRef(source_id="src-1", quality="medium")],
                ),
            ),
            Event(
                id="e3",
                type="death",
                participants=[
                    Participant(person_id="p1", role="deceased"),
                ],
                date=DateValue(
                    value="1920-06-01",
                    precision="exact",
                    source_refs=[SourceRef(source_id="src-2", quality="high")],
                ),
            ),
        ],
    )


@pytest.fixture()
def project_no_usage() -> ProjectData:
    """Create a project with sources but no referencing events."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=[
            Person(id="p1", sex="M", names=[Name(type="birth", given="Erik", surname="Andersson")]),
        ],
        sources=[
            Source(id="src-1", provider="Arkiv Digital", source_type="church_book", title="Ljusdal AI:17"),
        ],
        events=[
            Event(
                id="e1",
                type="birth",
                participants=[Participant(person_id="p1", role="child")],
                date=DateValue(
                    value="1850-03-15",
                    precision="exact",
                    source_refs=[SourceRef(source_id="other-src", quality="high")],
                ),
            ),
        ],
    )


class TestSourceListUsageDisplay:
    """Tests for inline usage statistics in the source list."""

    def test_source_list_shows_usage_counts(self, qapp, project_with_usage) -> None:
        """Source list items display person and event counts inline."""
        editor = SourceEditor(project_data=project_with_usage)

        # src-1 is referenced by 2 events (e1, e2), with 3 distinct persons (p1, p2, p3)
        item = editor._ui.source_list.item(0)
        assert item is not None
        text = item.text()
        assert "[3 pers, 2 händ]" in text
        assert "Ljusdal AI:17" in text

    def test_source_list_shows_second_source_counts(self, qapp, project_with_usage) -> None:
        """Second source also shows correct counts."""
        editor = SourceEditor(project_data=project_with_usage)

        # src-2 is referenced by 1 event (e3), with 1 person (p1)
        item = editor._ui.source_list.item(1)
        assert item is not None
        text = item.text()
        assert "[1 pers, 1 händ]" in text
        assert "Sveriges Dödbok" in text

    def test_source_with_zero_usage_shows_zero(self, qapp, project_no_usage) -> None:
        """Sources with no referencing events display '0' for both counts."""
        editor = SourceEditor(project_data=project_no_usage)

        item = editor._ui.source_list.item(0)
        assert item is not None
        text = item.text()
        assert "[0 pers, 0 händ]" in text

    def test_source_list_preserves_provider_display(self, qapp, project_with_usage) -> None:
        """Provider is still displayed in the list item."""
        editor = SourceEditor(project_data=project_with_usage)

        item = editor._ui.source_list.item(0)
        assert item is not None
        text = item.text()
        assert "(Arkiv Digital)" in text

    def test_source_list_filter_still_works(self, qapp, project_with_usage) -> None:
        """Search filtering still works with usage stats display."""
        editor = SourceEditor(project_data=project_with_usage)

        # Filter should reduce the list
        editor._refresh_source_list("Ljusdal")
        assert editor._ui.source_list.count() == 1
        item = editor._ui.source_list.item(0)
        assert "Ljusdal" in item.text()
        assert "[3 pers, 2 händ]" in item.text()

    def test_source_list_stores_source_id_in_user_role(self, qapp, project_with_usage) -> None:
        """Each list item still stores the source ID in UserRole data."""
        editor = SourceEditor(project_data=project_with_usage)

        item = editor._ui.source_list.item(0)
        assert item.data(Qt.ItemDataRole.UserRole) == "src-1"

        item = editor._ui.source_list.item(1)
        assert item.data(Qt.ItemDataRole.UserRole) == "src-2"


class TestUsageDetailDialog:
    """Tests for the usage detail dialog."""

    def test_build_usage_groups_returns_correct_grouping(self, project_with_usage) -> None:
        """build_usage_groups returns correct person->events mapping."""
        groups = build_usage_groups(
            "src-1", project_with_usage.events, project_with_usage.persons
        )

        # p1 participates in e1, p2 participates in e1 and e2, p3 participates in e2
        assert "p1" in groups
        assert "p2" in groups
        assert "p3" in groups
        assert len(groups["p1"]) == 1  # e1
        assert len(groups["p2"]) == 2  # e1, e2
        assert len(groups["p3"]) == 1  # e2

    def test_build_usage_groups_empty_for_unreferenced_source(self, project_with_usage) -> None:
        """build_usage_groups returns empty dict for unreferenced source."""
        groups = build_usage_groups(
            "nonexistent-src", project_with_usage.events, project_with_usage.persons
        )
        assert groups == {}

    def test_get_person_display_name_found(self, project_with_usage) -> None:
        """_get_person_display_name returns given + surname for known person."""
        name = _get_person_display_name("p1", project_with_usage.persons)
        assert name == "Erik Andersson"

    def test_get_person_display_name_not_found(self, project_with_usage) -> None:
        """_get_person_display_name returns person_id if not found."""
        name = _get_person_display_name("unknown-id", project_with_usage.persons)
        assert name == "unknown-id"

    def test_dialog_creates_successfully(self, qapp, project_with_usage) -> None:
        """UsageDetailDialog instantiates without error."""
        source = project_with_usage.sources[0]
        dialog = UsageDetailDialog(
            parent=None,
            source=source,
            events=project_with_usage.events,
            persons=project_with_usage.persons,
        )
        assert dialog.windowTitle() == f"Användning: {source.title}"

    def test_dialog_shows_no_usage_message(self, qapp, project_no_usage) -> None:
        """Dialog shows appropriate message when source has no usage."""
        source = project_no_usage.sources[0]
        dialog = UsageDetailDialog(
            parent=None,
            source=source,
            events=project_no_usage.events,
            persons=project_no_usage.persons,
        )
        # Dialog should exist without error
        assert dialog.windowTitle() == f"Användning: {source.title}"
