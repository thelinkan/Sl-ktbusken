"""Comparison_Family_View: one zoomable family view of a Person_Slot.

The view renders through the existing :class:`FamilyView` (so parents,
partners, children and siblings, every ``parentage_type`` styling and the
diagram settings are the existing ones) into its own scene with its own
:class:`ZoomableGraphicsView`. Focus, expansion, selection and zoom belong to
this view alone. The view never modifies genealogical data.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

import shiboken6
from PySide6.QtCore import QEvent, QPointF, Qt, Signal
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QLabel,
    QMenu,
    QStackedLayout,
    QWidget,
)

from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.settings_io import DiagramSettings, PersonBoxConfig
from slaktbusken.services.diagram_lookup import (
    DiagramLookup,
    find_parent_families,
    find_partner_families,
    find_person,
)
from slaktbusken.ui.diagram_panel import ZoomableGraphicsView
from slaktbusken.ui.views.family_view import FamilyView, _build_display_data
from slaktbusken.ui.widgets.connection_line import ConnectionLineItem, ConnectionType
from slaktbusken.ui.widgets.person_box import PersonBoxItem, _BOX_WIDTH

logger = logging.getLogger(__name__)

EMPTY_STATE_TEXT = "Ingen person är vald i den här platsen."
MAX_EXPANDED = 5

_BAND_GAP = 80.0
_BAND_H_GAP = 40.0
_BAND_V_GAP = 40.0
_BAND_LABEL_HEIGHT = 22.0

USE_AS_COMPARED_TEXT = "Använd som jämförd person"
EXPAND_TEXT = "Visa släkt"
COLLAPSE_TEXT = "Dölj släkt"


def _display_name(data: ProjectData, person_id: str) -> str:
    person = find_person(data, person_id)
    if person is None or not person.names:
        return person_id
    name = person.names[0]
    return f"{name.given.replace('*', '')} {name.surname}".strip() or person_id


class ComparisonFamilyView(QWidget):
    """Family view of one slot with an empty-state indication.

    Signals:
        person_clicked(str): a box was selected in this view.
        person_navigated(str): a box was double-clicked; re-centre this view.
        use_as_slot_requested(str): "Använd som jämförd person" was chosen.
        expansion_toggled(str): "Visa/Dölj släkt" was chosen for a person.
        zoom_changed(float): this view's zoom changed.
        rendered(): a render finished (overlay hooks have run).
    """

    person_clicked = Signal(str)
    person_navigated = Signal(str)
    use_as_slot_requested = Signal(str)
    expansion_toggled = Signal(str)
    zoom_changed = Signal(float)
    rendered = Signal()

    def __init__(self, view_index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.view_index = view_index
        self._family_view = FamilyView()
        self._extra_boxes: list[PersonBoxItem] = []
        self._focal_id: Optional[str] = None
        self._selected_id: Optional[str] = None
        self._expanded: tuple[str, ...] = ()
        self._lookup: Optional[DiagramLookup] = None
        self._overlay_hooks: list[Callable[["ComparisonFamilyView"], None]] = []

        self._scene = QGraphicsScene(self)
        self._view = ZoomableGraphicsView(self._scene, self)
        self._view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._view.setAccessibleName(f"Familjevy {view_index + 1}")
        self._view.viewport().installEventFilter(self)
        self._view.zoom_changed.connect(self.zoom_changed)

        self._empty_label = QLabel(EMPTY_STATE_TEXT, self)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setAccessibleName("Tom plats")

        layout = QStackedLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)
        layout.addWidget(self._empty_label)
        self._stack = layout
        layout.setCurrentWidget(self._empty_label)

    # -- accessors -----------------------------------------------------------

    @property
    def scene(self) -> QGraphicsScene:
        return self._scene

    @property
    def graphics_view(self) -> ZoomableGraphicsView:
        return self._view

    @property
    def focal_id(self) -> Optional[str]:
        return self._focal_id

    @property
    def selected_id(self) -> Optional[str]:
        return self._selected_id

    @property
    def lookup(self) -> Optional[DiagramLookup]:
        """The render-scoped lookup used by the last render."""
        return self._lookup

    @property
    def zoom_factor(self) -> float:
        return self._view.zoom_factor

    def set_zoom(self, factor: float) -> None:
        """Set this view's zoom; blocks the signal so no feedback loop starts."""
        self._view.blockSignals(True)
        try:
            self._view.set_zoom(factor)
        finally:
            self._view.blockSignals(False)

    def is_empty_state(self) -> bool:
        return self._stack.currentWidget() is self._empty_label

    def empty_state_text(self) -> str:
        return self._empty_label.text()

    def person_boxes(self) -> list[PersonBoxItem]:
        """All boxes drawn in this view (main diagram and expansion bands)."""
        return [
            b
            for b in (*self._family_view.get_person_boxes(), *self._extra_boxes)
            if shiboken6.isValid(b)
        ]

    def visible_person_ids(self) -> set[str]:
        """Ids drawn in this view, siblings included."""
        return {b.person_id for b in self.person_boxes()}

    def box_for(self, person_id: str) -> Optional[PersonBoxItem]:
        for box in self.person_boxes():
            if box.person_id == person_id:
                return box
        return None

    def add_overlay_hook(self, hook: Callable[["ComparisonFamilyView"], None]) -> None:
        """Register a callable run after every render (markers, chips)."""
        self._overlay_hooks.append(hook)

    # -- rendering -------------------------------------------------------------

    def render(
        self,
        data: ProjectData,
        focal_id: Optional[str],
        config: PersonBoxConfig,
        diagram_settings: Optional[DiagramSettings] = None,
        project_folder: Optional[Path] = None,
        expanded: tuple[str, ...] = (),
        selected_id: Optional[str] = None,
        lookup: Optional[DiagramLookup] = None,
    ) -> None:
        """Redraw the view; zoom and scroll position are kept."""
        self._lookup = lookup
        self._extra_boxes = []
        self._family_view._person_boxes = []
        self._family_view._placeholder_boxes = []
        self._scene.blockSignals(True)
        try:
            self._scene.clear()
        finally:
            self._scene.blockSignals(False)

        focal = find_person(data, focal_id) if focal_id else None
        self._focal_id = focal.id if focal is not None else None
        if focal is None:
            self._selected_id = None
            self._expanded = ()
            self._stack.setCurrentWidget(self._empty_label)
            self.rendered.emit()
            return

        self._stack.setCurrentWidget(self._view)
        main_person_id = data.project.main_person_id
        self._family_view.render(
            self._scene,
            data,
            focal.id,
            config,
            ancestor_set=set(),
            descendant_set=set(),
            project_folder=project_folder,
            diagram_settings=diagram_settings,
        )
        for box in self._family_view.get_person_boxes():
            box.setFlag(box.GraphicsItemFlag.ItemIsSelectable, False)

        valid = [pid for pid in expanded if find_person(data, pid) is not None]
        self._expanded = tuple(valid[:MAX_EXPANDED])
        self._render_bands(data, config, project_folder, main_person_id)

        self.set_selected(selected_id)
        scene_rect = self._scene.itemsBoundingRect().adjusted(-30, -30, 30, 30)
        self._scene.setSceneRect(scene_rect)
        for hook in list(self._overlay_hooks):
            try:
                hook(self)
            except Exception:  # noqa: BLE001 - an overlay must not break the view
                logger.exception("Överlägg i jämförelsevyn misslyckades.")
        self.rendered.emit()

    def _render_bands(
        self,
        data: ProjectData,
        config: PersonBoxConfig,
        project_folder: Optional[Path],
        main_person_id: Optional[str],
    ) -> None:
        """One band per expanded person: parents, partners and children."""
        if not self._expanded:
            return
        main_rect = self._scene.itemsBoundingRect()
        x = main_rect.left()
        y = main_rect.bottom() + _BAND_GAP

        def make_box(pid: str) -> Optional[PersonBoxItem]:
            person = find_person(data, pid)
            if person is None:
                return None
            display = _build_display_data(person, data, project_folder)
            display["is_ancestor"] = False
            display["is_descendant"] = False
            display["is_main_person"] = pid == main_person_id
            box = PersonBoxItem(pid, display, config)
            self._scene.addItem(box)
            self._extra_boxes.append(box)
            return box

        for pid in self._expanded:
            label = QGraphicsSimpleTextItem(f"Släkt till {_display_name(data, pid)}")
            label.setPos(x, y)
            self._scene.addItem(label)
            top = y + _BAND_LABEL_HEIGHT

            parent_ids: list[str] = []
            families = find_parent_families(data, pid)
            if families:
                parent_ids = [p.person_id for p in families[0].partners]
            partner_ids: list[str] = []
            child_ids: list[str] = []
            for family in find_partner_families(data, pid):
                for partner in family.partners:
                    if partner.person_id != pid and partner.person_id not in partner_ids:
                        partner_ids.append(partner.person_id)
                for child_id in family.children:
                    if child_id not in child_ids:
                        child_ids.append(child_id)

            parents = [b for b in (make_box(p) for p in parent_ids) if b is not None]
            focus_box = make_box(pid)
            partners = [b for b in (make_box(p) for p in partner_ids) if b is not None]
            children = [b for b in (make_box(c) for c in child_ids) if b is not None]

            width = max(
                len(parents) * (_BOX_WIDTH + _BAND_H_GAP),
                (1 + len(partners)) * (_BOX_WIDTH + _BAND_H_GAP),
                len(children) * (_BOX_WIDTH + _BAND_H_GAP),
            )

            row_y = top
            parent_height = max((b.box_height for b in parents), default=0.0)
            for i, box in enumerate(parents):
                box.setPos(x + i * (_BOX_WIDTH + _BAND_H_GAP), row_y)
            if parents:
                row_y += parent_height + _BAND_V_GAP

            focus_height = 0.0
            if focus_box is not None:
                focus_box.setPos(x, row_y)
                focus_height = focus_box.box_height
                for parent_box in parents:
                    self._scene.addItem(
                        ConnectionLineItem(
                            QPointF(parent_box.x() + _BOX_WIDTH / 2.0, parent_box.y() + parent_box.box_height),
                            QPointF(x + _BOX_WIDTH / 2.0, row_y),
                            ConnectionType.PARENT_CHILD,
                        )
                    )
            for i, box in enumerate(partners, start=1):
                box.setPos(x + i * (_BOX_WIDTH + _BAND_H_GAP), row_y)
                focus_height = max(focus_height, box.box_height)
                mid_y = row_y + box.box_height / 2.0
                self._scene.addItem(
                    ConnectionLineItem(
                        QPointF(x + (i - 1) * (_BOX_WIDTH + _BAND_H_GAP) + _BOX_WIDTH, mid_y),
                        QPointF(x + i * (_BOX_WIDTH + _BAND_H_GAP), mid_y),
                        ConnectionType.PARTNER,
                    )
                )
            row_y += focus_height + _BAND_V_GAP

            child_height = 0.0
            for i, box in enumerate(children):
                box.setPos(x + i * (_BOX_WIDTH + _BAND_H_GAP), row_y)
                child_height = max(child_height, box.box_height)
                if focus_box is not None:
                    self._scene.addItem(
                        ConnectionLineItem(
                            QPointF(x + _BOX_WIDTH / 2.0, focus_box.y() + focus_box.box_height),
                            QPointF(x + i * (_BOX_WIDTH + _BAND_H_GAP) + _BOX_WIDTH / 2.0, row_y),
                            ConnectionType.PARENT_CHILD,
                        )
                    )
            x += width + _BAND_GAP

    # -- selection ---------------------------------------------------------------

    def set_selected(self, person_id: Optional[str]) -> None:
        """Highlight one box (or none) in this view only."""
        boxes = self.person_boxes()
        if person_id is not None and not any(b.person_id == person_id for b in boxes):
            person_id = None
        self._selected_id = person_id
        self._family_view.selected_person_id = person_id
        for box in boxes:
            box.set_selected(person_id is not None and box.person_id == person_id)

    # -- interaction -------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt API
        if obj is self._view.viewport():
            etype = event.type()
            if etype in (
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonDblClick,
            ):
                box = self._box_at(event.position().toPoint())
                if box is not None and event.button() == Qt.MouseButton.LeftButton:
                    if etype == QEvent.Type.MouseButtonDblClick:
                        self.person_navigated.emit(box.person_id)
                        return True
                    self.person_clicked.emit(box.person_id)
                elif box is not None and event.button() == Qt.MouseButton.RightButton:
                    self.show_context_menu(box.person_id, event.globalPosition().toPoint())
                    return True
        return super().eventFilter(obj, event)

    def _box_at(self, view_pos) -> Optional[PersonBoxItem]:
        item = self._scene.itemAt(self._view.mapToScene(view_pos), self._view.transform())
        while item is not None and not isinstance(item, PersonBoxItem):
            item = item.parentItem()
        return item if isinstance(item, PersonBoxItem) else None

    def build_context_menu(self, person_id: str) -> QMenu:
        """Menu of a box: use as compared person, expand or collapse."""
        menu = QMenu(self)
        use = menu.addAction(USE_AS_COMPARED_TEXT)
        use.triggered.connect(lambda _=False, pid=person_id: self.use_as_slot_requested.emit(pid))
        expanded = person_id in self._expanded
        toggle = menu.addAction(COLLAPSE_TEXT if expanded else EXPAND_TEXT)
        toggle.setEnabled(expanded or len(self._expanded) < MAX_EXPANDED)
        toggle.triggered.connect(lambda _=False, pid=person_id: self.expansion_toggled.emit(pid))
        return menu

    def show_context_menu(self, person_id: str, global_pos) -> None:
        self.build_context_menu(person_id).exec(global_pos)
