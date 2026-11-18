"""Unit tests for the Kluster tab cluster-management buttons.

Covers the create ("Nytt kluster"), rename ("Byt namn") and delete
("Ta bort kluster") controls on the left panel of the DNA editor's cluster
tab. QInputDialog.getText is monkeypatched so no modal dialog is shown.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog

from slaktbusken.model.dna import DnaCluster
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.editors import dna_editor as dna_editor_module
from slaktbusken.ui.editors.dna_editor import DnaEditor


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def editor(qtbot) -> DnaEditor:
    """Create a DnaEditor instance for testing."""
    project_data = ProjectData(project=ProjectMetadata(title="Test"))
    ed = DnaEditor(project_data=project_data, project_path=None)
    qtbot.addWidget(ed)
    return ed


def _patch_gettext(monkeypatch, value: str, ok: bool) -> None:
    """Monkeypatch QInputDialog.getText to return (value, ok)."""
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        staticmethod(lambda *a, **k: (value, ok)),
    )


def _select_row(editor: DnaEditor, row: int) -> None:
    editor._cluster_list_widget.setCurrentRow(row)


# ------------------------------------------------------------------
# Nytt kluster
# ------------------------------------------------------------------


class TestCreateCluster:
    def test_create_with_name_adds_selected_cluster(self, editor, monkeypatch):
        _patch_gettext(monkeypatch, "Mormors gren", ok=True)

        editor._on_create_cluster()

        clusters = editor._project_data.dna_clusters
        assert len(clusters) == 1
        assert clusters[0].name == "Mormors gren"
        assert clusters[0].person_ids == []
        # New cluster is selected in the list
        current = editor._cluster_list_widget.currentItem()
        assert current is not None
        assert current.data(dna_editor_module.Qt.ItemDataRole.UserRole) == clusters[0].id

    def test_create_trims_whitespace(self, editor, monkeypatch):
        _patch_gettext(monkeypatch, "  Farfars gren  ", ok=True)

        editor._on_create_cluster()

        assert editor._project_data.dna_clusters[0].name == "Farfars gren"

    def test_create_generates_unique_id(self, editor, monkeypatch):
        _patch_gettext(monkeypatch, "A", ok=True)
        editor._on_create_cluster()
        _patch_gettext(monkeypatch, "B", ok=True)
        editor._on_create_cluster()

        clusters = editor._project_data.dna_clusters
        assert len(clusters) == 2
        assert clusters[0].id != clusters[1].id
        assert all(c.id for c in clusters)

    def test_cancel_creates_nothing(self, editor, monkeypatch):
        _patch_gettext(monkeypatch, "Ignored", ok=False)

        editor._on_create_cluster()

        assert editor._project_data.dna_clusters == []

    def test_empty_name_creates_nothing(self, editor, monkeypatch):
        _patch_gettext(monkeypatch, "   ", ok=True)

        editor._on_create_cluster()

        assert editor._project_data.dna_clusters == []


# ------------------------------------------------------------------
# Byt namn
# ------------------------------------------------------------------


class TestRenameCluster:
    def test_rename_changes_selected_name(self, editor, monkeypatch):
        editor._project_data.dna_clusters.append(DnaCluster(id="c1", name="Gammalt"))
        editor._refresh_clusters_list()
        _select_row(editor, 0)

        _patch_gettext(monkeypatch, "Nytt namn", ok=True)
        editor._on_rename_cluster()

        assert editor._project_data.dna_clusters[0].name == "Nytt namn"
        # Still selected
        current = editor._cluster_list_widget.currentItem()
        assert current.data(dna_editor_module.Qt.ItemDataRole.UserRole) == "c1"

    def test_rename_cancel_leaves_name(self, editor, monkeypatch):
        editor._project_data.dna_clusters.append(DnaCluster(id="c1", name="Behåll"))
        editor._refresh_clusters_list()
        _select_row(editor, 0)

        _patch_gettext(monkeypatch, "Ska ignoreras", ok=False)
        editor._on_rename_cluster()

        assert editor._project_data.dna_clusters[0].name == "Behåll"

    def test_rename_empty_leaves_name(self, editor, monkeypatch):
        editor._project_data.dna_clusters.append(DnaCluster(id="c1", name="Behåll"))
        editor._refresh_clusters_list()
        _select_row(editor, 0)

        _patch_gettext(monkeypatch, "   ", ok=True)
        editor._on_rename_cluster()

        assert editor._project_data.dna_clusters[0].name == "Behåll"

    def test_rename_button_disabled_without_selection(self, editor):
        editor._cluster_list_widget.clearSelection()
        editor._cluster_list_widget.setCurrentRow(-1)
        editor._update_cluster_button_states()

        assert editor._rename_cluster_button.isEnabled() is False

    def test_rename_button_enabled_with_selection(self, editor):
        editor._project_data.dna_clusters.append(DnaCluster(id="c1", name="X"))
        editor._refresh_clusters_list()
        _select_row(editor, 0)

        assert editor._rename_cluster_button.isEnabled() is True


# ------------------------------------------------------------------
# Ta bort kluster
# ------------------------------------------------------------------


class TestDeleteCluster:
    def test_delete_disabled_with_members_and_tooltip(self, editor):
        editor._project_data.dna_clusters.append(
            DnaCluster(id="c1", name="Med personer", person_ids=["p1"])
        )
        editor._refresh_clusters_list()
        _select_row(editor, 0)

        assert editor._remove_cluster_button.isEnabled() is False
        assert (
            editor._remove_cluster_button.toolTip()
            == "Klustret innehåller personer och kan inte tas bort."
        )

    def test_delete_enabled_when_empty(self, editor):
        editor._project_data.dna_clusters.append(DnaCluster(id="c1", name="Tomt"))
        editor._refresh_clusters_list()
        _select_row(editor, 0)

        assert editor._remove_cluster_button.isEnabled() is True

    def test_delete_disabled_without_selection(self, editor):
        editor._cluster_list_widget.clearSelection()
        editor._cluster_list_widget.setCurrentRow(-1)
        editor._update_cluster_button_states()

        assert editor._remove_cluster_button.isEnabled() is False
        assert editor._remove_cluster_button.toolTip() == "Välj ett kluster"

    def test_delete_removes_cluster_and_clears_panel(self, editor):
        editor._project_data.dna_clusters.append(
            DnaCluster(id="c1", name="Tomt", notes="Några anteckningar")
        )
        editor._refresh_clusters_list()
        _select_row(editor, 0)

        editor._on_remove_cluster()

        assert editor._project_data.dna_clusters == []
        assert editor._cluster_persons_list.count() == 0
        assert editor._cluster_notes_edit.toPlainText() == ""
        assert editor._cluster_notes_edit.isEnabled() is False


# ------------------------------------------------------------------
# No member-adding control on this tab
# ------------------------------------------------------------------


class TestNoMemberAddingControl:
    def test_left_panel_management_buttons_present(self, editor):
        # The three cluster-management buttons exist on the left panel.
        assert hasattr(editor, "_add_cluster_button")
        assert hasattr(editor, "_rename_cluster_button")
        assert hasattr(editor, "_remove_cluster_button")
        assert editor._add_cluster_button.text() == "Nytt kluster"
        assert editor._rename_cluster_button.text() == "Byt namn"
        assert editor._remove_cluster_button.text() == "Ta bort kluster"

    def test_no_control_adds_persons_to_cluster(self, editor):
        # The persons list is populated from the person editor, not here:
        # it must carry no "add member" affordance. Only a read-only list
        # plus the "Visa filtrerade" filter toggle live alongside it.
        from PySide6.QtWidgets import QPushButton

        # No handler on this editor adds a member to a cluster.
        assert not any(
            "member" in name or "person" in name
            for name in dir(editor)
            if name.startswith("_on_add_cluster") and callable(getattr(editor, name))
            and name not in {"_on_add_cluster", "_on_add_cluster_member"}
        )

        # The legacy member-add handler is a no-op (not wired to any button).
        before = list(getattr(editor, "_cluster_persons_list").findChildren(QPushButton))
        editor._on_add_cluster_member()
        after = list(getattr(editor, "_cluster_persons_list").findChildren(QPushButton))
        assert before == after
        # Adding a member via the UI is impossible: the persons list is a bare
        # QListWidget with no buttons of its own.
        assert editor._cluster_persons_list.findChildren(QPushButton) == []
