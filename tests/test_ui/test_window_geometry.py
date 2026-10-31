"""Remembered window sizes and positions."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.persistence.app_settings_io import AppSettings, AppSettingsService
from slaktbusken.ui.window_geometry import (
    KEY_PROPERTY,
    TRACK_PROPERTY,
    WindowGeometryKeeper,
    encode_geometry,
    geometry_key,
    is_tracked,
    restore_geometry,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def keeper(qapp):
    store: dict[str, str] = {}
    keeper = WindowGeometryKeeper(lambda: store)
    qapp.installEventFilter(keeper)
    yield keeper, store
    qapp.removeEventFilter(keeper)


def _screen() -> QRect:
    return QGuiApplication.primaryScreen().availableGeometry()


class _NamedDialog(QDialog):
    pass


class TestKeys:
    def test_dialog_subclass_uses_its_class_name(self, qapp) -> None:
        assert geometry_key(_NamedDialog()) == "_NamedDialog"

    def test_plain_dialog_uses_the_editor_inside_it(self, qapp) -> None:
        from slaktbusken.ui.widgets.research_tab import ResearchTab
        from slaktbusken.model.project import ProjectData

        first = QDialog()
        first.setWindowTitle("Redigera Person - Anna")
        QVBoxLayout(first).addWidget(ResearchTab(ProjectData(), "person", "p1", first))
        second = QDialog()
        second.setWindowTitle("Lägg till person")
        QVBoxLayout(second).addWidget(ResearchTab(ProjectData(), "person", "p2", second))
        assert geometry_key(first) == geometry_key(second) == "QDialog:ResearchTab"

    def test_plain_dialog_without_editor_uses_its_title(self, qapp) -> None:
        dialog = QDialog()
        dialog.setWindowTitle("Ny händelse")
        assert geometry_key(dialog) == "QDialog:Ny händelse"

    def test_explicit_key_wins(self, qapp) -> None:
        window = QMainWindow()
        window.setProperty(KEY_PROPERTY, "main_window")
        assert geometry_key(window) == "main_window"


class TestTracking:
    def test_dialogs_are_tracked_and_system_dialogs_are_not(self, qapp) -> None:
        assert is_tracked(QDialog())
        assert not is_tracked(QMessageBox())
        assert not is_tracked(QFileDialog())

    def test_other_windows_opt_in(self, qapp) -> None:
        window = QWidget()
        assert not is_tracked(window)
        window.setProperty(TRACK_PROPERTY, True)
        assert is_tracked(window)

    def test_child_widgets_are_not_tracked(self, qapp) -> None:
        parent = QDialog()
        child = QDialog(parent)
        inner = QWidget(parent)
        assert is_tracked(child)  # a child dialog is still its own window
        assert not is_tracked(inner)


class TestRestore:
    def test_closed_window_reopens_with_the_same_geometry(self, keeper) -> None:
        _keeper, store = keeper
        screen = _screen()
        target = QRect(screen.x() + 40, screen.y() + 50, 320, 210)

        first = _NamedDialog()
        first.show()
        first.setGeometry(target)
        first.hide()
        assert "_NamedDialog" in store

        second = _NamedDialog()
        second.resize(100, 100)
        second.show()
        assert second.size() == target.size()
        assert second.geometry().topLeft() == target.topLeft()
        second.hide()

    def test_window_without_saved_geometry_keeps_its_default(self, keeper) -> None:
        dialog = QDialog()
        dialog.setWindowTitle("Aldrig visad tidigare")
        dialog.resize(222, 111)
        dialog.show()
        assert dialog.size().width() == 222
        dialog.hide()

    def test_message_boxes_are_left_alone(self, keeper) -> None:
        _keeper, store = keeper
        box = QMessageBox()
        box.show()
        box.hide()
        assert store == {}

    def test_off_screen_geometry_is_discarded(self, qapp) -> None:
        donor = QDialog()
        donor.show()
        donor.setGeometry(QRect(50, 50, 300, 200))
        encoded = encode_geometry(donor)
        donor.hide()

        # Pretend the stored geometry was on a monitor that is no longer there.
        far = QDialog()
        far.show()
        far.setGeometry(QRect(50_000, 50_000, 300, 200))
        far_encoded = encode_geometry(far)
        far.hide()

        # Whether Qt pulls the window back itself or the keeper falls back to
        # the default, the window must end up on a screen.
        target = QDialog()
        target.resize(150, 120)
        restore_geometry(target, far_encoded)
        assert _screen().intersects(target.frameGeometry())
        assert restore_geometry(target, encoded) is True

    def test_damaged_entry_does_not_stop_the_window(self, keeper) -> None:
        _keeper, store = keeper
        store["_NamedDialog"] = "!!! not base64 !!!"
        dialog = _NamedDialog()
        dialog.resize(180, 90)
        dialog.show()  # must not raise
        assert dialog.isVisible()
        dialog.hide()


class TestPersistence:
    def test_geometries_survive_save_and_load(self, tmp_path) -> None:
        service = AppSettingsService()
        service.SETTINGS_PATH = tmp_path / "app_settings.json"
        settings = AppSettings()
        settings.window_geometries = {"main_window": "AAEC", "QDialog:PersonEditor": "AAED"}
        service.save(settings)

        again = AppSettingsService()
        again.SETTINGS_PATH = service.SETTINGS_PATH
        assert again.load().window_geometries == settings.window_geometries

    def test_malformed_entries_are_dropped(self, tmp_path) -> None:
        service = AppSettingsService()
        service.SETTINGS_PATH = tmp_path / "app_settings.json"
        service.SETTINGS_PATH.write_text(
            '{"window_geometries": {"ok": "AAEC", "bad": 5, "": "x", "empty": ""}}',
            encoding="utf-8",
        )
        assert service.load().window_geometries == {"ok": "AAEC"}
        service.SETTINGS_PATH.write_text('{"window_geometries": "nonsense"}', encoding="utf-8")
        assert service.load().window_geometries == {}

    def test_other_settings_saves_keep_the_geometries(self, tmp_path) -> None:
        service = AppSettingsService()
        service.SETTINGS_PATH = tmp_path / "app_settings.json"
        settings = service.load()
        settings.window_geometries["main_window"] = "AAEC"
        # Something else in the app saves settings, for example a column toggle.
        settings.column_visibility.research = False
        service.save(settings)
        assert service.load().window_geometries == {"main_window": "AAEC"}
