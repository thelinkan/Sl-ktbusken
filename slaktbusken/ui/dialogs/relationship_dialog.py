"""Relationship calculator dialog for Släktbusken.

Allows the user to select two persons and compute genealogical or legal
relationships between them.  Results are displayed as Swedish text and a
graphical path diagram with person nodes and connecting edges.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from slaktbusken.model.project import ProjectData

from slaktbusken.model.person import Person
from slaktbusken.relationship.calculator import RelationshipCalculator, RelationshipPath


class RelationshipDialog(QDialog):
    """Dialog for computing and displaying relationships between two persons.

    Provides two person selectors (filterable combo boxes), options for
    blood-only vs all relationships and closest-only vs all paths, a
    result text area with the Swedish kinship term, a graphical path
    diagram rendered via QGraphicsView, and print support.

    Args:
        data: The ProjectData containing all persons and families.
        parent: Optional parent widget.
    """

    # Layout constants for the graph
    _NODE_WIDTH = 140
    _NODE_HEIGHT = 50
    _NODE_SPACING_X = 60
    _NODE_CORNER_RADIUS = 8

    def __init__(self, data: "ProjectData", parent: Optional[QWidget] = None) -> None:
        """Initialise the RelationshipDialog.

        Args:
            data: Project data used for relationship computation.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._data = data
        self._calculator = RelationshipCalculator(data)
        self._persons: list[Person] = sorted(
            data.persons, key=lambda p: self._person_display_name(p)
        )
        self._person_id_map: dict[int, str] = {}  # combo index -> person id

        self.setWindowTitle("Släktskapsberäknare")
        self.setMinimumSize(800, 600)
        self.resize(900, 650)

        self._setup_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the dialog UI programmatically."""
        main_layout = QVBoxLayout(self)

        # --- Person selection group ---
        person_group = QGroupBox("Välj personer")
        person_layout = QVBoxLayout()

        # Person A
        row_a = QHBoxLayout()
        row_a.addWidget(QLabel("Person A:"))
        self._combo_a = QComboBox()
        self._combo_a.setEditable(True)
        self._combo_a.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._combo_a.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._combo_a.setMinimumWidth(250)
        row_a.addWidget(self._combo_a)
        person_layout.addLayout(row_a)

        # Person B
        row_b = QHBoxLayout()
        row_b.addWidget(QLabel("Person B:"))
        self._combo_b = QComboBox()
        self._combo_b.setEditable(True)
        self._combo_b.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._combo_b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._combo_b.setMinimumWidth(250)
        row_b.addWidget(self._combo_b)
        person_layout.addLayout(row_b)

        person_group.setLayout(person_layout)
        main_layout.addWidget(person_group)

        # Populate combo boxes
        self._populate_person_combos()

        # --- Options group ---
        options_group = QGroupBox("Alternativ")
        options_layout = QHBoxLayout()

        self._check_blood_only = QCheckBox("Visa endast blodsband")
        self._check_blood_only.setToolTip(
            "Visa bara biologiska (genealogiska) relationer"
        )
        options_layout.addWidget(self._check_blood_only)

        self._check_all_paths = QCheckBox("Visa alla relationsvägar")
        self._check_all_paths.setToolTip(
            "Visa alla relationsvägar (max 50), inte bara den närmaste"
        )
        options_layout.addWidget(self._check_all_paths)

        options_layout.addStretch()

        self._btn_calculate = QPushButton("Beräkna")
        self._btn_calculate.setToolTip("Beräkna släktskapsrelation")
        self._btn_calculate.setDefault(True)
        options_layout.addWidget(self._btn_calculate)

        options_group.setLayout(options_layout)
        main_layout.addWidget(options_group)

        # --- Result text area ---
        self._result_label = QLabel("")
        self._result_label.setWordWrap(True)
        self._result_label.setStyleSheet("font-size: 13pt; padding: 6px;")
        self._result_label.setMinimumHeight(40)
        main_layout.addWidget(self._result_label)

        # --- Graphics view for path diagram ---
        self._scene = QGraphicsScene(self)
        self._view = self._create_zoomable_view(self._scene)
        self._view.setMinimumHeight(200)
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(self._view)

        # --- Bottom button row ---
        button_row = QHBoxLayout()
        button_row.addStretch()

        self._btn_print = QPushButton("Skriv ut...")
        self._btn_print.setToolTip("Skriv ut relationsdiagrammet")
        self._btn_print.setEnabled(False)
        button_row.addWidget(self._btn_print)

        self._btn_close = QPushButton("Stäng")
        self._btn_close.setToolTip("Stäng dialogen")
        button_row.addWidget(self._btn_close)

        main_layout.addLayout(button_row)

    def _connect_signals(self) -> None:
        """Connect widget signals to slots."""
        self._btn_calculate.clicked.connect(self._on_calculate)
        self._btn_print.clicked.connect(self._on_print)
        self._btn_close.clicked.connect(self.close)

    def _create_zoomable_view(self, scene: QGraphicsScene) -> QGraphicsView:
        """Create a QGraphicsView with mouse-wheel zoom and click-drag panning.

        Zoom range: 25% to 400%. Scroll wheel zooms centered on the mouse
        cursor. Left-click drag pans the view.

        Args:
            scene: The QGraphicsScene to display.

        Returns:
            Configured QGraphicsView instance.
        """
        view = QGraphicsView(scene, self)
        view.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        view.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Store zoom state on the view object
        view._zoom_factor = 1.0  # type: ignore[attr-defined]

        # Override wheelEvent via an event filter
        view.installEventFilter(self)
        return view

    def eventFilter(self, obj, event) -> bool:
        """Handle mouse wheel zoom on the graphics view.

        Zooms in/out between 25% and 400%, centered on the cursor.

        Args:
            obj: The object that received the event.
            event: The event to filter.

        Returns:
            True if the event was handled, False otherwise.
        """
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QWheelEvent

        if obj is self._view and event.type() == QEvent.Type.Wheel:
            wheel_event: QWheelEvent = event  # type: ignore[assignment]
            angle = wheel_event.angleDelta().y()
            if angle == 0:
                return False

            zoom_step = 1.15
            min_zoom = 0.25
            max_zoom = 4.0

            factor = zoom_step if angle > 0 else 1.0 / zoom_step
            current = self._view._zoom_factor  # type: ignore[attr-defined]
            new_zoom = current * factor

            # Clamp
            if new_zoom < min_zoom:
                factor = min_zoom / current
                new_zoom = min_zoom
            elif new_zoom > max_zoom:
                factor = max_zoom / current
                new_zoom = max_zoom

            if abs(factor - 1.0) < 0.001:
                return True

            self._view._zoom_factor = new_zoom  # type: ignore[attr-defined]
            self._view.scale(factor, factor)
            return True

        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Person combo population
    # ------------------------------------------------------------------

    def _populate_person_combos(self) -> None:
        """Fill both person combo boxes with all persons sorted by name."""
        self._combo_a.clear()
        self._combo_b.clear()
        self._person_id_map.clear()

        display_names: list[str] = []
        for idx, person in enumerate(self._persons):
            display = self._person_display_name(person)
            self._combo_a.addItem(display)
            self._combo_b.addItem(display)
            self._person_id_map[idx] = person.id
            display_names.append(display)

        # Create custom QCompleter with substring matching for each combo box
        for combo in (self._combo_a, self._combo_b):
            completer = QCompleter(display_names, combo)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            combo.setCompleter(completer)

    # ------------------------------------------------------------------
    # Calculation
    # ------------------------------------------------------------------

    def _on_calculate(self) -> None:
        """Run the relationship calculation and display results."""
        idx_a = self._combo_a.currentIndex()
        idx_b = self._combo_b.currentIndex()

        if idx_a < 0 or idx_b < 0:
            self._show_no_result("Välj två personer att beräkna släktskap mellan.")
            return

        person_a_id = self._person_id_map.get(idx_a)
        person_b_id = self._person_id_map.get(idx_b)

        if not person_a_id or not person_b_id:
            self._show_no_result("Välj två personer att beräkna släktskap mellan.")
            return

        if person_a_id == person_b_id:
            self._show_no_result("Du har valt samma person. Välj två olika personer.")
            return

        blood_only = self._check_blood_only.isChecked()
        all_paths = self._check_all_paths.isChecked()

        paths = self._calculator.find_relationships(
            person_a_id=person_a_id,
            person_b_id=person_b_id,
            include_legal=not blood_only,
            closest_only=not all_paths,
        )

        if not paths:
            self._show_no_result(
                "Ingen släktskapsrelation hittades mellan de valda personerna."
            )
            return

        # Display results
        self._display_results(paths)

    def _show_no_result(self, message: str) -> None:
        """Show a message when no relationship is found.

        Args:
            message: The Swedish-language message to display.
        """
        self._result_label.setText(message)
        self._scene.clear()
        self._btn_print.setEnabled(False)

    def _display_results(self, paths: list[RelationshipPath]) -> None:
        """Display relationship results as text and graphical diagram.

        Args:
            paths: List of computed relationship paths.
        """
        # Deduplicate paths by swedish_term (keep one representative per term)
        seen_terms: set[str] = set()
        unique_paths: list[RelationshipPath] = []
        for path in paths:
            if path.swedish_term not in seen_terms:
                seen_terms.add(path.swedish_term)
                unique_paths.append(path)

        # Build text description
        descriptions: list[str] = []
        for i, path in enumerate(unique_paths, 1):
            term = self._calculator.describe_relationship(path)
            person_a_name = self._get_person_name(path.person_a_id)
            person_b_name = self._get_person_name(path.person_b_id)
            if len(unique_paths) == 1:
                desc = (
                    f"{person_b_name} är {term} till {person_a_name}"
                )
            else:
                desc = (
                    f"{i}. {person_b_name} är {term} till {person_a_name}"
                )
            if path.relationship_type != "blood":
                desc += f" ({path.relationship_type})"
            descriptions.append(desc)

        self._result_label.setText("\n".join(descriptions))

        # Draw all unique paths in a unified generational graph
        self._draw_generational_diagram(unique_paths)
        self._btn_print.setEnabled(True)

    # ------------------------------------------------------------------
    # Generational 2D diagram
    # ------------------------------------------------------------------

    # Path colors for distinguishing multiple relationships
    _PATH_COLORS = [
        "#2980b9",  # blue
        "#c0392b",  # red
        "#27ae60",  # green
        "#8e44ad",  # purple
        "#d35400",  # orange
        "#16a085",  # teal
    ]

    def _draw_generational_diagram(self, paths: list[RelationshipPath]) -> None:
        """Draw a unified 2D generational diagram for all relationship paths.

        The Y-axis represents generation (oldest at top, targets at bottom).
        Each person appears once at its correct generation level.
        Multiple paths are drawn with different colors.

        The layout algorithm:
        1. Merge all paths into a unified node set with generation levels.
        2. Assign generation 0 to the two target persons (bottom row).
        3. Walking up path edges: each 'child' edge increments generation.
        4. Walking down path edges: each 'parent' edge decrements generation.
        5. For the visual: highest generation number = top row.
        6. X positions are assigned per row to spread nodes evenly.

        Args:
            paths: List of relationship paths to visualize together.
        """
        self._scene.clear()

        if not paths:
            return

        person_a_id = paths[0].person_a_id
        person_b_id = paths[0].person_b_id

        # Step 1: Determine generation level for every person across all paths.
        # Generation is defined as: targets = 0, parents = 1, grandparents = 2, etc.
        # We compute this by walking each path and tracking how far "up" we go.
        person_generation: dict[str, int] = {}
        all_edges: set[tuple[str, str, int]] = set()  # (parent_id, child_id, path_index)

        for path_idx, path in enumerate(paths):
            nodes = path.path_nodes
            edges = path.path_edges

            # Assign generation to person A and B
            person_generation.setdefault(person_a_id, 0)
            person_generation.setdefault(person_b_id, 0)

            # Walk the path and compute generations relative to person_a.
            # path_nodes[0] = person_a, path goes up then down.
            # 'child' edge means going UP (current → parent), so gen increases.
            # 'parent' edge means going DOWN (current → child), so gen decreases.
            current_gen = 0
            for i, edge_type in enumerate(edges):
                current_node = nodes[i]
                next_node = nodes[i + 1]

                if edge_type == "child":
                    # Going up: next node is a parent (higher generation)
                    current_gen += 1
                    parent_id, child_id = next_node, current_node
                elif edge_type == "parent":
                    # Going down: next node is a child (lower generation)
                    current_gen -= 1
                    parent_id, child_id = current_node, next_node
                else:
                    # Partner edge: same generation
                    parent_id, child_id = None, None

                # Assign generation to next node (take the max if already set,
                # since we want the highest generation level for proper display)
                if next_node not in person_generation:
                    person_generation[next_node] = current_gen
                else:
                    person_generation[next_node] = max(
                        person_generation[next_node], current_gen
                    )

                if parent_id and child_id:
                    all_edges.add((parent_id, child_id, path_idx))

        # Step 2: Group persons by generation row.
        max_gen = max(person_generation.values()) if person_generation else 0
        min_gen = min(person_generation.values()) if person_generation else 0

        rows: dict[int, list[str]] = {}
        for pid, gen in person_generation.items():
            rows.setdefault(gen, []).append(pid)

        # Step 3: Assign X positions within each row.
        # Strategy: for each row, sort persons so that persons connected by
        # edges to the same parent/child are grouped together. Then spread
        # evenly.
        node_w = self._NODE_WIDTH
        node_h = self._NODE_HEIGHT
        spacing_x = 40
        spacing_y = 80

        # First pass: determine ordering within rows to minimize edge crossings.
        # Simple heuristic: sort by average X of connected nodes in adjacent rows.
        # Start from top (highest generation) and propagate downward.
        row_order: dict[int, list[str]] = {}
        for gen in sorted(rows.keys(), reverse=True):
            row_order[gen] = list(rows[gen])

        # Refine ordering using parent-child connectivity
        for gen in sorted(rows.keys(), reverse=True):
            if gen - 1 in row_order:
                # Sort the child row based on their parent's position
                parent_positions = {
                    pid: idx for idx, pid in enumerate(row_order[gen])
                }
                children = row_order[gen - 1]

                def child_sort_key(child_id: str) -> float:
                    """Sort key: average X position of parents."""
                    parent_xs = []
                    for parent_id, cid, _ in all_edges:
                        if cid == child_id and parent_id in parent_positions:
                            parent_xs.append(parent_positions[parent_id])
                    return sum(parent_xs) / len(parent_xs) if parent_xs else 0

                row_order[gen - 1] = sorted(children, key=child_sort_key)

        # Step 4: Compute pixel positions.
        # Center each row horizontally.
        positions: dict[str, tuple[float, float]] = {}

        # Find the widest row to determine total width
        max_row_count = max(len(r) for r in row_order.values()) if row_order else 1
        total_width = max_row_count * (node_w + spacing_x) - spacing_x

        for gen, pids in row_order.items():
            row_width = len(pids) * (node_w + spacing_x) - spacing_x
            x_offset = (total_width - row_width) / 2
            # Y: highest generation at top, generation 0 at bottom
            y = (max_gen - gen) * (node_h + spacing_y) + 20

            for idx, pid in enumerate(pids):
                x = x_offset + idx * (node_w + spacing_x) + 20
                positions[pid] = (x, y)

        # Step 5: Draw edges (lines from parent to child).
        drawn_edges: set[tuple[str, str]] = set()
        for parent_id, child_id, path_idx in all_edges:
            edge_key = (parent_id, child_id)
            if edge_key in drawn_edges:
                continue
            drawn_edges.add(edge_key)

            # Determine which paths this edge belongs to (for coloring)
            edge_paths = [
                pi for (pid, cid, pi) in all_edges
                if pid == parent_id and cid == child_id
            ]
            color_idx = edge_paths[0] % len(self._PATH_COLORS)
            color = QColor(self._PATH_COLORS[color_idx])

            px, py = positions[parent_id]
            cx, cy = positions[child_id]

            # Line from bottom-center of parent to top-center of child
            x1 = px + node_w / 2
            y1 = py + node_h
            x2 = cx + node_w / 2
            y2 = cy

            pen = QPen(color, 2.0)
            self._scene.addLine(x1, y1, x2, y2, pen)

        # Step 6: Draw partner edges (horizontal dashed lines at same level).
        for path in paths:
            for i, edge_type in enumerate(path.path_edges):
                if edge_type == "partner":
                    pid_a = path.path_nodes[i]
                    pid_b = path.path_nodes[i + 1]
                    if pid_a in positions and pid_b in positions:
                        ax, ay = positions[pid_a]
                        bx, by = positions[pid_b]
                        x1 = ax + node_w / 2
                        y1 = ay + node_h / 2
                        x2 = bx + node_w / 2
                        y2 = by + node_h / 2
                        pen = QPen(QColor("#e74c3c"), 1.5, Qt.PenStyle.DashLine)
                        self._scene.addLine(x1, y1, x2, y2, pen)

        # Step 7: Draw nodes on top.
        text_font = QFont("Sans", 9)
        target_brush = QBrush(QColor("#d4efdf"))  # green tint for targets
        normal_brush = QBrush(QColor("#eaf2f8"))  # light blue for others
        ancestor_brush = QBrush(QColor("#fdebd0"))  # light orange for common ancestors
        target_pen = QPen(QColor("#1a8c4e"), 2.5)
        normal_pen = QPen(QColor("#2980b9"), 1.5)
        ancestor_pen = QPen(QColor("#d35400"), 2.0)

        # Collect all common ancestors across paths
        common_ancestors: set[str] = set()
        for path in paths:
            common_ancestors.update(path.common_ancestor_ids)

        for pid, (x, y) in positions.items():
            # Choose style based on role
            if pid in (person_a_id, person_b_id):
                brush = target_brush
                pen = target_pen
            elif pid in common_ancestors:
                brush = ancestor_brush
                pen = ancestor_pen
            else:
                brush = normal_brush
                pen = normal_pen

            # Rounded rectangle
            path_item = QPainterPath()
            path_item.addRoundedRect(
                QRectF(x, y, node_w, node_h),
                self._NODE_CORNER_RADIUS,
                self._NODE_CORNER_RADIUS,
            )
            self._scene.addPath(path_item, pen, brush)

            # Person name text
            name = self._get_person_name(pid)
            text_item = self._scene.addSimpleText(name)
            text_item.setFont(text_font)
            text_rect = text_item.boundingRect()

            # Truncate if too wide
            if text_rect.width() > node_w - 10:
                shortened = name
                while text_rect.width() > node_w - 14 and len(shortened) > 3:
                    shortened = shortened[:-1]
                    text_item.setText(shortened + "…")
                    text_rect = text_item.boundingRect()

            text_x = x + (node_w - text_rect.width()) / 2
            text_y = y + (node_h - text_rect.height()) / 2
            text_item.setPos(text_x, text_y)

        # Step 8: Add a legend if multiple paths with different colors.
        if len(paths) > 1:
            legend_y = (max_gen - min_gen + 1) * (node_h + spacing_y) + 40
            legend_x = 20.0
            legend_font = QFont("Sans", 8)
            for i, path in enumerate(paths):
                color = QColor(self._PATH_COLORS[i % len(self._PATH_COLORS)])
                # Color swatch
                self._scene.addRect(
                    QRectF(legend_x, legend_y, 14, 14),
                    QPen(color, 1),
                    QBrush(color),
                )
                # Label
                label = self._scene.addSimpleText(f" {path.swedish_term}")
                label.setFont(legend_font)
                label.setPos(legend_x + 18, legend_y - 1)
                legend_y += 20

        # Fit the view to the scene content initially
        self._scene.setSceneRect(
            self._scene.itemsBoundingRect().adjusted(-15, -15, 15, 15)
        )
        # Reset zoom and fit to show the full graph
        self._view.resetTransform()
        self._view._zoom_factor = 1.0  # type: ignore[attr-defined]
        self._view.fitInView(
            self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio
        )
        # Record the actual zoom after fitInView so wheel zoom builds on it
        transform = self._view.transform()
        self._view._zoom_factor = transform.m11()  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Print support
    # ------------------------------------------------------------------

    def _on_print(self) -> None:
        """Open a print dialog and render the relationship graph to the printer."""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Skriv ut relationsdiagram")

        if dialog.exec() == QDialog.DialogCode.Accepted:
            painter = QPainter(printer)
            self._scene.render(painter)
            painter.end()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _person_display_name(person: Person) -> str:
        """Get display name for a person (Förnamn Efternamn).

        Args:
            person: The Person instance.

        Returns:
            Formatted display name string.
        """
        if person.names:
            name = person.names[0]
            parts = []
            if name.given:
                parts.append(name.given)
            if name.surname:
                parts.append(name.surname)
            if parts:
                return " ".join(parts)
        return f"[Okänd] ({person.id})"

    def _get_person_name(self, person_id: str) -> str:
        """Look up a person's display name by ID.

        Args:
            person_id: The person's ID.

        Returns:
            The formatted display name.
        """
        for person in self._data.persons:
            if person.id == person_id:
                return self._person_display_name(person)
        return person_id
