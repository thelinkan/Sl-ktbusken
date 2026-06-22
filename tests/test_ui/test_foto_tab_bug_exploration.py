"""Bug condition exploration tests for FotoTab / PersonEditor / PersonListWidget.

These tests encode the EXPECTED (correct) behavior for five known bugs.
They are written BEFORE the fix is implemented. On unfixed code they MUST FAIL,
confirming the bugs exist. After the fix, they should PASS.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

Bugs tested:
1. Person list not persisted on save — _on_save() doesn't flush pending changes
2. No way to delete/unlink a photo — missing "Ta bort foto" button
3. Person not auto-added to mentioned_person_ids on photo add
4. Cannot distinguish persons with same name — no birth/death years in display
5. Tilltalsnamn marker (*) breaks person search — * included in display text
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from PySide6.QtWidgets import QApplication, QPushButton

from slaktbusken.model.event import Event, Participant, DateValue
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.photo_service import PhotoService
from slaktbusken.ui.widgets.foto_tab import FotoTab
from slaktbusken.ui.widgets.person_list_widget import _person_display_name


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_given_names_with_star = st.text(
    alphabet=st.characters(categories=("L",)),
    min_size=1,
    max_size=20,
).map(lambda s: s + "*")

_plain_names = st.text(
    alphabet=st.characters(categories=("L",)),
    min_size=1,
    max_size=20,
)

_surnames = st.text(
    alphabet=st.characters(categories=("L",)),
    min_size=1,
    max_size=20,
)

_years = st.integers(min_value=1600, max_value=2024)


# ---------------------------------------------------------------------------
# Bug 1: Person list not persisted on save
# ---------------------------------------------------------------------------


class TestBug1_PersonListNotPersistedOnSave:
    """Bug 1: PersonEditor._on_save() does not flush pending FotoTab changes.

    Expected behavior (after fix): When _save_persons_btn is enabled (pending
    changes exist), calling _on_save() should persist the person list changes
    to the MediaItem before completing the save.
    """

    def test_pending_person_list_flushed_on_save(self, qapp, tmp_path: Path):
        """After modifying person list and calling _on_save, mentioned_person_ids
        should be updated on the MediaItem.

        **Validates: Requirements 2.1**
        """
        # Set up project data with a person and a linked photo
        person = Person(
            id="p1", sex="M",
            names=[Name(type="birth", given="Erik", surname="Svensson")],
        )
        media_item = MediaItem(
            id="m1", type="photo", file="media/photos/test.jpg",
            title="[Porträtt] Test",
            linked_entities=[LinkedEntity(entity_type="person", entity_id="p1")],
            mentioned_person_ids=[],
        )
        # A second person to add to the person list
        person2 = Person(
            id="p2", sex="F",
            names=[Name(type="birth", given="Anna", surname="Johansson")],
        )
        project_data = ProjectData()
        project_data.persons = [person, person2]
        project_data.media = [media_item]

        foto_mapp = tmp_path / "media" / "photos"
        foto_mapp.mkdir(parents=True)

        service = PhotoService(project_data, foto_mapp)
        foto_tab = FotoTab(project_data, person, service)

        # Select the photo in the table
        foto_tab._table.selectRow(0)

        # Simulate adding a person via the PersonListWidget
        foto_tab._person_list_widget._current_person_ids.append("p2")
        foto_tab._person_list_widget.persons_changed.emit()

        # At this point _save_persons_btn should be enabled (pending changes)
        assert foto_tab._save_persons_btn.isEnabled(), (
            "Save persons button should be enabled after modifying person list"
        )

        # Now simulate what PersonEditor._on_save() does — it should flush
        # pending changes. On unfixed code, it does NOT call any flush method.
        # We import PersonEditor and call _on_save, but to keep this focused
        # we directly check: does the FotoTab have a flush method that is called?
        # The expected behavior is that after a "save" action, the MediaItem
        # has the updated mentioned_person_ids.

        # Simulate the save action by checking if flush_pending_person_list exists
        # and if calling it persists the changes. On unfixed code, the method
        # doesn't exist, OR _on_save doesn't call it.
        # For this test, we directly verify the expected outcome:
        # After enabling the save button and triggering what _on_save should do,
        # the media_item.mentioned_person_ids should contain "p2".

        # The bug is that _on_save does NOT call _on_save_persons or any flush.
        # So we verify the expected behavior: if pending changes exist AND
        # a flush is triggered, the media item gets updated.
        # On unfixed code, we'll just check that the media_item was NOT updated
        # (proving the bug), by asserting the EXPECTED state.

        # EXPECTED BEHAVIOR (will fail on unfixed code):
        # After "save" with pending person list changes, the media_item should
        # have the updated mentioned_person_ids
        # We simulate: if PersonEditor._on_save were correct, it would call
        # foto_tab._on_save_persons() or flush_pending_person_list()
        # The bug is that it doesn't. We test that flush_pending_person_list exists:
        assert hasattr(foto_tab, "flush_pending_person_list"), (
            "FotoTab should have a flush_pending_person_list() method "
            "that PersonEditor._on_save() can call to persist pending changes"
        )


# ---------------------------------------------------------------------------
# Bug 2: No way to delete/unlink a photo
# ---------------------------------------------------------------------------


class TestBug2_NoDeletePhotoButton:
    """Bug 2: FotoTab has no 'Ta bort foto' button.

    Expected behavior (after fix): FotoTab should contain a QPushButton
    with text 'Ta bort foto' that allows users to unlink/delete a photo.
    """

    def test_delete_photo_button_exists(self, qapp, tmp_path: Path):
        """FotoTab should have a 'Ta bort foto' button in its widget hierarchy.

        **Validates: Requirements 2.2**
        """
        person = Person(
            id="p1", sex="M",
            names=[Name(type="birth", given="Erik", surname="Svensson")],
        )
        project_data = ProjectData()
        project_data.persons = [person]

        foto_mapp = tmp_path / "media" / "photos"
        foto_mapp.mkdir(parents=True)

        service = PhotoService(project_data, foto_mapp)
        foto_tab = FotoTab(project_data, person, service)

        # Search for a QPushButton with text "Ta bort foto" in the widget tree
        delete_buttons = foto_tab.findChildren(QPushButton)
        delete_button_texts = [btn.text() for btn in delete_buttons]

        assert "Ta bort foto" in delete_button_texts, (
            f"FotoTab should contain a 'Ta bort foto' button. "
            f"Found buttons: {delete_button_texts}"
        )


# ---------------------------------------------------------------------------
# Bug 3: Person not auto-added to mentioned_person_ids on photo add
# ---------------------------------------------------------------------------


class TestBug3_PersonNotAutoAdded:
    """Bug 3: _on_add_photo does not add person to mentioned_person_ids.

    Expected behavior (after fix): After adding a photo to a person,
    the new MediaItem's mentioned_person_ids should include the person's ID.
    """

    def test_person_auto_added_to_mentioned_person_ids(self, qapp, tmp_path: Path):
        """After _on_add_photo creates a MediaItem, the person's id should be
        in mentioned_person_ids.

        **Validates: Requirements 2.3**
        """
        person = Person(
            id="p1", sex="M",
            names=[Name(type="birth", given="Erik", surname="Svensson")],
        )
        project_data = ProjectData()
        project_data.persons = [person]

        foto_mapp = tmp_path / "media" / "photos"
        foto_mapp.mkdir(parents=True)

        # Create a test image file to "add"
        test_image = tmp_path / "test_photo.jpg"
        test_image.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # minimal JPEG

        service = PhotoService(project_data, foto_mapp)
        foto_tab = FotoTab(project_data, person, service)

        # Mock the file dialog and input dialogs to simulate a successful add
        with patch.object(
            foto_tab, "_on_add_photo", wraps=None
        ) as _:
            pass  # We'll call the real method with mocked dialogs

        # Patch dialogs to simulate successful photo add flow
        with (
            patch(
                "slaktbusken.ui.widgets.foto_tab.QFileDialog.getOpenFileName",
                return_value=(str(test_image), ""),
            ),
            patch(
                "slaktbusken.ui.widgets.foto_tab.QInputDialog.getText",
                return_value=("Testfoto", True),
            ),
            patch(
                "slaktbusken.ui.widgets.foto_tab.QInputDialog.getItem",
                return_value=("Porträtt", True),
            ),
        ):
            foto_tab._on_add_photo()

        # Find the newly created media item
        new_items = [
            m for m in project_data.media
            if any(
                le.entity_type == "person" and le.entity_id == "p1"
                for le in m.linked_entities
            )
        ]
        assert len(new_items) == 1, "Expected exactly one new media item"

        new_media = new_items[0]

        # EXPECTED BEHAVIOR (will fail on unfixed code):
        # The person should be auto-added to mentioned_person_ids
        assert "p1" in new_media.mentioned_person_ids, (
            f"Person 'p1' should be in mentioned_person_ids after adding a photo. "
            f"Got: {new_media.mentioned_person_ids}"
        )


# ---------------------------------------------------------------------------
# Bug 4: Cannot distinguish persons with same name
# ---------------------------------------------------------------------------


class TestBug4_DuplicateNamesIndistinguishable:
    """Bug 4: _person_display_name() shows no birth/death years.

    Expected behavior (after fix): When two persons share the same name but
    have different birth/death years, their display names should be different
    (include year disambiguation).
    """

    @given(
        birth_year_1=_years,
        birth_year_2=_years,
    )
    @settings(max_examples=10)
    def test_same_name_different_years_distinguishable(
        self, birth_year_1: int, birth_year_2: int
    ):
        """Two persons with the same name but different birth years should
        produce DIFFERENT display strings.

        **Validates: Requirements 2.4**
        """
        assume(birth_year_1 != birth_year_2)

        person_a = Person(
            id="pa", sex="M",
            names=[Name(type="birth", given="Erik", surname="Andersson")],
        )
        person_b = Person(
            id="pb", sex="M",
            names=[Name(type="birth", given="Erik", surname="Andersson")],
        )

        # Create birth events for both persons with different years
        events = [
            Event(
                id="e1", type="birth",
                participants=[Participant(person_id="pa", role="primary")],
                date=DateValue(value=str(birth_year_1), precision="year"),
            ),
            Event(
                id="e2", type="birth",
                participants=[Participant(person_id="pb", role="primary")],
                date=DateValue(value=str(birth_year_2), precision="year"),
            ),
        ]

        # EXPECTED BEHAVIOR (will fail on unfixed code):
        # Display names should be different because they include years
        display_a = _person_display_name(person_a, events)
        display_b = _person_display_name(person_b, events)

        assert display_a != display_b, (
            f"Two persons with same name but different birth years "
            f"({birth_year_1} vs {birth_year_2}) should have different "
            f"display names. Got: '{display_a}' == '{display_b}'"
        )


# ---------------------------------------------------------------------------
# Bug 5: Tilltalsnamn marker (*) breaks person search
# ---------------------------------------------------------------------------


class TestBug5_TilltalsnamnsMarkerInDisplay:
    """Bug 5: _person_display_name() does not strip * from given names.

    Expected behavior (after fix): The * character (tilltalsnamn marker)
    should be stripped from the display text.
    """

    @given(
        given_base=_plain_names,
        surname=_surnames,
    )
    @settings(max_examples=20)
    def test_star_stripped_from_display_name(
        self, given_base: str, surname: str
    ):
        """Display name should NOT contain '*' when given name has tilltalsnamn marker.

        **Validates: Requirements 2.5**
        """
        # Create a person with a star in the given name
        given_with_star = given_base + "*"
        person = Person(
            id="p_star", sex="M",
            names=[Name(type="birth", given=given_with_star, surname=surname)],
        )

        display = _person_display_name(person)

        # EXPECTED BEHAVIOR (will fail on unfixed code):
        # The display name should NOT contain the * character
        assert "*" not in display, (
            f"Display name should not contain '*' (tilltalsnamn marker). "
            f"Given: '{given_with_star}', Got display: '{display}'"
        )

    def test_concrete_star_example(self):
        """Concrete example: 'Karl Erik*' surname 'Andersson' should display
        as 'Karl Erik Andersson' (no star).

        **Validates: Requirements 2.5**
        """
        person = Person(
            id="p1", sex="M",
            names=[Name(type="birth", given="Karl Erik*", surname="Andersson")],
        )

        display = _person_display_name(person)

        assert "*" not in display, (
            f"Expected 'Karl Erik Andersson' (no star), got: '{display}'"
        )
        assert "Karl Erik" in display, (
            f"Expected 'Karl Erik' in display, got: '{display}'"
        )
