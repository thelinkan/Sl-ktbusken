"""Diagram panel for displaying family tree diagrams.

Provides the main diagram view area with a QGraphicsScene and a
custom ZoomableGraphicsView supporting mouse-wheel zoom from 25% to 400%.
Supports switching between Family, Ancestry, and Descendants views.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from PySide6.QtGui import QWheelEvent

    from slaktbusken.ui.main_window import ViewType

logger = logging.getLogger(__name__)

# Zoom limits as scale factors (1.0 = 100%)
_MIN_ZOOM = 0.25
_MAX_ZOOM = 4.0
_ZOOM_STEP = 1.15  # Each wheel notch scales by 15%


class ZoomableGraphicsView(QGraphicsView):
    """A QGraphicsView with mouse-wheel zoom support.

    Supports smooth zooming between 25% and 400% using the mouse
    wheel while holding Ctrl, or always (depending on configuration).

    Signals:
        zoom_changed: Emitted when the zoom level changes, with the
            new scale factor (1.0 = 100%).
    """

    zoom_changed = Signal(float)

    def __init__(self, scene: QGraphicsScene, parent: Optional[QWidget] = None) -> None:
        """Initialise the zoomable view.

        Args:
            scene: The QGraphicsScene to display.
            parent: Optional parent widget.
        """
        super().__init__(scene, parent)
        self._zoom_factor: float = 1.0

        # Rendering quality
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    @property
    def zoom_factor(self) -> float:
        """Current zoom factor (1.0 = 100%)."""
        return self._zoom_factor

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle mouse wheel zoom.

        Zooms in/out when the mouse wheel is scrolled, clamping
        to the 25%-400% range.

        Args:
            event: The wheel event.
        """
        angle_delta = event.angleDelta().y()
        if angle_delta == 0:
            super().wheelEvent(event)
            return

        if angle_delta > 0:
            factor = _ZOOM_STEP
        else:
            factor = 1.0 / _ZOOM_STEP

        new_zoom = self._zoom_factor * factor

        # Clamp to allowed range
        if new_zoom < _MIN_ZOOM:
            factor = _MIN_ZOOM / self._zoom_factor
            new_zoom = _MIN_ZOOM
        elif new_zoom > _MAX_ZOOM:
            factor = _MAX_ZOOM / self._zoom_factor
            new_zoom = _MAX_ZOOM

        if factor == 1.0:
            return

        self.scale(factor, factor)
        self._zoom_factor = new_zoom
        self.zoom_changed.emit(self._zoom_factor)

    def set_zoom(self, factor: float) -> None:
        """Set the zoom level to a specific factor.

        Args:
            factor: Desired zoom factor (clamped to 0.25–4.0).
        """
        factor = max(_MIN_ZOOM, min(_MAX_ZOOM, factor))
        scale_change = factor / self._zoom_factor
        self.scale(scale_change, scale_change)
        self._zoom_factor = factor
        self.zoom_changed.emit(self._zoom_factor)

    def reset_zoom(self) -> None:
        """Reset zoom to 100%."""
        self.set_zoom(1.0)


class DiagramPanel(QWidget):
    """Main diagram panel displaying family tree views.

    Contains a QGraphicsScene and a ZoomableGraphicsView. Provides
    methods to set the active person, switch between view types
    (Family, Ancestry, Descendants), and print the current diagram.

    Signals:
        person_selected: Emitted when a person box is clicked, with person_id.
        person_activated: Emitted when a person box is double-clicked, with person_id.
        placeholder_clicked: Emitted when a placeholder box is clicked, with role string.
    """

    person_selected = Signal(str)
    person_activated = Signal(str)
    placeholder_clicked = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialise the diagram panel.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._active_person_id: Optional[str] = None
        self._current_view: Optional[ViewType] = None

        self._scene = QGraphicsScene(self)
        self._view = ZoomableGraphicsView(self._scene, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

    @property
    def scene(self) -> QGraphicsScene:
        """The underlying QGraphicsScene."""
        return self._scene

    @property
    def view(self) -> ZoomableGraphicsView:
        """The ZoomableGraphicsView widget."""
        return self._view

    @property
    def active_person_id(self) -> Optional[str]:
        """The currently active person ID, or None."""
        return self._active_person_id

    @property
    def current_view(self) -> Optional[ViewType]:
        """The currently active view type."""
        return self._current_view

    def set_active_person(self, person_id: Optional[str]) -> None:
        """Set the active person and refresh the diagram.

        Args:
            person_id: The person ID to centre the diagram on,
                or None to clear.
        """
        self._active_person_id = person_id
        self._refresh_diagram()

    def switch_view(self, view_type: ViewType) -> None:
        """Switch the diagram to a different view type.

        Args:
            view_type: The view type to switch to (FAMILY, ANCESTRY,
                or DESCENDANTS).
        """
        self._current_view = view_type
        self._refresh_diagram()

    def print_diagram(self) -> None:
        """Print the current diagram view.

        Opens a print dialog and renders the current scene content
        to the selected printer.
        """
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QPrintDialog.DialogCode.Accepted:
            painter = QPainter(printer)
            self._view.render(painter)
            painter.end()

    def _refresh_diagram(self) -> None:
        """Clear and rebuild the diagram for the current state.

        This is a placeholder that clears the scene. Full layout
        logic will be implemented in later tasks when diagram
        layout algorithms are added.
        """
        self._scene.clear()
        # Full diagram layout will be implemented in subsequent tasks.
        # For now, the scene is cleared and ready for items to be added.
