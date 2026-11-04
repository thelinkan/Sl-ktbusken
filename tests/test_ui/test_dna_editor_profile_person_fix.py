"""Regression tests for the DNA editor Profiler tab.

Covers two bugs in :class:`slaktbusken.ui.editors.dna_editor.DnaEditor`:

BUG 1 (data loss): creating / editing a profile through the Profiler tab must
reliably store ``kit_name``, ``kit_id`` and the chosen ``person_id`` through the
visible controls (a :class:`PersonSearchWidget`), and survive a
serialize/deserialize round trip. Previously the save path read ``person_id``
from a hidden, cleared line edit, so new profiles were never saved.

BUG 2 (layout): the "Sök person" admin widget was placed with a hard-coded form
row that collided with another cell. QFormLayout silently refused to manage the
widget, so it floated on top of the Kit-namn row. Every profile field must now
occupy its own distinct form row.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QFormLayout

from slaktbusken.model.dna import DnaCompany, DnaProfile
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.serialization import deserialize, serialize
from slaktbusken.ui.editors.dna_editor import DnaEditor


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_project() -> ProjectData:
    """Build a project with two persons and one DNA company."""
    persons = [
        Person(
            id="person_1",
            sex="M",
            names=[Name(type="birth", given="Anna", surname="Andersson")],
        ),
        Person(
            id="person_2",
            sex="F",
            names=[Name(type="birth", given="Bertil", surname="Berg")],
        ),
    ]
    companies = [DnaCompany(id="company_1", name="TestDNA")]
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=persons,
        dna_companies=companies,
    )


def _make_editor(qtbot, project_data: ProjectData) -> DnaEditor:
    editor = DnaEditor(project_data=project_data, project_path=None)
    qtbot.addWidget(editor)
    return editor


# ---------------------------------------------------------------------------
# BUG 1 — create / edit through the UI stores person_id, kit_name, kit_id
# ---------------------------------------------------------------------------


class TestProfileCreateStoresFieldsThroughVisibleControls:
    """Creating a profile via the Profiler tab stores all visible-control fields."""

    def test_create_profile_stores_person_kit_name_and_kit_id(self, qtbot):
        project_data = _make_project()
        editor = _make_editor(qtbot, project_data)

        # Drive the "add profile" path (clears the form, populates search list).
        editor._on_add_profile()

        # Choose a person via the visible search widget (no hidden input).
        editor._profile_person_search.set_selected_person(
            "person_1", project_data.persons
        )
        # company combo already has company_1 selected (only option)
        editor._ui.profile_kit_name_input.setText("Mitt Kit")
        editor._ui.profile_kit_id_input.setText("KIT-42")

        editor._on_save_profile()

        assert len(project_data.dna_profiles) == 1
        saved = project_data.dna_profiles[0]
        assert saved.person_id == "person_1"
        assert saved.company_id == "company_1"
        assert saved.kit_name == "Mitt Kit"
        assert saved.kit_id == "KIT-42"

    def test_save_rejected_when_no_person_chosen(self, qtbot):
        project_data = _make_project()
        editor = _make_editor(qtbot, project_data)

        editor._on_add_profile()
        # Deliberately choose no person.
        editor._ui.profile_kit_name_input.setText("Namnlös")
        editor._ui.profile_kit_id_input.setText("X")

        editor._on_save_profile()

        # Nothing should be saved, and a status message should be shown.
        assert project_data.dna_profiles == []

    def test_edit_existing_profile_updates_kit_fields(self, qtbot):
        project_data = _make_project()
        profile = DnaProfile(
            id="profile_1",
            person_id="person_1",
            company_id="company_1",
            test_type="autosomal",
            kit_name="Gammalt",
            kit_id="OLD",
        )
        project_data.dna_profiles.append(profile)

        editor = _make_editor(qtbot, project_data)
        editor._editing_profile = profile
        editor._load_profile(profile)

        # The person search widget should be pre-populated.
        assert editor._profile_person_search.selected_person_id() == "person_1"

        editor._ui.profile_kit_name_input.setText("Nytt Kit")
        editor._ui.profile_kit_id_input.setText("NEW-1")
        editor._on_save_profile()

        assert profile.kit_name == "Nytt Kit"
        assert profile.kit_id == "NEW-1"
        assert profile.person_id == "person_1"
        # No duplicate profile created.
        assert len(project_data.dna_profiles) == 1


class TestProfileRoundTripPreservesKitFields:
    """A UI-created profile keeps kit_name/kit_id across a serialize round trip."""

    def test_created_profile_survives_serialize_roundtrip(self, qtbot):
        project_data = _make_project()
        editor = _make_editor(qtbot, project_data)

        editor._on_add_profile()
        editor._profile_person_search.set_selected_person(
            "person_2", project_data.persons
        )
        editor._ui.profile_kit_name_input.setText("Resekit")
        editor._ui.profile_kit_id_input.setText("RK-7")
        editor._on_save_profile()

        # Round trip through the JSON serializer.
        restored = deserialize(serialize(project_data))

        assert len(restored.dna_profiles) == 1
        rp = restored.dna_profiles[0]
        assert rp.kit_name == "Resekit"
        assert rp.kit_id == "RK-7"
        assert rp.person_id == "person_2"

    def test_combo_and_list_label_show_kit_name_not_uuid(self, qtbot):
        project_data = _make_project()
        editor = _make_editor(qtbot, project_data)

        editor._on_add_profile()
        editor._profile_person_search.set_selected_person(
            "person_1", project_data.persons
        )
        editor._ui.profile_kit_name_input.setText("Synligt Namn")
        editor._on_save_profile()

        # Round trip, then rebuild UI from restored data.
        restored = deserialize(serialize(project_data))
        editor2 = _make_editor(qtbot, restored)

        # Profiles list label uses kit_name, not the uuid id.
        list_labels = [
            editor2._ui.profiles_list.item(i).text()
            for i in range(editor2._ui.profiles_list.count())
        ]
        assert any("Synligt Namn" in label for label in list_labels)
        assert all(restored.dna_profiles[0].id not in label for label in list_labels)

        # Match profile combos also use kit_name, not the uuid id.
        combo = editor2._ui.match_profile1_combo
        combo_texts = [combo.itemText(i) for i in range(combo.count())]
        assert any("Synligt Namn" in t for t in combo_texts)
        assert all(restored.dna_profiles[0].id not in t for t in combo_texts)


# ---------------------------------------------------------------------------
# BUG 2 — layout: every profile field sits on its own distinct form row
# ---------------------------------------------------------------------------


class TestProfileFormLayoutNoOverlap:
    """The admin/person search widgets and kit fields occupy distinct rows."""

    def _row_of(self, layout: QFormLayout, widget):
        row, _role = layout.getWidgetPosition(widget)
        return row

    def test_admin_search_and_kit_name_on_different_rows(self, qtbot):
        project_data = _make_project()
        editor = _make_editor(qtbot, project_data)
        layout = editor._ui.profile_form_layout

        person_row = self._row_of(layout, editor._profile_person_search)
        kit_name_row = self._row_of(layout, editor._ui.profile_kit_name_input)
        kit_id_row = self._row_of(layout, editor._ui.profile_kit_id_input)
        admin_row = self._row_of(layout, editor._admin_person_search)
        notes_row = self._row_of(layout, editor._ui.profile_notes_input)

        # All widgets are actually managed by the layout (not floating).
        for row in (person_row, kit_name_row, kit_id_row, admin_row, notes_row):
            assert row >= 0

        # No two of these widgets share a row.
        rows = [person_row, kit_name_row, kit_id_row, admin_row, notes_row]
        assert len(set(rows)) == len(rows)

        # The admin search must not collide with Kit-namn.
        assert admin_row != kit_name_row

    def test_field_order_person_kit_admin_notes(self, qtbot):
        project_data = _make_project()
        editor = _make_editor(qtbot, project_data)
        layout = editor._ui.profile_form_layout

        person_row = self._row_of(layout, editor._profile_person_search)
        kit_name_row = self._row_of(layout, editor._ui.profile_kit_name_input)
        kit_id_row = self._row_of(layout, editor._ui.profile_kit_id_input)
        admin_row = self._row_of(layout, editor._admin_person_search)
        notes_row = self._row_of(layout, editor._ui.profile_notes_input)

        assert person_row < kit_name_row < kit_id_row < admin_row < notes_row

    def test_kit_fields_and_notes_visible(self, qtbot):
        project_data = _make_project()
        editor = _make_editor(qtbot, project_data)
        editor.show()

        assert not editor._ui.profile_kit_name_input.isHidden()
        assert not editor._ui.profile_kit_id_input.isHidden()
        assert not editor._ui.profile_notes_input.isHidden()
        assert not editor._profile_person_search.isHidden()
        assert not editor._admin_person_search.isHidden()
