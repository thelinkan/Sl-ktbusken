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
    QGraphicsTextItem,
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

from slaktbusken.model.name_parser import parse_given_name
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
        # We compute this by walking each path and tracking relative generation.
        # Generation 0 = the two target persons. Going up (child edge) increases,
        # going down (parent edge) decreases.
        person_generation: dict[str, int] = {}
        all_edges: set[tuple[str, str, int]] = set()  # (parent_id, child_id, path_index)
        partner_edges: list[tuple[str, str]] = []  # (node_a, node_b) from partner edges

        for path_idx, path in enumerate(paths):
            nodes = path.path_nodes
            edges = path.path_edges

            # Start from person_a at generation 0
            current_gen = person_generation.get(nodes[0], 0)
            if nodes[0] not in person_generation:
                person_generation[nodes[0]] = current_gen

            for i, edge_type in enumerate(edges):
                current_node = nodes[i]
                next_node = nodes[i + 1]
                # Use the established generation of the current node if available
                current_gen = person_generation.get(current_node, current_gen)

                if edge_type == "child":
                    # Going up: next node is a parent (higher generation)
                    next_gen = current_gen + 1
                    all_edges.add((next_node, current_node, path_idx))
                elif edge_type == "parent":
                    # Going down: next node is a child (lower generation)
                    next_gen = current_gen - 1
                    all_edges.add((current_node, next_node, path_idx))
                else:
                    # Partner edge: same generation as current
                    next_gen = current_gen
                    partner_edges.append((current_node, next_node))

                # Assign generation: use max to prefer higher placement
                # (ensures a person who is both traversed as a parent and via
                # another route always appears at the parent level)
                if next_node not in person_generation:
                    person_generation[next_node] = next_gen
                else:
                    person_generation[next_node] = max(
                        person_generation[next_node], next_gen
                    )

                current_gen = next_gen

        # Ensure both targets are at generation 0 (the baseline)
        person_generation.setdefault(person_a_id, 0)
        person_generation.setdefault(person_b_id, 0)

        # Post-process generation assignments to produce a correct visual layout.
        # Key principle: partners must appear at the same level, and parents must
        # be above their children. When a marriage crosses generations (e.g.,
        # Bertil at gen 2 married Vera at gen 1), the partner with fewer
        # descendants below them gets pulled DOWN to match the other's level.
        #
        # Algorithm:
        # 1. Enforce parent > child (bump parents UP)
        # 2. Sync partners to same level (pull the HIGHER partner DOWN to
        #    match the lower one, since the lower one has children below)
        # 3. Re-enforce parent > child (may need to bump parents again)

        # Phase 1: Enforce all parents are strictly above all children
        changed = True
        iterations = 0
        while changed and iterations < 50:
            changed = False
            iterations += 1
            for parent_id, child_id, _ in all_edges:
                p_gen = person_generation.get(parent_id, 0)
                c_gen = person_generation.get(child_id, 0)
                if p_gen <= c_gen:
                    person_generation[parent_id] = c_gen + 1
                    changed = True

        # Phase 2: Sync partners. For each partner pair, pull the one WITHOUT
        # children in the graph DOWN to match the one WITH children (who is
        # constrained by their child's level). If both have children, pull
        # the higher one down to the lower one's level (preserving the parent
        # constraint for the one with deeper descendants).
        for pa, pb in partner_edges:
            if pa not in person_generation or pb not in person_generation:
                continue
            ga = person_generation[pa]
            gb = person_generation[pb]
            if ga == gb:
                continue
            # Determine who has children in the graph (using all_edges)
            pa_has_children = any(
                pid == pa and cid in person_generation
                for pid, cid, _ in all_edges
            )
            pb_has_children = any(
                pid == pb and cid in person_generation
                for pid, cid, _ in all_edges
            )

            if pa_has_children and not pb_has_children:
                # Pull pb down to pa's level
                person_generation[pb] = ga
            elif pb_has_children and not pa_has_children:
                # Pull pa down to pb's level
                person_generation[pa] = gb
            else:
                # Both have children (or neither) — pull the higher one down
                target_gen = min(ga, gb)
                person_generation[pa] = target_gen
                person_generation[pb] = target_gen

        # Phase 3: Re-enforce parent > child after partner sync
        changed = True
        iterations = 0
        while changed and iterations < 50:
            changed = False
            iterations += 1
            for parent_id, child_id, _ in all_edges:
                p_gen = person_generation.get(parent_id, 0)
                c_gen = person_generation.get(child_id, 0)
                if p_gen <= c_gen:
                    person_generation[parent_id] = c_gen + 1
                    changed = True

        # Step 2: Group persons by generation row.
        max_gen = max(person_generation.values()) if person_generation else 0
        min_gen = min(person_generation.values()) if person_generation else 0

        rows: dict[int, list[str]] = {}
        for pid, gen in person_generation.items():
            rows.setdefault(gen, []).append(pid)

        # Step 3: Assign X positions within each row.
        # Strategy: use the barycenter heuristic with multiple up/down sweeps
        # to minimize edge crossings between adjacent layers.
        node_w = self._NODE_WIDTH
        node_h = self._NODE_HEIGHT
        spacing_x = 40
        spacing_y = 80

        # Build adjacency for ordering: parent→children and child→parents
        # (ignoring path_idx for layout purposes)
        parent_to_children: dict[str, set[str]] = {}
        child_to_parents: dict[str, set[str]] = {}
        for parent_id, child_id, _ in all_edges:
            parent_to_children.setdefault(parent_id, set()).add(child_id)
            child_to_parents.setdefault(child_id, set()).add(parent_id)

        # Detect partner pairs: two nodes at the same generation that share
        # at least one child. These must be placed adjacent in their row.
        partner_pairs: dict[int, list[tuple[str, str]]] = {}  # gen -> [(a, b), ...]
        partner_of: dict[str, str] = {}  # node -> its partner

        # Use the partner_edges collected during path traversal
        explicit_partners: set[tuple[str, str]] = set()
        for pa, pb in partner_edges:
            explicit_partners.add((pa, pb))

        for gen, pids in rows.items():
            if len(pids) < 2:
                continue
            pairs_for_gen: list[tuple[str, str]] = []
            seen: set[str] = set()
            for i in range(len(pids)):
                if pids[i] in seen:
                    continue
                for j in range(i + 1, len(pids)):
                    if pids[j] in seen:
                        continue
                    a, b = pids[i], pids[j]
                    # Check if they share a child (both are parents of same node)
                    children_a = parent_to_children.get(a, set())
                    children_b = parent_to_children.get(b, set())
                    shared_children = children_a & children_b
                    # Or if they're explicit partners from the path
                    is_explicit = (a, b) in explicit_partners or (b, a) in explicit_partners
                    if shared_children or is_explicit:
                        pairs_for_gen.append((a, b))
                        partner_of[a] = b
                        partner_of[b] = a
                        seen.add(a)
                        seen.add(b)
                        break
            if pairs_for_gen:
                partner_pairs[gen] = pairs_for_gen

        # Initial ordering: place shortest path's nodes first, keep partners adjacent
        row_order: dict[int, list[str]] = {}
        for gen in sorted(rows.keys(), reverse=True):
            row_order[gen] = []

        sorted_paths = sorted(paths, key=lambda p: len(p.path_edges))
        placed_in_row: dict[int, set[str]] = {gen: set() for gen in rows}

        for path in sorted_paths:
            for node_id in path.path_nodes:
                gen = person_generation.get(node_id)
                if gen is None:
                    continue
                if node_id in placed_in_row[gen]:
                    continue
                row = row_order[gen]
                insert_pos = len(row) // 2
                row.insert(insert_pos, node_id)
                placed_in_row[gen].add(node_id)
                # If this node has a partner, place partner immediately adjacent
                if node_id in partner_of:
                    partner = partner_of[node_id]
                    if partner not in placed_in_row[gen] and partner in rows.get(gen, []):
                        row.insert(insert_pos + 1, partner)
                        placed_in_row[gen].add(partner)

        # Add any remaining nodes at the edges
        for gen, pids in rows.items():
            for pid in pids:
                if pid not in placed_in_row[gen]:
                    row_order[gen].append(pid)
                    placed_in_row[gen].add(pid)

        # Ensure targets are placed left-right at the bottom
        if min_gen in row_order:
            bottom = row_order[min_gen]
            if person_a_id in bottom and person_b_id in bottom:
                others = [p for p in bottom if p not in (person_a_id, person_b_id)]
                row_order[min_gen] = [person_a_id] + others + [person_b_id]

        # Barycenter crossing reduction with partner constraints:
        # Partners must remain adjacent during reordering.
        def _get_partner_groups(gen: int, row: list[str]) -> list[list[str]]:
            """Group nodes into partner-pairs and singletons for ordering."""
            groups: list[list[str]] = []
            used: set[str] = set()
            for pid in row:
                if pid in used:
                    continue
                if pid in partner_of and partner_of[pid] in row:
                    partner = partner_of[pid]
                    if partner not in used:
                        groups.append([pid, partner])
                        used.add(pid)
                        used.add(partner)
                        continue
                groups.append([pid])
                used.add(pid)
            return groups

        def _barycenter_down(row_order: dict[int, list[str]]) -> None:
            """Sweep top to bottom, reordering groups by parent positions."""
            for gen in sorted(row_order.keys(), reverse=True):
                if gen - 1 not in row_order:
                    continue
                upper_pos = {pid: idx for idx, pid in enumerate(row_order[gen])}
                children_row = row_order[gen - 1]
                groups = _get_partner_groups(gen - 1, children_row)

                def group_bary(group: list[str]) -> float:
                    xs: list[float] = []
                    for node_id in group:
                        parents = child_to_parents.get(node_id, set())
                        xs.extend(upper_pos[p] for p in parents if p in upper_pos)
                    return sum(xs) / len(xs) if xs else float("inf")

                groups.sort(key=group_bary)
                row_order[gen - 1] = [pid for group in groups for pid in group]

        def _barycenter_up(row_order: dict[int, list[str]]) -> None:
            """Sweep bottom to top, reordering groups by child positions."""
            for gen in sorted(row_order.keys()):
                if gen + 1 not in row_order:
                    continue
                lower_pos = {pid: idx for idx, pid in enumerate(row_order[gen])}
                parents_row = row_order[gen + 1]
                groups = _get_partner_groups(gen + 1, parents_row)

                def group_bary(group: list[str]) -> float:
                    xs: list[float] = []
                    for node_id in group:
                        children = parent_to_children.get(node_id, set())
                        xs.extend(lower_pos[c] for c in children if c in lower_pos)
                    return sum(xs) / len(xs) if xs else float("inf")

                groups.sort(key=group_bary)
                row_order[gen + 1] = [pid for group in groups for pid in group]

        def _count_crossings(row_order: dict[int, list[str]]) -> int:
            """Count edge crossings between all adjacent layers."""
            crossings = 0
            for gen in sorted(row_order.keys(), reverse=True):
                if gen - 1 not in row_order:
                    continue
                upper_pos = {pid: idx for idx, pid in enumerate(row_order[gen])}
                lower_pos = {pid: idx for idx, pid in enumerate(row_order[gen - 1])}

                layer_edges: list[tuple[int, int]] = []
                for parent_id, child_id, _ in all_edges:
                    if parent_id in upper_pos and child_id in lower_pos:
                        layer_edges.append((upper_pos[parent_id], lower_pos[child_id]))

                for i in range(len(layer_edges)):
                    for j in range(i + 1, len(layer_edges)):
                        u1, l1 = layer_edges[i]
                        u2, l2 = layer_edges[j]
                        if (u1 - u2) * (l1 - l2) < 0:
                            crossings += 1
            return crossings

        # Run multiple iterations, keeping the best result
        best_order = {k: list(v) for k, v in row_order.items()}
        best_crossings = _count_crossings(best_order)

        for _iteration in range(12):
            _barycenter_down(row_order)
            _barycenter_up(row_order)

            current_crossings = _count_crossings(row_order)
            if current_crossings < best_crossings:
                best_crossings = current_crossings
                best_order = {k: list(v) for k, v in row_order.items()}

            if best_crossings == 0:
                break

        row_order = best_order

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

        # Step 5: Draw family-tree style connectors.
        # Pattern: couple bar → vertical trunk → sibling bar → child drops.
        # For couples (partner pairs sharing children), draw:
        #   - Horizontal bar connecting the two partners
        #   - Vertical trunk down from the bar center to a midpoint
        #   - Horizontal sibling bar at the midpoint spanning all children
        #   - Vertical drops from sibling bar to each child's top-center
        # For single parents, use a simple orthogonal L-shape.

        connector_pen_color = QColor("#555555")
        connector_pen = QPen(connector_pen_color, 1.5)
        connector_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        connector_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        drawn_edges: set[tuple[str, str]] = set()
        drawn_partner_bars: set[tuple[str, str]] = set()

        # Group edges by parent couple: find which children belong to which
        # parent pair (or single parent).
        # Build: for each generation, group children by their parent set.
        couple_children: dict[tuple[str, ...], set[str]] = {}
        for parent_id, child_id, _ in all_edges:
            if parent_id not in positions or child_id not in positions:
                continue
            drawn_edges.add((parent_id, child_id))
            # Find if this parent has a partner (same gen, shared children)
            partner = partner_of.get(parent_id)
            if partner and partner in positions:
                couple_key = tuple(sorted([parent_id, partner]))
            else:
                couple_key = (parent_id,)
            couple_children.setdefault(couple_key, set()).add(child_id)

        for couple_key, children in couple_children.items():
            children_list = sorted(
                children,
                key=lambda c: positions[c][0],  # sort by x position
            )

            if len(couple_key) == 2:
                # Couple: draw partner bar and family connector
                pa, pb = couple_key
                ax, ay = positions[pa]
                bx, by = positions[pb]

                # Partner bar: connect inner edges at vertical midpoint of boxes
                left_x = min(ax, bx) + node_w
                right_x = max(ax, bx)
                bar_y = ay + node_h / 2  # same generation, same y

                # Draw the partner bar (horizontal line between boxes)
                pair_key = (min(pa, pb), max(pa, pb))
                if pair_key not in drawn_partner_bars:
                    drawn_partner_bars.add(pair_key)
                    pen = QPen(QColor("#e74c3c"), 1.5)
                    self._scene.addLine(left_x, bar_y, right_x, bar_y, pen)

                # Trunk: vertical line from bar center down to sibling level
                trunk_x = (ax + node_w / 2 + bx + node_w / 2) / 2
                trunk_top = max(ay, by) + node_h  # below the boxes
                # Midpoint between parents' bottom and children's top
                first_child_y = min(positions[c][1] for c in children_list)
                trunk_bottom = (trunk_top + first_child_y) / 2

                path_line = QPainterPath()
                path_line.moveTo(trunk_x, trunk_top)
                path_line.lineTo(trunk_x, trunk_bottom)
                self._scene.addPath(path_line, connector_pen)

                if len(children_list) == 1:
                    # Single child: straight line down
                    cx, cy = positions[children_list[0]]
                    child_center_x = cx + node_w / 2
                    path_line = QPainterPath()
                    path_line.moveTo(trunk_x, trunk_bottom)
                    path_line.lineTo(child_center_x, trunk_bottom)
                    path_line.lineTo(child_center_x, cy)
                    self._scene.addPath(path_line, connector_pen)
                else:
                    # Multiple children: sibling bar + drops
                    leftmost_x = positions[children_list[0]][0] + node_w / 2
                    rightmost_x = positions[children_list[-1]][0] + node_w / 2

                    # Sibling bar
                    path_line = QPainterPath()
                    path_line.moveTo(leftmost_x, trunk_bottom)
                    path_line.lineTo(rightmost_x, trunk_bottom)
                    self._scene.addPath(path_line, connector_pen)

                    # Connect trunk to sibling bar if trunk_x not on the bar
                    if trunk_x < leftmost_x or trunk_x > rightmost_x:
                        path_line = QPainterPath()
                        path_line.moveTo(trunk_x, trunk_bottom)
                        path_line.lineTo(
                            max(leftmost_x, min(rightmost_x, trunk_x)),
                            trunk_bottom,
                        )
                        self._scene.addPath(path_line, connector_pen)

                    # Child drops
                    for child_id in children_list:
                        cx, cy = positions[child_id]
                        child_center_x = cx + node_w / 2
                        path_line = QPainterPath()
                        path_line.moveTo(child_center_x, trunk_bottom)
                        path_line.lineTo(child_center_x, cy)
                        self._scene.addPath(path_line, connector_pen)

            else:
                # Single parent: orthogonal L-connector from parent to each child
                parent_id = couple_key[0]
                px, py = positions[parent_id]
                parent_bottom_x = px + node_w / 2
                parent_bottom_y = py + node_h

                first_child_y = min(positions[c][1] for c in children_list)
                mid_y = (parent_bottom_y + first_child_y) / 2

                # Vertical trunk from parent
                path_line = QPainterPath()
                path_line.moveTo(parent_bottom_x, parent_bottom_y)
                path_line.lineTo(parent_bottom_x, mid_y)
                self._scene.addPath(path_line, connector_pen)

                if len(children_list) == 1:
                    cx, cy = positions[children_list[0]]
                    child_center_x = cx + node_w / 2
                    path_line = QPainterPath()
                    path_line.moveTo(parent_bottom_x, mid_y)
                    path_line.lineTo(child_center_x, mid_y)
                    path_line.lineTo(child_center_x, cy)
                    self._scene.addPath(path_line, connector_pen)
                else:
                    leftmost_x = positions[children_list[0]][0] + node_w / 2
                    rightmost_x = positions[children_list[-1]][0] + node_w / 2

                    # Sibling bar
                    path_line = QPainterPath()
                    path_line.moveTo(leftmost_x, mid_y)
                    path_line.lineTo(rightmost_x, mid_y)
                    self._scene.addPath(path_line, connector_pen)

                    # Connect trunk to bar
                    if parent_bottom_x < leftmost_x or parent_bottom_x > rightmost_x:
                        path_line = QPainterPath()
                        path_line.moveTo(parent_bottom_x, mid_y)
                        path_line.lineTo(
                            max(leftmost_x, min(rightmost_x, parent_bottom_x)),
                            mid_y,
                        )
                        self._scene.addPath(path_line, connector_pen)

                    # Child drops
                    for child_id in children_list:
                        cx, cy = positions[child_id]
                        child_center_x = cx + node_w / 2
                        path_line = QPainterPath()
                        path_line.moveTo(child_center_x, mid_y)
                        path_line.lineTo(child_center_x, cy)
                        self._scene.addPath(path_line, connector_pen)

        # Step 6: Draw any remaining partner lines not already drawn
        # (explicit partner edges from paths that weren't in partner_pairs)
        for path in paths:
            for i, edge_type in enumerate(path.path_edges):
                if edge_type == "partner":
                    pid_a = path.path_nodes[i]
                    pid_b = path.path_nodes[i + 1]
                    pair_key = (min(pid_a, pid_b), max(pid_a, pid_b))
                    if pair_key in drawn_partner_bars:
                        continue
                    drawn_partner_bars.add(pair_key)
                    if pid_a in positions and pid_b in positions:
                        ax, ay = positions[pid_a]
                        bx, by = positions[pid_b]
                        left_x = min(ax, bx) + node_w
                        right_x = max(ax, bx)
                        bar_y = (ay + by) / 2 + node_h / 2
                        pen = QPen(QColor("#e74c3c"), 1.5)
                        self._scene.addLine(left_x, bar_y, right_x, bar_y, pen)

        for gen, pairs in partner_pairs.items():
            for pa, pb in pairs:
                pair_key = (min(pa, pb), max(pa, pb))
                if pair_key in drawn_partner_bars:
                    continue
                drawn_partner_bars.add(pair_key)
                if pa in positions and pb in positions:
                    ax, ay = positions[pa]
                    bx, by = positions[pb]
                    left_x = min(ax, bx) + node_w
                    right_x = max(ax, bx)
                    bar_y = (ay + by) / 2 + node_h / 2
                    pen = QPen(QColor("#e74c3c"), 1.5)
                    self._scene.addLine(left_x, bar_y, right_x, bar_y, pen)

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

            # Person name text — use rich text for tilltalsnamn underline
            name_html = self._get_person_name_html(pid)
            text_item = QGraphicsTextItem()
            text_item.setFont(text_font)
            text_item.document().setDocumentMargin(0)
            text_item.setHtml(name_html)
            text_item.setDefaultTextColor(QColor("#000000"))
            self._scene.addItem(text_item)

            text_rect = text_item.boundingRect()

            # Truncate if too wide — fall back to plain text with ellipsis
            if text_rect.width() > node_w - 10:
                plain_name = self._get_person_name(pid)
                shortened = plain_name
                while True:
                    text_item.setHtml(shortened + "…")
                    text_rect = text_item.boundingRect()
                    if text_rect.width() <= node_w - 14 or len(shortened) <= 3:
                        break
                    shortened = shortened[:-1]

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

        Uses parse_given_name() to strip tilltalsnamn asterisk markers
        and produce a clean display string.

        Args:
            person: The Person instance.

        Returns:
            Formatted display name string.
        """
        if person.names:
            name = person.names[0]
            parts = []
            if name.given:
                try:
                    parsed = parse_given_name(name.given)
                    parts.append(parsed.display_string)
                except ValueError:
                    # Multiple markers — fall back to raw given name
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

    def _get_person_name_html(self, person_id: str) -> str:
        """Look up a person's display name as HTML with tilltalsnamn underlined.

        If the person's given name has a tilltalsnamn marker, the marked
        name part is wrapped in <u>...</u> tags. Otherwise returns plain text.

        Args:
            person_id: The person's ID.

        Returns:
            HTML-formatted name string with underlined tilltalsnamn.
        """
        for person in self._data.persons:
            if person.id == person_id:
                return self._person_display_name_html(person)
        return person_id

    @staticmethod
    def _person_display_name_html(person: Person) -> str:
        """Get HTML display name for a person with tilltalsnamn underlined.

        Uses parse_given_name() to identify the tilltalsnamn part and
        wraps it in <u>...</u> for underline rendering in QGraphicsTextItem.

        Args:
            person: The Person instance.

        Returns:
            HTML-formatted display name string.
        """
        if person.names:
            name = person.names[0]
            given_html = ""
            if name.given:
                try:
                    parsed = parse_given_name(name.given)
                    if (
                        parsed.tilltalsnamn_index is not None
                        and parsed.parts
                        and 0 <= parsed.tilltalsnamn_index < len(parsed.parts)
                    ):
                        # Build HTML with underlined tilltalsnamn part
                        html_parts = []
                        for idx, part in enumerate(parsed.parts):
                            if idx == parsed.tilltalsnamn_index:
                                html_parts.append(f"<u>{part}</u>")
                            else:
                                html_parts.append(part)
                        given_html = " ".join(html_parts)
                    else:
                        given_html = parsed.display_string
                except ValueError:
                    # Multiple markers — fall back to raw given name without asterisks
                    given_html = name.given.replace("*", "")

            parts = []
            if given_html:
                parts.append(given_html)
            if name.surname:
                parts.append(name.surname)
            if parts:
                return " ".join(parts)
        return f"[Okänd] ({person.id})"
