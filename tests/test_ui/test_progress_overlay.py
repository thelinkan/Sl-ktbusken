"""Unit tests for ProgressOverlay show/hide, message, resize, and animation.

Verifies that:
- show_with_message() makes the overlay visible.
- hide() makes the overlay not visible.
- show_with_message() sets the internal message correctly.
- The overlay resizes to match its parent widget.
- The animation starts on show and stops on hide.

Covers Requirements 8.5, 8.6, 8.7.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPropertyAnimation
from PySide6.QtWidgets import QApplication, QWidget

from slaktbusken.ui.widgets.progress_overlay import ProgressOverlay


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def parent_widget(qapp) -> QWidget:
    """Return a shown QWidget to act as the parent for the overlay."""
    widget = QWidget()
    widget.resize(800, 600)
    widget.show()
    qapp.processEvents()
    return widget


@pytest.fixture()
def overlay(parent_widget: QWidget) -> ProgressOverlay:
    """Return a ProgressOverlay attached to the parent widget."""
    return ProgressOverlay(parent_widget)


class TestShowHide:
    """Tests for visibility state transitions."""

    def test_overlay_visible_after_show(self, overlay: ProgressOverlay):
        """After show_with_message(), the overlay is visible."""
        overlay.show_with_message("Test")
        assert overlay.isVisible() is True

    def test_overlay_hidden_after_hide(self, overlay: ProgressOverlay):
        """After hide(), the overlay is not visible."""
        overlay.show_with_message("Test")
        overlay.hide()
        assert overlay.isVisible() is False

    def test_overlay_starts_hidden(self, overlay: ProgressOverlay):
        """The overlay is hidden by default after construction."""
        assert overlay.isVisible() is False


class TestMessage:
    """Tests for message text handling."""

    def test_message_set_correctly(self, overlay: ProgressOverlay):
        """show_with_message() stores the message in _message."""
        overlay.show_with_message("Laddar...")
        assert overlay._message == "Laddar..."

    def test_message_updates_on_subsequent_call(self, overlay: ProgressOverlay):
        """Calling show_with_message() again updates the message."""
        overlay.show_with_message("First")
        overlay.show_with_message("Second")
        assert overlay._message == "Second"


class TestResize:
    """Tests for overlay resizing with parent."""

    def test_overlay_matches_parent_on_show(
        self, parent_widget: QWidget, overlay: ProgressOverlay
    ):
        """On show, overlay geometry matches parent rect."""
        parent_widget.resize(1024, 768)
        overlay.show_with_message("Resizing...")
        assert overlay.geometry() == parent_widget.rect()

    def test_overlay_matches_parent_after_resize(
        self, qapp, parent_widget: QWidget, overlay: ProgressOverlay
    ):
        """When the parent is resized, the overlay geometry updates to match."""
        overlay.show_with_message("Resize test")
        parent_widget.resize(640, 480)
        qapp.processEvents()
        assert overlay.geometry() == parent_widget.rect()


class TestAnimation:
    """Tests for spinner animation start/stop."""

    def test_animation_running_after_show(self, overlay: ProgressOverlay):
        """The spinner animation is running after show_with_message()."""
        overlay.show_with_message("Animating...")
        assert overlay._animation.state() == QPropertyAnimation.State.Running

    def test_animation_stopped_after_hide(self, overlay: ProgressOverlay):
        """The spinner animation is stopped after hide()."""
        overlay.show_with_message("Animating...")
        overlay.hide()
        assert overlay._animation.state() == QPropertyAnimation.State.Stopped
