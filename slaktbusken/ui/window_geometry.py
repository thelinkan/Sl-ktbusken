"""Remember where windows were and how big they were.

One application-wide event filter covers every dialog and tool window, so no
window has to opt in: when a window is shown for the first time its last
geometry is restored, and when it is hidden (closed, accepted, rejected) its
current geometry is recorded. Windows are keyed by type, not by the record
they show, so every person editor opens where the last one was closed.

The geometries live in ``AppSettings.window_geometries`` (per computer, not
per project) and are written to disk when the application quits.

Transient system dialogs (message boxes, file, colour, font, input and
progress dialogs) keep Qt's own placement. A restored geometry that would put
the window off every screen, for example after a monitor was unplugged, is
discarded and the window opens at its default place instead.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from PySide6.QtCore import QByteArray, QEvent, QObject, QRect
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QErrorMessage,
    QFileDialog,
    QFontDialog,
    QInputDialog,
    QMessageBox,
    QProgressDialog,
    QWidget,
)

logger = logging.getLogger(__name__)

#: Dialog types that keep Qt's default placement.
_EXCLUDED_TYPES: tuple[type, ...] = (
    QMessageBox,
    QFileDialog,
    QColorDialog,
    QFontDialog,
    QInputDialog,
    QProgressDialog,
    QErrorMessage,
)

#: Widget property that makes a non-dialog top-level window tracked, or (as a
#: string) overrides the key used for any window.
TRACK_PROPERTY = "rememberGeometry"
KEY_PROPERTY = "geometryKey"

_RESTORED_PROPERTY = "_geometryRestored"

#: How much of a window must be on a screen for a restored geometry to count.
_MIN_VISIBLE = 60

MAIN_WINDOW_KEY = "main_window"


def is_tracked(widget: QWidget) -> bool:
    """Return True for top-level windows whose geometry should be remembered."""
    if not widget.isWindow():
        return False
    if isinstance(widget, _EXCLUDED_TYPES):
        return False
    if isinstance(widget, QDialog):
        return True
    return bool(widget.property(TRACK_PROPERTY))


def geometry_key(widget: QWidget) -> str:
    """Return the stable key a window's geometry is stored under.

    A dialog subclass is keyed by its class name. A plain ``QDialog`` that wraps
    an editor (the common pattern here) is keyed by the class of the first
    application widget inside it, so "Redigera Person - Anna" and "Lägg till
    person" share the key ``PersonEditor``. Otherwise the window title is used.
    A ``geometryKey`` property overrides all of this.
    """
    explicit = widget.property(KEY_PROPERTY)
    if isinstance(explicit, str) and explicit:
        return explicit

    if type(widget) is not QDialog:
        return type(widget).__name__

    for child in widget.children():
        if isinstance(child, QWidget) and type(child).__module__.startswith("slaktbusken"):
            return f"QDialog:{type(child).__name__}"
    title = widget.windowTitle().strip()
    return f"QDialog:{title}" if title else "QDialog"


def encode_geometry(widget: QWidget) -> str:
    """Return the widget's geometry as a base64 string."""
    return bytes(widget.saveGeometry().toBase64()).decode("ascii")


def _visible_on_some_screen(rect: QRect) -> bool:
    for screen in QGuiApplication.screens():
        overlap = screen.availableGeometry().intersected(rect)
        if overlap.width() >= _MIN_VISIBLE and overlap.height() >= _MIN_VISIBLE // 2:
            return True
    return False


def restore_geometry(widget: QWidget, encoded: str) -> bool:
    """Apply a stored geometry; keep the current one if it would be off-screen.

    Returns:
        True if the stored geometry was applied.
    """
    before = widget.geometry()
    data = QByteArray.fromBase64(encoded.encode("ascii"))
    if data.isEmpty() or not widget.restoreGeometry(data):
        return False
    if not _visible_on_some_screen(widget.frameGeometry()):
        widget.setGeometry(before)
        return False
    return True


class WindowGeometryKeeper(QObject):
    """Event filter that restores and records window geometry.

    Args:
        store: Returns the dict the geometries are kept in. A callable (rather
            than the dict itself) so the keeper always writes into the
            settings object that is current when a window closes.
    """

    def __init__(self, store: Callable[[], dict[str, str]], parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._store = store

    def remember(self, widget: QWidget) -> None:
        """Record a window's current geometry."""
        try:
            self._store()[geometry_key(widget)] = encode_geometry(widget)
        except Exception:  # noqa: BLE001 - never break closing a window
            logger.exception("Kunde inte spara fönstrets position.")

    def restore(self, widget: QWidget) -> bool:
        """Restore a window's stored geometry, if there is one."""
        encoded = self._store().get(geometry_key(widget))
        if not encoded:
            return False
        try:
            return restore_geometry(widget, encoded)
        except Exception:  # noqa: BLE001 - a bad entry must not stop the window opening
            logger.exception("Kunde inte återställa fönstrets position.")
            return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt override
        event_type = event.type()
        if event_type not in (QEvent.Type.Show, QEvent.Type.Hide):
            return False
        if not isinstance(watched, QWidget) or not is_tracked(watched):
            return False

        if event_type == QEvent.Type.Show:
            if not watched.property(_RESTORED_PROPERTY):
                watched.setProperty(_RESTORED_PROPERTY, True)
                self.restore(watched)
        elif watched.property(_RESTORED_PROPERTY):
            # Only windows that were really shown are recorded.
            self.remember(watched)
        return False
