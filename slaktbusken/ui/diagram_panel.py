"""Diagram panel for displaying family tree diagrams.

Provides the main diagram view area with a QGraphicsScene and a
custom ZoomableGraphicsView supporting mouse-wheel zoom from 25% to 400%.
Supports switching between Family, Ancestry, and Descendants views.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QKeyEvent, QPainter
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.services.lineage_computer import LineageComputer
from slaktbusken.ui.widgets.person_box import PersonBoxItem
from slaktbusken.ui.widgets.placeholder_box import (
    PlaceholderBoxItem,
    PlaceholderRole,
)

if TYPE_CHECKING:
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QGraphicsSceneMouseEvent

    from slaktbusken.model.project import ProjectData
    from slaktbusken.persistence.settings_io import PersonBoxConfig
    from slaktbusken.ui.main_window import ViewType

logger = logging.getLogger(__name__)

# Zoom limits as scale factors (1.0 = 100%)
_MIN_ZOOM = 0.01
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
        self._project_folder: Optional[Path] = None

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

        Rensar aktiv person om den inte finns i den nya datan,
        för att undvika att ett gammalt person-ID från en tidigare
        fil orsakar felmeddelanden.

        Args:
            project_data: Projektdata eller None för att rensa.
        """
        # Clear stale active person if it doesn't exist in new data
        if project_data is None:
            self._active_person_id = None
        elif self._active_person_id is not None:
            person_ids = {p.id for p in project_data.persons}
            if self._active_person_id not in person_ids:
                self._active_person_id = None

        self._project_data = project_data
        self._refresh_diagram()

    def set_project_folder(self, folder: Optional["Path"]) -> None:
        """Ange projektmapp för att kunna ladda mediafiler (foton, logotyper).

        Args:
            folder: Sökväg till projektmappen eller None.
        """
        self._project_folder = folder

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
        # Apply background color
        if hasattr(settings, 'background_color') and settings.background_color:
            from PySide6.QtGui import QBrush, QColor
            self._scene.setBackgroundBrush(QBrush(QColor(settings.background_color)))
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

    def _current_view_title(self) -> str:
        """Returnera en läsbar titel för den aktuella vyn."""
        from slaktbusken.ui.main_window import ViewType

        names = {
            ViewType.FAMILY: "Familjevy",
            ViewType.ANCESTRY: "Antavla",
            ViewType.DESCENDANTS: "Ättlingar",
        }
        return names.get(self._current_view, "Diagram")

    def _active_person_years(self) -> tuple[Optional[str], Optional[str]]:
        """Hämta födelse- och dödsår för den aktiva personen.

        Scannar händelser efter personens födelse- och dödshändelser och
        extraherar ett fyrsiffrigt årtal ur respektive datum om möjligt.

        Returns:
            Ett par (födelseår, dödsår) där vardera kan vara None.
        """
        import re

        if self._project_data is None or self._active_person_id is None:
            return (None, None)

        def _extract_year(date_value: Optional[str]) -> Optional[str]:
            if not date_value:
                return None
            match = re.search(r"\d{4}", date_value)
            return match.group(0) if match else None

        birth_year: Optional[str] = None
        death_year: Optional[str] = None
        for event in self._project_data.events:
            if not any(
                p.person_id == self._active_person_id for p in event.participants
            ):
                continue
            if event.type == "birth" and event.date and birth_year is None:
                birth_year = _extract_year(event.date.value)
            elif event.type == "death" and event.date and death_year is None:
                death_year = _extract_year(event.date.value)
        return (birth_year, death_year)

    def _print_heading(self) -> Optional[str]:
        """Bygg rubriken som visas överst i utskriften.

        Formaterar rubriken som "Familj till Förnamn Efternamn (ÅÅÅÅ–ÅÅÅÅ)"
        beroende på aktuell vy. Returnerar None om det inte finns någon aktiv
        person att beskriva.

        Returns:
            Rubriktext eller None.
        """
        from slaktbusken.ui.main_window import ViewType
        from slaktbusken.ui.views.family_view import (
            _find_person,
            _get_display_name,
        )

        if self._project_data is None or self._active_person_id is None:
            return None

        person = _find_person(self._project_data, self._active_person_id)
        if person is None:
            return None

        name = _get_display_name(person)

        birth_year, death_year = self._active_person_years()
        years = ""
        if birth_year or death_year:
            years = f" ({birth_year or ''}-{death_year or ''})"

        prefixes = {
            ViewType.FAMILY: "Familj till",
            ViewType.ANCESTRY: "Anor till",
            ViewType.DESCENDANTS: "Ättlingar till",
        }
        prefix = prefixes.get(self._current_view, "Diagram för")
        return f"{prefix} {name}{years}"

    def _person_box_scene_rects(self) -> list["QRectF"]:
        """Samla personrutornas gränser i scenekoordinater.

        Används av utskriftsplaneringen för att undvika att en personruta
        delas mellan två sidor. Fungerar för alla tre vyer eftersom
        personrutorna läses direkt från scenen.

        Returns:
            Lista med QRectF i scenekoordinater.
        """
        rects: list[QRectF] = []
        for item in self._scene.items():
            if isinstance(item, PersonBoxItem):
                rects.append(item.sceneBoundingRect())
        return rects

    def _collect_print_hidden_items(self) -> list["QGraphicsItem"]:
        """Hämta objekt som ska döljas i utskriften.

        Vid utskrift ska icke-existerande personer utelämnas, utom när de
        behövs för att visa kopplingen mellan två personer. Platshållare för
        förälder (far/mor) markerar en strukturell position i släktträdet och
        behålls därför, medan "Lägg till barn" och "Lägg till partner" är rena
        tilläggsknappar utan någon person på andra sidan och tas bort.

        Dessutom tas kopplingslinjer bort om de inte förbinder minst två
        kvarvarande ankare (personrutor eller behållna förälderplatshållare).
        På så vis försvinner även hängande linjestumpar — t.ex. "ryggraden"
        ned mot den aktiva personens "Lägg till partner"-platshållare — som
        annars skulle lämna lösa linjer mot tom yta.

        Returns:
            Lista med objekt (platshållare och tillhörande linjer) som ska
            döljas i utskriften.
        """
        from slaktbusken.ui.widgets.connection_line import ConnectionLineItem

        drop_roles = {PlaceholderRole.CHILD, PlaceholderRole.PARTNER}
        removed_placeholders = [
            item
            for item in self._scene.items()
            if isinstance(item, PlaceholderBoxItem) and item.role in drop_roles
        ]

        # Ankare som en linje måste förbinda för att vara meningsfull:
        # verkliga personrutor samt behållna förälderplatshållare.
        anchor_rects: list[QRectF] = []
        for item in self._scene.items():
            if isinstance(item, PersonBoxItem):
                anchor_rects.append(item.sceneBoundingRect().adjusted(-2, -2, 2, 2))
            elif isinstance(item, PlaceholderBoxItem) and item.role not in drop_roles:
                anchor_rects.append(item.sceneBoundingRect().adjusted(-2, -2, 2, 2))

        lines = [
            item
            for item in self._scene.items()
            if isinstance(item, ConnectionLineItem)
        ]

        # Ändpunkter (scenekoordinater) för varje linje.
        endpoints: list[tuple[QPointF, QPointF]] = []
        for line in lines:
            endpoints.append(
                (line.mapToScene(line.start_point), line.mapToScene(line.end_point))
            )

        tol = 2.0

        def _on_segment(pt: QPointF, a: QPointF, b: QPointF) -> bool:
            """True om punkten ligger på segmentet a–b (med tolerans)."""
            minx, maxx = min(a.x(), b.x()) - tol, max(a.x(), b.x()) + tol
            miny, maxy = min(a.y(), b.y()) - tol, max(a.y(), b.y()) + tol
            if not (minx <= pt.x() <= maxx and miny <= pt.y() <= maxy):
                return False
            # Avstånd punkt-till-linje (räcker med linjens riktning).
            dx, dy = b.x() - a.x(), b.y() - a.y()
            seg_len = (dx * dx + dy * dy) ** 0.5
            if seg_len < 1e-6:
                return (
                    abs(pt.x() - a.x()) <= tol and abs(pt.y() - a.y()) <= tol
                )
            dist = abs(dy * (pt.x() - a.x()) - dx * (pt.y() - a.y())) / seg_len
            return dist <= tol

        # Union-find för att koppla ihop linjer som rör varandra, även vid
        # T-korsningar (en linjes ändpunkt ligger på en annan linjes mitt).
        parent = list(range(len(lines)))

        def _find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def _union(i: int, j: int) -> None:
            ri, rj = _find(i), _find(j)
            if ri != rj:
                parent[ri] = rj

        for i in range(len(lines)):
            ai, bi = endpoints[i]
            for j in range(i + 1, len(lines)):
                aj, bj = endpoints[j]
                if (
                    _on_segment(ai, aj, bj)
                    or _on_segment(bi, aj, bj)
                    or _on_segment(aj, ai, bi)
                    or _on_segment(bj, ai, bi)
                ):
                    _union(i, j)

        # Räkna distinkta ankare som varje komponent rör.
        comp_anchors: dict[int, set[int]] = {}
        for i in range(len(lines)):
            root = _find(i)
            touched = comp_anchors.setdefault(root, set())
            for pt in endpoints[i]:
                for ai, rect in enumerate(anchor_rects):
                    if rect.contains(pt):
                        touched.add(ai)

        # En meningsfull koppling förbinder minst två ankare. Komponenter som
        # rör färre är hängande stumpar och tas bort.
        lines_to_remove: list[QGraphicsItem] = []
        for i in range(len(lines)):
            if len(comp_anchors.get(_find(i), set())) < 2:
                lines_to_remove.append(lines[i])

        return [*removed_placeholders, *lines_to_remove]

    def print_diagram(self) -> None:
        """Visa förhandsgranskning för utskrift av den aktuella vyn.

        Öppnar en dialog som renderar scenen skalad efter aktuell zoomnivå,
        delar upp innehållet på flera sidor vid behov (utan att dela
        personrutor) och erbjuder utskrift samt PDF-export.

        Rena "lägg till"-platshållare (barn/partner) döljs tillfälligt så att
        de inte kommer med i utskriften, medan förälderplatshållare behålls
        eftersom de visar kopplingen mellan personer.
        """
        from slaktbusken.ui.dialogs.diagram_print import DiagramPrintDialog

        if not self._scene.items():
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(
                self,
                "Skriv ut",
                "Det finns inget att skriva ut i den aktuella vyn.",
            )
            return

        # Ta tillfälligt bort rena tilläggsplatshållare (och linjer som leder
        # till dem) ur scenen så att de varken påverkar innehållsgränser eller
        # renderingen. Återställs efter att dialogen stängts.
        hidden = self._collect_print_hidden_items()
        for item in hidden:
            self._scene.removeItem(item)

        try:
            dialog = DiagramPrintDialog(
                scene=self._scene,
                box_rects=self._person_box_scene_rects(),
                zoom_factor=self._view.zoom_factor,
                view_title=self._current_view_title(),
                heading=self._print_heading(),
                parent=self,
            )
            dialog.exec()
        finally:
            for item in hidden:
                self._scene.addItem(item)

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
        from PySide6.QtCore import QRectF, QSignalBlocker

        # Block selectionChanged during the entire clear+rebuild cycle to
        # prevent _on_scene_selection_changed from accessing stale refs.
        with QSignalBlocker(self._scene):
            # Reset scene rect before clearing to avoid retaining old bounds
            self._scene.setSceneRect(QRectF())

            # Defense in depth: clear stale person box references before scene.clear()
            # so deselect_all() iterates an empty list if selectionChanged fires
            self._family_view._person_boxes = []
            self._ancestry_view._person_boxes = []
            self._descendants_view._person_boxes = []

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
                    project_folder=self._project_folder,
                    diagram_settings=self._diagram_settings,
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
                # Get ancestry depth and compact mode from the config
                ancestry_depth = 4
                ancestry_compact = False
                if hasattr(self, "_diagram_settings") and self._diagram_settings:
                    ancestry_depth = self._diagram_settings.ancestry_depth
                    ancestry_compact = self._diagram_settings.ancestry_compact

                self._ancestry_view.render(
                    self._scene,
                    self._project_data,
                    self._active_person_id,
                    self._person_box_config,
                    depth=ancestry_depth - 1,
                    ancestor_set=ancestor_set,
                    descendant_set=descendant_set,
                    project_folder=self._project_folder,
                    compact=ancestry_compact,
                    diagram_settings=getattr(self, "_diagram_settings", None),
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
                    depth=descendants_depth - 1,
                    ancestor_set=ancestor_set,
                    descendant_set=descendant_set,
                    project_folder=self._project_folder,
                    diagram_settings=(
                        self._diagram_settings
                        if hasattr(self, "_diagram_settings")
                        else None
                    ),
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
