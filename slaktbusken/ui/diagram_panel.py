"""Diagram panel for displaying family tree diagrams.

Provides the main diagram view area with a QGraphicsScene and a
custom ZoomableGraphicsView supporting mouse-wheel zoom from 25% to 400%.
Supports switching between Family, Ancestry, and Descendants views.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QPainter
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.services.lineage_computer import LineageComputer
from slaktbusken.ui.widgets.person_box import PersonBoxItem
from slaktbusken.ui.widgets.placeholder_box import PlaceholderBoxItem

if TYPE_CHECKING:
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QGraphicsSceneMouseEvent

    from slaktbusken.model.project import ProjectData
    from slaktbusken.persistence.settings_io import PersonBoxConfig
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
        person_activated: Emitted when a person should become active, with person_id.
        person_double_clicked: Emitted when a person box is double-clicked, with person_id.
        placeholder_clicked: Emitted when a placeholder box is clicked, with role and family_id.
    """

    person_selected = Signal(str)
    person_activated = Signal(str)
    person_double_clicked = Signal(str)
    placeholder_clicked = Signal(str, str)  # role, family_id
    context_menu_action = Signal(str, str)  # action_type, person_id

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialise the diagram panel.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._active_person_id: Optional[str] = None
        self._current_view: Optional[ViewType] = None
        self._project_data: Optional[ProjectData] = None
        self._person_box_config: Optional[PersonBoxConfig] = None
        self._diagram_settings = None

        self._scene = QGraphicsScene(self)
        self._view = ZoomableGraphicsView(self._scene, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        # View renderers
        from slaktbusken.ui.views.family_view import FamilyView
        from slaktbusken.ui.views.ancestry_view import AncestryView
        from slaktbusken.ui.views.descendants_view import DescendantsView

        self._family_view = FamilyView()
        self._ancestry_view = AncestryView()
        self._descendants_view = DescendantsView()

        # Enable keyboard focus for A-key handling
        self._view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._view.installEventFilter(self)

        # Connect scene click handling
        self._scene.selectionChanged.connect(self._on_scene_selection_changed)

        # Install event filter on the view's viewport for double-click
        self._view.viewport().installEventFilter(self)

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

    def set_project_data(self, project_data: Optional[ProjectData]) -> None:
        """Ange projektdata för diagramrendering.

        Args:
            project_data: Projektdata eller None för att rensa.
        """
        self._project_data = project_data
        self._refresh_diagram()

    def set_person_box_config(self, config: PersonBoxConfig) -> None:
        """Ange konfiguration för personrutor.

        Args:
            config: PersonBoxConfig med fältinställningar.
        """
        self._person_box_config = config
        self._refresh_diagram()

    def set_diagram_settings(self, settings) -> None:
        """Ange diagraminställningar (djup för anor/ättlingar).

        Args:
            settings: DiagramSettings med djupinställningar.
        """
        self._diagram_settings = settings
        self._refresh_diagram()

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
            self._scene.render(painter)
            painter.end()

    def eventFilter(self, obj, event) -> bool:
        """Filtrera tangentbords- och mushändelser.

        Hanterar:
        - A-tangenten: aktivera markerad person
        - Enkelklick: markera person (kringgår ScrollHandDrag)
        - Dubbelklick: öppna redigering för klickad person

        Args:
            obj: Objektet som händelsen gäller.
            event: Händelsen.

        Returns:
            True om händelsen hanterats, annars False.
        """
        from PySide6.QtCore import QEvent

        # A-key on the view for activation
        if obj == self._view and isinstance(event, QKeyEvent):
            if event.type() == event.Type.KeyPress and event.key() == Qt.Key.Key_A:
                selected_id = (
                    self._family_view.selected_person_id
                    or self._ancestry_view.selected_person_id
                    or self._descendants_view.selected_person_id
                )
                if selected_id:
                    self.person_activated.emit(selected_id)
                    self.set_active_person(selected_id)
                    return True

        # Single-click on the viewport to select person/placeholder
        # (ScrollHandDrag consumes mouse events, so we handle selection here)
        # NOTE: We do NOT return True for person clicks — that would prevent
        # Qt from generating MouseButtonDblClick events needed for double-click
        # to open the editor. We only return True for placeholder clicks.
        if obj == self._view.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.position().toPoint()
                scene_pos = self._view.mapToScene(pos)
                item = self._scene.itemAt(scene_pos, self._view.transform())
                if isinstance(item, PersonBoxItem):
                    from slaktbusken.ui.main_window import ViewType

                    if self._current_view == ViewType.FAMILY:
                        self._family_view.handle_click(item.person_id)
                    elif self._current_view == ViewType.ANCESTRY:
                        self._ancestry_view.handle_click(item.person_id)
                    elif self._current_view == ViewType.DESCENDANTS:
                        self._descendants_view.handle_click(item.person_id)
                    self.person_selected.emit(item.person_id)
                    # Don't return True — allow double-click detection
                elif isinstance(item, PlaceholderBoxItem):
                    role_str = item.role.name.lower()
                    family_id = item.family_id or ""
                    self.placeholder_clicked.emit(role_str, family_id)
                    return True
            elif event.button() == Qt.MouseButton.RightButton:
                pos = event.position().toPoint()
                scene_pos = self._view.mapToScene(pos)
                item = self._scene.itemAt(scene_pos, self._view.transform())
                if isinstance(item, PersonBoxItem):
                    self._show_person_context_menu(item.person_id, event.globalPosition().toPoint())
                    return True

        # Double-click on the viewport to open editor
        if obj == self._view.viewport() and event.type() == QEvent.Type.MouseButtonDblClick:
            pos = event.position().toPoint()
            scene_pos = self._view.mapToScene(pos)
            item = self._scene.itemAt(scene_pos, self._view.transform())
            if isinstance(item, PersonBoxItem):
                self.person_double_clicked.emit(item.person_id)
                return True

        return super().eventFilter(obj, event)

    def _on_scene_selection_changed(self) -> None:
        """Hantera förändringar i scenens markering.

        Kontrollerar vilka objekt som är markerade och emitterar
        rätt signaler beroende på typ (person eller platshållare).
        """
        selected_items = self._scene.selectedItems()
        if not selected_items:
            self._family_view.deselect_all()
            self._ancestry_view.deselect_all()
            self._descendants_view.deselect_all()
            return

        item = selected_items[0]
        if isinstance(item, PersonBoxItem):
            self._family_view.handle_click(item.person_id)
            self._ancestry_view.handle_click(item.person_id)
            self._descendants_view.handle_click(item.person_id)
            self.person_selected.emit(item.person_id)
        elif isinstance(item, PlaceholderBoxItem):
            role_str = item.role.name.lower()
            family_id = item.family_id or ""
            self.placeholder_clicked.emit(role_str, family_id)

    def _handle_double_click(self, person_id: str) -> None:
        """Hantera dubbelklick på en personruta.

        Emitterar person_double_clicked-signalen.

        Args:
            person_id: ID för den dubbelklickade personen.
        """
        self.person_double_clicked.emit(person_id)

    def _show_person_context_menu(self, person_id: str, global_pos) -> None:
        """Show context menu for a right-clicked person box.

        Uses ContextMenuBuilder to create the menu and emits
        context_menu_action signal with the selected action type.

        Args:
            person_id: The ID of the right-clicked person.
            global_pos: The global screen position for the menu.
        """
        from PySide6.QtCore import QPoint
        from slaktbusken.ui.context_menu_builder import ContextMenuBuilder

        main_person_id: Optional[str] = None
        if self._project_data is not None:
            main_person_id = self._project_data.project.main_person_id

        builder = ContextMenuBuilder()
        menu = builder.build_person_menu(person_id, main_person_id, self)

        action = menu.exec(QPoint(global_pos.x(), global_pos.y()) if not isinstance(global_pos, QPoint) else global_pos)
        if action is None:
            return

        data = action.data()
        if data and isinstance(data, tuple) and len(data) == 2:
            action_type, pid = data
            # "show_relationship" edge case is handled by ContextMenuBuilder
            # internally (shows message if person == main person).
            # For the normal case, emit signal for app.py to handle.
            if action_type == "show_relationship" and pid == main_person_id:
                # Already handled by ContextMenuBuilder's triggered connection
                return
            self.context_menu_action.emit(action_type, pid)

    def _refresh_diagram(self) -> None:
        """Clear and rebuild the diagram for the current state.

        Uses the FamilyView renderer when the current view is FAMILY,
        AncestryView when ANCESTRY, and project data is available.
        Computes ancestor/descendant sets via LineageComputer based on
        main_person_id and passes them to each view renderer.
        """
        from PySide6.QtCore import QRectF

        # Reset scene rect before clearing to avoid retaining old bounds
        self._scene.setSceneRect(QRectF())
        self._scene.clear()

        from slaktbusken.ui.main_window import ViewType

        # Compute lineage sets based on main_person_id
        ancestor_set: set[str] = set()
        descendant_set: set[str] = set()

        if self._project_data is not None:
            main_person_id = self._project_data.project.main_person_id
            if main_person_id:
                lineage = LineageComputer(self._project_data)
                ancestor_set = lineage.get_ancestors(main_person_id)
                descendant_set = lineage.get_descendants(main_person_id)

        if (
            self._current_view == ViewType.FAMILY
            and self._project_data is not None
            and self._active_person_id is not None
            and self._person_box_config is not None
        ):
            self._family_view.render(
                self._scene,
                self._project_data,
                self._active_person_id,
                self._person_box_config,
                ancestor_set=ancestor_set,
                descendant_set=descendant_set,
            )

            # Enable selection on person boxes
            for box in self._family_view.get_person_boxes():
                box.setFlag(
                    box.GraphicsItemFlag.ItemIsSelectable, True
                )

            # Enable selection on placeholder boxes
            for ph in self._family_view.get_placeholder_boxes():
                ph.setFlag(
                    ph.GraphicsItemFlag.ItemIsSelectable, True
                )

        elif (
            self._current_view == ViewType.ANCESTRY
            and self._project_data is not None
            and self._active_person_id is not None
            and self._person_box_config is not None
        ):
            from slaktbusken.persistence.settings_io import DiagramSettings

            # Get ancestry depth from the config; default to 4
            ancestry_depth = 4
            if hasattr(self, "_diagram_settings") and self._diagram_settings:
                ancestry_depth = self._diagram_settings.ancestry_depth

            self._ancestry_view.render(
                self._scene,
                self._project_data,
                self._active_person_id,
                self._person_box_config,
                depth=ancestry_depth,
                ancestor_set=ancestor_set,
                descendant_set=descendant_set,
            )

            # Enable selection on person boxes
            for box in self._ancestry_view.get_person_boxes():
                box.setFlag(
                    box.GraphicsItemFlag.ItemIsSelectable, True
                )

            # Enable selection on placeholder boxes
            for ph in self._ancestry_view.get_placeholder_boxes():
                ph.setFlag(
                    ph.GraphicsItemFlag.ItemIsSelectable, True
                )

        elif (
            self._current_view == ViewType.DESCENDANTS
            and self._project_data is not None
            and self._active_person_id is not None
            and self._person_box_config is not None
        ):
            # Hämta djup för ättlingar från inställningar; standard 4
            descendants_depth = 4
            if hasattr(self, "_diagram_settings") and self._diagram_settings:
                descendants_depth = self._diagram_settings.descendants_depth

            self._descendants_view.render(
                self._scene,
                self._project_data,
                self._active_person_id,
                self._person_box_config,
                depth=descendants_depth,
                ancestor_set=ancestor_set,
                descendant_set=descendant_set,
            )

            # Aktivera markering på personrutor
            for box in self._descendants_view.get_person_boxes():
                box.setFlag(
                    box.GraphicsItemFlag.ItemIsSelectable, True
                )

        # After rendering, reset scene rect to actual content bounds
        # and force a viewport repaint to avoid old graph remnants
        self._scene.setSceneRect(self._scene.itemsBoundingRect())
        self._view.viewport().update()
