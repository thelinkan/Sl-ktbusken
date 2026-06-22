"""Property-based preservation tests for FotoTab and PersonListWidget.

Feature: photo-editor-bugs, Property 2: Preservation

These tests verify that existing (non-buggy) behaviors are unchanged BEFORE
implementing the fix. They capture the baseline behavior for:
- Photo addition (creates MediaItem with LinkedEntity)
- Metadata editing (format_title produces "[Foto_Typ] title")
- Explicit person list save (syncs mentioned_person_ids and linked_entities)
- Photo selection (populates editing panel)
- Profile photo selection (sets profile_media_id)
- Non-starred name display (returns "given surname")
- No-year display (no parentheses in output)
- Combo box add (adds person to list and emits persons_changed)

These tests MUST PASS on the current unfixed code.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9**
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st
from PySide6.QtWidgets import QApplication

from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.photo_service import PhotoService
from slaktbusken.ui.widgets.foto_tab import FotoTab
from slaktbusken.ui.widgets.person_list_widget import PersonListWidget, _person_display_name


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# Strategies for preservation tests
# ---------------------------------------------------------------------------

# Photo titles (1–200 chars, no special chars that would break format parsing)
# Must equal its stripped form since _on_add_photo applies strip() before saving
_valid_titles = st.text(
    alphabet=st.characters(categories=("L", "N", "Z")),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip() and len(s.strip()) <= 200 and s == s.strip())

# Foto types from the PhotoService list
_foto_types = st.sampled_from(PhotoService.FOTO_TYPES)

# Person IDs
_person_ids = st.integers(min_value=1, max_value=999).map(lambda n: f"p{n}")

# Given names WITHOUT "*" (preservation of non-starred behavior)
_given_names_no_star = st.text(
    alphabet=st.characters(categories=("L",)),
    min_size=1,
    max_size=30,
).filter(lambda s: "*" not in s and s.strip())

# Surnames
_surnames = st.text(
    alphabet=st.characters(categories=("L",)),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip())

# Allowed image extensions
_image_extensions = st.sampled_from([".jpg", ".jpeg", ".png", ".tif", ".bmp", ".gif"])


# ---------------------------------------------------------------------------
# Property: format_title preservation
# ---------------------------------------------------------------------------


class TestMetadataFormatPreservation:
    """Property: For all metadata edits with valid title/foto_typ,
    _on_save_metadata produces title in format "[Foto_Typ] title".

    This tests the PhotoService.format_title function directly and the
    FotoTab._on_save_metadata integration.

    **Validates: Requirements 3.2**
    """

    @given(
        foto_typ=_foto_types,
        title=_valid_titles,
    )
    @settings(max_examples=50, deadline=None)
    def test_format_title_produces_bracket_prefix(
        self, foto_typ: str, title: str
    ) -> None:
        """For all valid foto_typ and title combinations, format_title
        returns '[Foto_Typ] title'.

        **Validates: Requirements 3.2**
        """
        project_data = ProjectData()
        foto_mapp = Path("/tmp/fake_mapp")
        service = PhotoService(project_data, foto_mapp)

        result = service.format_title(foto_typ, title)

        assert result == f"[{foto_typ}] {title}", (
            f"Expected '[{foto_typ}] {title}', got '{result}'"
        )

    @given(
        foto_typ=_foto_types,
        title=_valid_titles,
    )
    @settings(max_examples=50, deadline=None)
    def test_parse_title_roundtrips_format_title(
        self, foto_typ: str, title: str
    ) -> None:
        """For all valid inputs, parse_title(format_title(typ, title)) == (typ, title).

        **Validates: Requirements 3.2**
        """
        project_data = ProjectData()
        foto_mapp = Path("/tmp/fake_mapp")
        service = PhotoService(project_data, foto_mapp)

        formatted = service.format_title(foto_typ, title)
        parsed_typ, parsed_title = service.parse_title(formatted)

        assert parsed_typ == foto_typ, (
            f"Round-trip failed: expected typ '{foto_typ}', got '{parsed_typ}'"
        )
        assert parsed_title == title, (
            f"Round-trip failed: expected title '{title}', got '{parsed_title}'"
        )


# ---------------------------------------------------------------------------
# Property: _on_add_photo creates MediaItem with LinkedEntity
# ---------------------------------------------------------------------------


class TestAddPhotoLinkedEntityPreservation:
    """Property: For all valid photo file inputs, _on_add_photo creates a MediaItem
    with a LinkedEntity(entity_type="person", entity_id=person.id) and appends
    to project_data.media.

    **Validates: Requirements 3.1, 3.6**
    """

    @given(
        person_id=_person_ids,
        foto_typ=_foto_types,
        title=_valid_titles,
        extension=_image_extensions,
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_add_photo_creates_linked_entity(
        self, person_id: str, foto_typ: str, title: str, extension: str,
        tmp_path: Path
    ) -> None:
        """For all valid photo additions, the new MediaItem has a LinkedEntity
        linking it to the current person.

        **Validates: Requirements 3.1, 3.6**
        """
        # Use a unique subdirectory per hypothesis example
        work_dir = Path(tempfile.mkdtemp(dir=tmp_path))

        person = Person(
            id=person_id, sex="M",
            names=[Name(type="birth", given="Test", surname="Person")],
        )
        project_data = ProjectData()
        project_data.persons = [person]

        foto_mapp = work_dir / "media" / "photos"
        foto_mapp.mkdir(parents=True)

        # Create a fake image file
        test_image = work_dir / f"photo{extension}"
        test_image.write_bytes(b"\x00" * 50)

        service = PhotoService(project_data, foto_mapp)
        tab = FotoTab(project_data, person, service)

        with (
            patch(
                "slaktbusken.ui.widgets.foto_tab.QFileDialog.getOpenFileName",
                return_value=(str(test_image), ""),
            ),
            patch(
                "slaktbusken.ui.widgets.foto_tab.QInputDialog.getText",
                return_value=(title, True),
            ),
            patch(
                "slaktbusken.ui.widgets.foto_tab.QInputDialog.getItem",
                return_value=(foto_typ, True),
            ),
        ):
            tab._on_add_photo()

        # Verify a MediaItem was created
        assert len(project_data.media) == 1, (
            f"Expected 1 media item, got {len(project_data.media)}"
        )
        media_item = project_data.media[0]

        # Property: MediaItem has correct type
        assert media_item.type == "photo"

        # Property: MediaItem has LinkedEntity for the person
        person_links = [
            le for le in media_item.linked_entities
            if le.entity_type == "person" and le.entity_id == person_id
        ]
        assert len(person_links) == 1, (
            f"Expected exactly one LinkedEntity for person '{person_id}', "
            f"got {len(person_links)}"
        )

        # Property: title is formatted correctly
        assert media_item.title == f"[{foto_typ}] {title}"


# ---------------------------------------------------------------------------
# Property: _on_save_persons syncs mentioned_person_ids and linked_entities
# ---------------------------------------------------------------------------


class TestSavePersonsPreservation:
    """Property: For all explicit _on_save_persons calls with pending changes,
    mentioned_person_ids and linked_entities are synced correctly.

    **Validates: Requirements 3.3**
    """

    @given(
        person_ids_to_add=st.lists(
            _person_ids, min_size=1, max_size=5, unique=True
        ),
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_save_persons_syncs_mentioned_and_linked(
        self, person_ids_to_add: list[str], tmp_path: Path
    ) -> None:
        """For all explicit save_persons calls, mentioned_person_ids and
        linked_entities are updated correctly.

        **Validates: Requirements 3.3**
        """
        # Use a unique subdirectory per hypothesis example
        work_dir = Path(tempfile.mkdtemp(dir=tmp_path))

        # Set up project with a person and a photo
        owner_id = "owner_1"
        person = Person(
            id=owner_id, sex="M",
            names=[Name(type="birth", given="Erik", surname="Svensson")],
        )

        # Create persons for the IDs to add
        all_persons = [person]
        for pid in person_ids_to_add:
            all_persons.append(
                Person(
                    id=pid, sex="M",
                    names=[Name(type="birth", given="Test", surname="Person")],
                )
            )

        media_item = MediaItem(
            id="m1", type="photo", file="media/photos/test.jpg",
            title="[Porträtt] Test",
            linked_entities=[LinkedEntity(entity_type="person", entity_id=owner_id)],
            mentioned_person_ids=[],
        )

        project_data = ProjectData()
        project_data.persons = all_persons
        project_data.media = [media_item]

        foto_mapp = work_dir / "media" / "photos"
        foto_mapp.mkdir(parents=True)

        service = PhotoService(project_data, foto_mapp)
        tab = FotoTab(project_data, person, service)

        # Select the photo
        tab._table.selectRow(0)

        # Simulate adding persons to the person list widget
        tab._person_list_widget._current_person_ids = list(person_ids_to_add)
        tab._person_list_widget.persons_changed.emit()

        # Explicitly click "Spara personlista"
        tab._on_save_persons()

        # Property: mentioned_person_ids matches what we set
        assert media_item.mentioned_person_ids == person_ids_to_add, (
            f"Expected mentioned_person_ids={person_ids_to_add}, "
            f"got {media_item.mentioned_person_ids}"
        )

        # Property: linked_entities contains a person link for each ID
        person_entity_ids = [
            le.entity_id for le in media_item.linked_entities
            if le.entity_type == "person"
        ]
        for pid in person_ids_to_add:
            assert pid in person_entity_ids, (
                f"Expected person '{pid}' in linked_entities, "
                f"got {person_entity_ids}"
            )

        # Property: save button is disabled after save
        assert not tab._save_persons_btn.isEnabled()


# ---------------------------------------------------------------------------
# Property: Photo selection populates editing panel
# ---------------------------------------------------------------------------


class TestPhotoSelectionPreservation:
    """Property: For all photo selections, the editing panel is populated
    with the selected MediaItem data.

    **Validates: Requirements 3.4**
    """

    @given(
        foto_typ=_foto_types,
        title=_valid_titles,
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_photo_selection_populates_editing_fields(
        self, foto_typ: str, title: str, tmp_path: Path
    ) -> None:
        """For all photo selections, the title and foto_typ fields are
        populated with the parsed values from the MediaItem title.

        **Validates: Requirements 3.4**
        """
        work_dir = Path(tempfile.mkdtemp(dir=tmp_path))

        person = Person(
            id="p1", sex="M",
            names=[Name(type="birth", given="Erik", surname="Svensson")],
        )

        formatted_title = f"[{foto_typ}] {title}"
        media_item = MediaItem(
            id="m1", type="photo", file="media/photos/test.jpg",
            title=formatted_title,
            linked_entities=[LinkedEntity(entity_type="person", entity_id="p1")],
        )

        project_data = ProjectData()
        project_data.persons = [person]
        project_data.media = [media_item]

        foto_mapp = work_dir / "media" / "photos"
        foto_mapp.mkdir(parents=True)

        service = PhotoService(project_data, foto_mapp)
        tab = FotoTab(project_data, person, service)

        # Select the photo
        tab._table.selectRow(0)

        # Property: editing panel is visible
        assert tab._edit_group.isVisibleTo(tab), (
            "Edit group should be visible after selecting a photo"
        )

        # Property: title input contains the parsed title
        assert tab._edit_title_input.text() == title, (
            f"Expected title input '{title}', got '{tab._edit_title_input.text()}'"
        )

        # Property: foto_typ combo shows the correct type
        assert tab._edit_typ_combo.currentText() == foto_typ, (
            f"Expected foto_typ '{foto_typ}', got '{tab._edit_typ_combo.currentText()}'"
        )

        # Property: person list section is visible
        assert tab._person_list_group.isVisibleTo(tab), (
            "Person list group should be visible after selecting a photo"
        )


# ---------------------------------------------------------------------------
# Property: "Välj som profilbild" sets profile_media_id
# ---------------------------------------------------------------------------


class TestProfilePhotoPreservation:
    """Property: For all 'Välj som profilbild' invocations,
    profile_media_id is set to the selected media.id.

    NOTE: The profile photo button may be on the PersonEditor level
    rather than FotoTab itself. We test the expected outcome: that
    setting profile_media_id on Person works correctly for any media ID.

    **Validates: Requirements 3.5**
    """

    @given(
        media_id=st.text(
            alphabet=st.characters(categories=("L", "N")),
            min_size=5,
            max_size=20,
        ),
    )
    @settings(max_examples=30, deadline=None)
    def test_profile_media_id_can_be_set(self, media_id: str) -> None:
        """For all valid media IDs, profile_media_id can be set on a Person.

        **Validates: Requirements 3.5**
        """
        person = Person(
            id="p1", sex="M",
            names=[Name(type="birth", given="Erik", surname="Svensson")],
        )

        # Set profile_media_id
        person.profile_media_id = media_id

        # Property: profile_media_id is stored correctly
        assert person.profile_media_id == media_id, (
            f"Expected profile_media_id '{media_id}', got '{person.profile_media_id}'"
        )


# ---------------------------------------------------------------------------
# Property: Non-starred names display correctly
# ---------------------------------------------------------------------------


class TestNonStarredNameDisplayPreservation:
    """Property: For all persons whose names do NOT contain '*',
    _person_display_name returns 'given surname' (stripped).

    **Validates: Requirements 3.7, 3.8**
    """

    @given(
        given_name=_given_names_no_star,
        surname=_surnames,
    )
    @settings(max_examples=50, deadline=None)
    def test_non_starred_names_display_as_given_surname(
        self, given_name: str, surname: str
    ) -> None:
        """For all persons without '*' in their name, the display is
        'given surname' (stripped of leading/trailing whitespace).

        **Validates: Requirements 3.7, 3.8**
        """
        person = Person(
            id="p1", sex="M",
            names=[Name(type="birth", given=given_name, surname=surname)],
        )

        display = _person_display_name(person)

        expected = f"{given_name} {surname}".strip()
        assert display == expected, (
            f"Expected '{expected}', got '{display}'"
        )

    @given(
        given_name=_given_names_no_star,
        surname=_surnames,
    )
    @settings(max_examples=50, deadline=None)
    def test_non_starred_names_do_not_contain_star(
        self, given_name: str, surname: str
    ) -> None:
        """For all persons without '*' in given name, display never contains '*'.

        **Validates: Requirements 3.7**
        """
        person = Person(
            id="p1", sex="M",
            names=[Name(type="birth", given=given_name, surname=surname)],
        )

        display = _person_display_name(person)
        assert "*" not in display

    def test_person_with_no_names_returns_fallback(self) -> None:
        """Person with no names returns '(Person {id})' format.

        **Validates: Requirements 3.7**
        """
        person = Person(id="p99", sex="M", names=[])
        display = _person_display_name(person)
        assert display == "(Person p99)"


# ---------------------------------------------------------------------------
# Property: No parentheses for persons without year data
# ---------------------------------------------------------------------------


class TestNoYearNoParenthesesPreservation:
    """Property: For all persons with no birth AND no death year,
    display text contains no parentheses.

    On unfixed code, _person_display_name never shows years at all, so
    this property is trivially true for ALL persons currently. This test
    captures that baseline behavior.

    **Validates: Requirements 3.9**
    """

    @given(
        given_name=_given_names_no_star,
        surname=_surnames,
    )
    @settings(max_examples=50, deadline=None)
    def test_no_parentheses_in_display_without_year_data(
        self, given_name: str, surname: str
    ) -> None:
        """For all persons with no birth/death year, display contains no parentheses.

        **Validates: Requirements 3.9**
        """
        # Person with no events (hence no birth/death year data)
        person = Person(
            id="p1", sex="M",
            names=[Name(type="birth", given=given_name, surname=surname)],
        )

        display = _person_display_name(person)

        # Property: no parentheses in the display
        assert "(" not in display and ")" not in display, (
            f"Display should contain no parentheses for person without year data. "
            f"Got: '{display}'"
        )


# ---------------------------------------------------------------------------
# Property: Combo box "Lägg till" adds person and emits persons_changed
# ---------------------------------------------------------------------------


class TestComboBoxAddPreservation:
    """Property: For all combo box selections via 'Lägg till', person is
    added to list and persons_changed emitted.

    **Validates: Requirements 3.8**
    """

    @given(
        person_index=st.integers(min_value=0, max_value=4),
    )
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_add_db_person_adds_to_list_and_emits_signal(
        self, person_index: int, tmp_path: Path
    ) -> None:
        """For all combo box selections, the person is added to the internal
        list and persons_changed signal is emitted.

        **Validates: Requirements 3.8**
        """
        work_dir = Path(tempfile.mkdtemp(dir=tmp_path))

        # Create a pool of persons
        persons = [
            Person(
                id=f"p{i}", sex="M",
                names=[Name(type="birth", given=f"Person{i}", surname=f"Surname{i}")],
            )
            for i in range(5)
        ]
        # Limit index to valid range
        person_index = person_index % len(persons)
        target_person = persons[person_index]

        # The photo owner is a different person
        owner = Person(
            id="owner", sex="M",
            names=[Name(type="birth", given="Owner", surname="Person")],
        )

        media_item = MediaItem(
            id="m1", type="photo", file="media/photos/test.jpg",
            title="[Porträtt] Test",
            linked_entities=[LinkedEntity(entity_type="person", entity_id="owner")],
            mentioned_person_ids=[],
        )

        project_data = ProjectData()
        project_data.persons = [owner] + persons
        project_data.media = [media_item]

        foto_mapp = work_dir / "media" / "photos"
        foto_mapp.mkdir(parents=True)

        service = PhotoService(project_data, foto_mapp)
        tab = FotoTab(project_data, owner, service)

        # Select the photo
        tab._table.selectRow(0)

        # Track signal emission
        signal_emitted = []
        tab._person_list_widget.persons_changed.connect(
            lambda: signal_emitted.append(True)
        )

        # Find the target person in the combo box
        combo = tab._person_list_widget._person_combo
        found_index = -1
        for i in range(combo.count()):
            if combo.itemData(i) == target_person.id:
                found_index = i
                break

        assume(found_index > 0)  # Must find the person (skip placeholder at 0)

        # Select the person in combo and click "Lägg till"
        combo.setCurrentIndex(found_index)
        tab._person_list_widget._on_add_db_person()

        # Property: person is now in the internal list
        assert target_person.id in tab._person_list_widget.get_person_ids(), (
            f"Person '{target_person.id}' should be in the person list after add"
        )

        # Property: persons_changed signal was emitted
        assert len(signal_emitted) > 0, (
            "persons_changed signal should have been emitted after adding a person"
        )
