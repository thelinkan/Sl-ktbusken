"""DNA editor widget.

Provides a tabbed editor for DNA-related records: companies, profiles,
matches, segments, clusters, and triangulations. Each tab has a list
panel and a form panel. Validates references before saving.
All UI text is in Swedish.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.dna import (
    DnaCluster,
    DnaCompany,
    DnaMatch,
    DnaProfile,
    DnaSegment,
    DnaTriangulation,
)
from slaktbusken.model.media import MediaItem
from slaktbusken.model.person import Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.cluster_filter import get_dna_match_filtered_persons
from slaktbusken.services.dna_file_utils import delete_dna_file
from slaktbusken.services.match_segment_storage import load_match_segments
from slaktbusken.services.triangulation_format import format_triangulation_entry
from slaktbusken.ui.dialogs.chromosome_browser_dialog import ChromosomeBrowserDialog
from slaktbusken.ui.dna_match_display import format_match_entry, matches_filter
from slaktbusken.ui.generated.ui_dna_editor import Ui_DnaEditor
from slaktbusken.ui.widgets.person_search_widget import PersonSearchWidget

logger = logging.getLogger(__name__)

# Valid chromosome values
CHROMOSOMES: list[str] = [str(i) for i in range(1, 23)] + ["X", "Y"]

# Test type options
TEST_TYPES: list[str] = ["autosomal", "y-dna", "mtdna", "combined"]

# Admin status options
ADMIN_STATUSES: list[str] = ["self", "managed_by_user", "self_managed"]

# Match source options
MATCH_SOURCES: list[str] = ["internal", "external"]

# Supported logo image file extensions
LOGO_EXTENSIONS: tuple[str, ...] = ("png", "jpg", "jpeg", "gif", "svg", "bmp", "webp")

# File dialog filter string
LOGO_FILE_FILTER: str = "Bildfiler (*.png *.jpg *.jpeg *.gif *.svg *.bmp *.webp)"

# Preview/icon dimensions
LOGO_PREVIEW_SIZE: int = 64  # company form preview
LOGO_ICON_SIZE: int = 24  # match list icon


# ------------------------------------------------------------------
# Pure helper functions for logo path logic
# ------------------------------------------------------------------


def _is_inside_logo_folder(file_path: Path, logo_folder: Path) -> bool:
    """Check whether *file_path* is located within *logo_folder*.

    Uses resolved paths and case-insensitive comparison for Windows
    compatibility.
    """
    try:
        resolved_file = file_path.resolve()
        resolved_folder = logo_folder.resolve()
        return str(resolved_file).lower().startswith(str(resolved_folder).lower() + "\\") or \
            str(resolved_file).lower().startswith(str(resolved_folder).lower() + "/") or \
            str(resolved_file).lower() == str(resolved_folder).lower()
    except (OSError, ValueError):
        return False


def _compute_relative_path(file_path: Path, project_folder: Path) -> str:
    """Return the forward-slash relative path of *file_path* within *project_folder*."""
    resolved_file = file_path.resolve()
    resolved_folder = project_folder.resolve()
    relative = resolved_file.relative_to(resolved_folder)
    return relative.as_posix()


def _unique_filename(folder: Path, name: str) -> Path:
    """Generate a unique filename in *folder* by appending numeric suffix if needed.

    If ``folder / name`` does not exist, returns it directly. Otherwise
    appends ``_1``, ``_2``, etc. to the stem until a non-conflicting name
    is found.
    """
    target = folder / name
    if not target.exists():
        return target

    stem = Path(name).stem
    suffix = Path(name).suffix
    counter = 1
    while True:
        candidate = folder / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _find_media_by_path(
    media_list: list[MediaItem], rel_path: str
) -> MediaItem | None:
    """Find a MediaItem whose file path matches *rel_path* case-insensitively."""
    lower_path = rel_path.lower()
    for item in media_list:
        if item.file.lower() == lower_path:
            return item
    return None


def _create_logo_media_item(rel_path: str, filename: str) -> MediaItem:
    """Create a new MediaItem for a logo image.

    Args:
        rel_path: Forward-slash relative path from the project folder.
        filename: The image filename (used to derive the title).

    Returns:
        A new MediaItem with type="logo", a generated uuid4 id, and
        title set to the filename stem.
    """
    return MediaItem(
        id=str(uuid.uuid4()),
        type="logo",
        file=rel_path,
        title=Path(filename).stem,
    )


def _copy_to_logo_folder(source: Path, logo_folder: Path) -> Path | None:
    """Copy an external image file to the logo folder.

    Creates the logo folder if it does not exist. Uses
    :func:`_unique_filename` to avoid overwriting existing files.

    Args:
        source: Absolute path to the source image file.
        logo_folder: Absolute path to the destination logo folder.

    Returns:
        The destination :class:`Path` on success, or ``None`` if the
        copy fails due to a filesystem error.
    """
    try:
        logo_folder.mkdir(parents=True, exist_ok=True)
        destination = _unique_filename(logo_folder, source.name)
        shutil.copy2(source, destination)
        return destination
    except OSError as e:
        logger.error("Misslyckades kopiera logofil %s: %s", source, e)
        return None


# Sentinel value indicating the logo file path was resolved but the file
# does not exist on disk.
_LOGO_FILE_MISSING: str = "__MISSING__"


def _resolve_logo_file_path_for_company_id(
    company_id: str,
    project_data: ProjectData,
    project_folder: Path | None,
) -> Path | None | str:
    """Resolve the chain from a company_id to the logo file's absolute path.

    Returns:
        - ``None`` if any link in the chain is missing (no logo assigned).
        - The sentinel string :data:`_LOGO_FILE_MISSING` if the path resolves
          but the file does not exist on disk.
        - A :class:`Path` instance if the file exists on disk.
    """
    if project_folder is None:
        return None

    # Step 1: company_id → DnaCompany
    company: DnaCompany | None = None
    for c in project_data.dna_companies:
        if c.id == company_id:
            company = c
            break
    if company is None:
        return None

    # Step 2: DnaCompany.logo_media_id → MediaItem
    if company.logo_media_id is None:
        return None
    media_item: MediaItem | None = None
    for m in project_data.media:
        if m.id == company.logo_media_id:
            media_item = m
            break
    if media_item is None:
        return None

    # Step 3: MediaItem.file → absolute path
    import unicodedata
    normalized_file = unicodedata.normalize("NFC", media_item.file)
    abs_path = project_folder / Path(normalized_file)

    # Step 4: Check if file exists on disk
    if not abs_path.is_file():
        return _LOGO_FILE_MISSING

    return abs_path


def _resolve_logo_file_path(
    match: DnaMatch,
    project_data: ProjectData,
    project_folder: Path | None,
) -> Path | None | str:
    """Resolve the chain from a DnaMatch to the logo file's absolute path.

    Returns:
        - ``None`` if any link in the chain is missing (no logo assigned).
        - The sentinel string :data:`_LOGO_FILE_MISSING` if the path resolves
          but the file does not exist on disk.
        - A :class:`Path` instance if the file exists on disk.
    """
    if project_folder is None:
        return None

    # Step 1: match.profile2_id → DnaProfile
    profile: DnaProfile | None = None
    for p in project_data.dna_profiles:
        if p.id == match.profile2_id:
            profile = p
            break
    if profile is None:
        return None

    # Delegate remaining resolution to the company-level helper
    return _resolve_logo_file_path_for_company_id(
        profile.company_id, project_data, project_folder
    )


def resolve_company_logo_icon(
    match: DnaMatch,
    project_data: ProjectData,
    project_folder: Path | None,
    size: int = LOGO_ICON_SIZE,
) -> QIcon:
    """Resolve the company logo for a DNA match and return it as a QIcon.

    Follows the chain: DnaMatch → profile2 → company → logo_media_id →
    MediaItem → file → disk path → QIcon scaled to *size* × *size*.

    Returns:
        - A scaled :class:`QIcon` when the logo file exists on disk.
        - An empty :class:`QIcon` (default placeholder) when any link in the
          resolution chain is missing or ``None``.
        - A distinct "missing file" :class:`QIcon` (red-bordered pixmap) when
          the file path resolves but the file does not exist on disk.
    """
    result = _resolve_logo_file_path(match, project_data, project_folder)

    if result is None:
        # No logo assigned — return empty placeholder icon
        return QIcon()

    if result == _LOGO_FILE_MISSING:
        # File path resolved but file missing on disk — distinct indicator
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.white)
        from PySide6.QtGui import QPainter, QPen
        from PySide6.QtCore import QRect

        painter = QPainter(pixmap)
        pen = QPen(Qt.GlobalColor.red, 2)
        painter.setPen(pen)
        painter.drawRect(QRect(1, 1, size - 2, size - 2))
        # Draw an X to indicate missing
        painter.drawLine(1, 1, size - 2, size - 2)
        painter.drawLine(size - 2, 1, 1, size - 2)
        painter.end()
        return QIcon(pixmap)

    # result is a Path — load and scale
    pixmap = QPixmap(str(result))
    if pixmap.isNull():
        # Could not load the image (unsupported format, corrupt, etc.)
        return QIcon()
    scaled = pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return QIcon(scaled)


def resolve_profile_logo_icon(
    profile: DnaProfile,
    project_data: ProjectData,
    project_folder: Path | None,
    size: int = LOGO_ICON_SIZE,
) -> QIcon:
    """Resolve the company logo for a DNA profile and return it as a QIcon.

    Follows the chain: DnaProfile → company → logo_media_id →
    MediaItem → file → disk path → QIcon scaled to *size* × *size*.

    Returns:
        - A scaled :class:`QIcon` when the logo file exists on disk.
        - An empty :class:`QIcon` (default placeholder) when any link in the
          resolution chain is missing or ``None``.
        - A distinct "missing file" :class:`QIcon` (red-bordered pixmap) when
          the file path resolves but the file does not exist on disk.
    """
    result = _resolve_logo_file_path_for_company_id(
        profile.company_id, project_data, project_folder
    )

    if result is None:
        return QIcon()

    if result == _LOGO_FILE_MISSING:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.white)
        from PySide6.QtGui import QPainter, QPen
        from PySide6.QtCore import QRect

        painter = QPainter(pixmap)
        pen = QPen(Qt.GlobalColor.red, 2)
        painter.setPen(pen)
        painter.drawRect(QRect(1, 1, size - 2, size - 2))
        painter.drawLine(1, 1, size - 2, size - 2)
        painter.drawLine(size - 2, 1, 1, size - 2)
        painter.end()
        return QIcon(pixmap)

    pixmap = QPixmap(str(result))
    if pixmap.isNull():
        return QIcon()
    scaled = pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return QIcon(scaled)


class DnaEditor(QWidget):
    """Editor widget for DNA-related records with tabbed interface.

    Provides management of DNA companies, profiles, matches,
    clusters, and triangulations via a five-tab interface. Each tab
    contains a list on the left and a form on the right.

    Args:
        project_data: The current project data containing all entities.
        project_path: Optional path to the project file on disk.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        project_data: ProjectData,
        project_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the DNA editor.

        Args:
            project_data: The current project data containing all entities.
            project_path: Optional path to the project file on disk.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._project_data = project_data
        self._project_path = project_path
        self._project_folder = project_path.parent if project_path else None
        self._logo_folder = (
            self._project_folder / "media" / "logo"
            if self._project_folder
            else None
        )
        self._editing_company: Optional[DnaCompany] = None
        self._editing_profile: Optional[DnaProfile] = None
        self._editing_match: Optional[DnaMatch] = None
        self._editing_segment: Optional[DnaSegment] = None
        self._editing_cluster: Optional[DnaCluster] = None
        self._editing_triangulation: Optional[DnaTriangulation] = None

        # Set up UI from generated form
        self._ui = Ui_DnaEditor()
        self._ui.setupUi(self)

        # Remove Segment tab and reorder remaining tabs.
        # After setupUi the order is: Företag(0), Profiler(1), Matchningar(2),
        # Segment(3), Kluster(4), Triangulering(5).
        # Target order: Företag(0), Profiler(1), Matchningar(2), Triangulering(3),
        # Kluster(4).
        self._ui.tab_widget.removeTab(
            self._ui.tab_widget.indexOf(self._ui.segments_tab)
        )
        # After segment removal: Företag(0), Profiler(1), Matchningar(2),
        # Kluster(3), Triangulering(4).
        # Move Triangulering (index 4) before Kluster (index 3):
        tri_idx = self._ui.tab_widget.indexOf(self._ui.triangulations_tab)
        self._ui.tab_widget.tabBar().moveTab(tri_idx, 3)

        # Hide the logo media-ID text field and its label (Req 3.1)
        self._ui.company_logo_input.setVisible(False)
        self._ui.company_logo_label.setVisible(False)

        # Add URL field with maxLength 2048 (Req 3.7)
        self._company_url_input = QLineEdit()
        self._company_url_input.setMaxLength(2048)
        self._company_url_input.setPlaceholderText("https://")
        self._ui.company_form_layout.insertRow(2, "URL:", self._company_url_input)

        # Add logo choose button and preview label to company form (Req 3.2, 3.3, 3.4)
        self._logo_choose_button = QPushButton("Välj logo...")
        self._logo_choose_button.setEnabled(False)
        self._logo_preview_label = QLabel()
        self._logo_preview_label.setFixedSize(LOGO_PREVIEW_SIZE, LOGO_PREVIEW_SIZE)

        logo_row_layout = QHBoxLayout()
        logo_row_layout.addWidget(self._logo_choose_button)
        logo_row_layout.addWidget(self._logo_preview_label)

        self._ui.company_form_layout.insertRow(4, "", logo_row_layout)

        # ---------------------------------------------------------------
        # Profile form customization (Req 1.1–1.5, 1.7, 1.8, 4.1–4.5)
        # ---------------------------------------------------------------

        # --- Replace person_id input with read-only name label (Req 4.1, 4.2)
        self._profile_person_name_label = QLabel()
        self._profile_person_name_label.setObjectName("profile_person_name_label")
        # Hide the original editable person_id input
        self._ui.profile_person_input.hide()
        # Insert the read-only name label in the same form row (row 0 field)
        self._ui.profile_form_layout.setWidget(
            0, QFormLayout.ItemRole.FieldRole, self._profile_person_name_label
        )

        # --- Add haplogroup fields (Req 1.2–1.5, 1.8)
        self._y_haplogroup_label = QLabel("Y-haplogrupp:")
        self._y_haplogroup_input = QLineEdit()
        self._y_haplogroup_input.setMaxLength(50)
        self._y_haplogroup_input.setPlaceholderText("T.ex. R1b-M269")

        self._mt_haplogroup_label = QLabel("mt-haplogrupp:")
        self._mt_haplogroup_input = QLineEdit()
        self._mt_haplogroup_input.setMaxLength(50)
        self._mt_haplogroup_input.setPlaceholderText("T.ex. H1a1")

        # Insert haplogroup fields after test_type (row 2) — insert at row 3
        # We insert mt first at row 3, then y at row 3 so y ends up above mt
        self._ui.profile_form_layout.insertRow(
            3, self._mt_haplogroup_label, self._mt_haplogroup_input
        )
        self._ui.profile_form_layout.insertRow(
            3, self._y_haplogroup_label, self._y_haplogroup_input
        )

        # --- Replace admin_person_id input with PersonSearchWidget (Req 4.3, 4.4)
        self._admin_person_search = PersonSearchWidget()
        self._admin_person_search.setObjectName("admin_person_search_widget")
        # Hide the original admin person input
        self._ui.profile_admin_person_input.hide()
        # Find the row of the admin person field. Originally at row 5, after
        # inserting 2 haplogroup rows it's shifted to row 7.
        self._ui.profile_form_layout.setWidget(
            7, QFormLayout.ItemRole.FieldRole, self._admin_person_search
        )

        # --- Remove/hide admin_status combo box (Req 4.5)
        self._ui.profile_admin_status_combo.hide()
        self._ui.profile_admin_status_label.hide()

        # Connect test_type change signal to show/hide haplogroup fields
        self._ui.profile_test_type_combo.currentIndexChanged.connect(
            self._on_test_type_changed
        )
        # Initialize visibility based on default selection
        self._update_haplogroup_visibility()

        self._logo_choose_button.clicked.connect(self._on_choose_logo)

        # Redesign cluster tab with split-panel layout (Req 8.1–8.7)
        self._setup_cluster_panel()

        # Redesign triangulation tab — read-only detail view (Req 7.1–7.5)
        self._setup_triangulation_detail_view()

        # Add "Kromosomvy" button to match form (Req 15.1, 15.2)
        self._chromosome_view_button = QPushButton("Kromosomvy")
        self._chromosome_view_button.setObjectName("chromosome_view_button")
        self._chromosome_view_button.setEnabled(False)
        self._ui.match_form_layout.insertRow(
            9, "", self._chromosome_view_button
        )

        self._populate_combos()
        self._connect_signals()
        self._refresh_all_lists()

    # ------------------------------------------------------------------
    # Private: setup
    # ------------------------------------------------------------------

    def _on_test_type_changed(self, _index: int) -> None:
        """Handle test_type combo box change — update haplogroup field visibility.

        Req 1.2–1.5, 1.7: Show/hide haplogroup fields based on test type,
        but never clear the underlying data model values.
        """
        self._update_haplogroup_visibility()

    def _update_haplogroup_visibility(self) -> None:
        """Show or hide haplogroup fields based on current test_type selection.

        - y-dna: show Y-haplogroup only
        - mtdna: show mt-haplogroup only
        - combined: show both
        - autosomal: hide both
        """
        test_type = self._ui.profile_test_type_combo.currentData() or ""
        show_y = test_type in ("y-dna", "combined")
        show_mt = test_type in ("mtdna", "combined")

        self._y_haplogroup_label.setVisible(show_y)
        self._y_haplogroup_input.setVisible(show_y)
        self._mt_haplogroup_label.setVisible(show_mt)
        self._mt_haplogroup_input.setVisible(show_mt)

    def _setup_triangulation_detail_view(self) -> None:
        """Replace the triangulation form with a read-only detail view.

        Hides the original editable form group and replaces it with:
        - Read-only labels: Företag, Delad cM, Antal segment, Största segment,
          Anteckningar, and a profiles list
        - A "Redigera" button that opens DnaTriangulationDialog in edit mode

        Req 7.1–7.5, 2.1–2.3
        """
        # Hide the original editable form group
        self._ui.triangulation_form_group.hide()

        # Create a new QGroupBox for the read-only detail view
        self._triangulation_detail_group = QGroupBox("Trianguleringsuppgifter")
        self._triangulation_detail_group.setObjectName("triangulation_detail_group")

        detail_layout = QVBoxLayout(self._triangulation_detail_group)

        # Form layout for read-only labels
        form = QFormLayout()

        self._tri_detail_company_label = QLabel("—")
        self._tri_detail_company_label.setObjectName("tri_detail_company")
        form.addRow("Företag:", self._tri_detail_company_label)

        self._tri_detail_shared_cm_label = QLabel("—")
        self._tri_detail_shared_cm_label.setObjectName("tri_detail_shared_cm")
        form.addRow("Delad cM:", self._tri_detail_shared_cm_label)

        self._tri_detail_segment_count_label = QLabel("—")
        self._tri_detail_segment_count_label.setObjectName("tri_detail_segment_count")
        form.addRow("Antal segment:", self._tri_detail_segment_count_label)

        self._tri_detail_largest_segment_label = QLabel("—")
        self._tri_detail_largest_segment_label.setObjectName("tri_detail_largest_segment")
        form.addRow("Största segment:", self._tri_detail_largest_segment_label)

        self._tri_detail_notes_label = QLabel("—")
        self._tri_detail_notes_label.setObjectName("tri_detail_notes")
        self._tri_detail_notes_label.setWordWrap(True)
        form.addRow("Anteckningar:", self._tri_detail_notes_label)

        detail_layout.addLayout(form)

        # Profiles list (read-only)
        profiles_header = QLabel("Profiler:")
        profiles_header.setObjectName("tri_detail_profiles_header")
        detail_layout.addWidget(profiles_header)

        self._tri_detail_profiles_list = QListWidget()
        self._tri_detail_profiles_list.setObjectName("tri_detail_profiles_list")
        self._tri_detail_profiles_list.setSelectionMode(
            QListWidget.SelectionMode.NoSelection
        )
        self._tri_detail_profiles_list.setMaximumHeight(120)
        detail_layout.addWidget(self._tri_detail_profiles_list)

        # "Redigera" button (Req 7.2, 7.3)
        self._tri_edit_button = QPushButton("Redigera")
        self._tri_edit_button.setObjectName("tri_edit_button")
        self._tri_edit_button.setEnabled(False)
        self._tri_edit_button.clicked.connect(self._on_edit_triangulation)
        detail_layout.addWidget(self._tri_edit_button)

        detail_layout.addStretch()

        # Add the new detail group to the triangulations tab layout
        self._ui.triangulations_layout.addWidget(self._triangulation_detail_group)

    def _setup_cluster_panel(self) -> None:
        """Replace the cluster tab content with a split-panel layout.

        Builds a horizontal QSplitter (30%/70%):
        - Left: scrollable QListWidget of clusters
        - Right upper: scrollable QListWidget of persons in selected cluster
        - Right lower: QLabel "Anteckningar" + QTextEdit for cluster notes

        Req 8.1–8.7
        """
        # Get the cluster tab widget
        clusters_tab = self._ui.clusters_tab

        # Remove existing layout and all children
        old_layout = clusters_tab.layout()
        if old_layout is not None:
            # Delete all child widgets from old layout
            while old_layout.count():
                child = old_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                elif child.layout():
                    # Recursively delete sub-layout items
                    sub_layout = child.layout()
                    while sub_layout.count():
                        sub_child = sub_layout.takeAt(0)
                        if sub_child.widget():
                            sub_child.widget().deleteLater()
            # Remove the old layout from the widget
            from PySide6.QtWidgets import QWidget as _QW
            _QW().setLayout(old_layout)

        # Create a new layout for the clusters tab
        new_layout = QVBoxLayout(clusters_tab)
        new_layout.setContentsMargins(0, 0, 0, 0)

        # Create horizontal splitter
        self._cluster_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: cluster list (30%)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._cluster_list_widget = QListWidget()
        self._cluster_list_widget.setObjectName("cluster_panel_list")
        left_layout.addWidget(self._cluster_list_widget)

        # Right panel (70%)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 0, 0)

        # Right upper: persons list header with filter toggle
        persons_header_layout = QHBoxLayout()
        persons_label = QLabel("Personer i kluster:")
        persons_header_layout.addWidget(persons_label)
        persons_header_layout.addStretch()

        # "Visa filtrerade" toggle button (Req 9.5)
        self._cluster_filter_toggle = QPushButton("Visa filtrerade")
        self._cluster_filter_toggle.setObjectName("cluster_filter_toggle")
        self._cluster_filter_toggle.setCheckable(True)
        self._cluster_filter_toggle.setChecked(False)
        self._cluster_filter_toggle.clicked.connect(self._on_cluster_filter_toggle)
        persons_header_layout.addWidget(self._cluster_filter_toggle)

        right_layout.addLayout(persons_header_layout)

        self._cluster_persons_list = QListWidget()
        self._cluster_persons_list.setObjectName("cluster_persons_list")
        # Enable context menu (Req 9.1)
        self._cluster_persons_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._cluster_persons_list.customContextMenuRequested.connect(
            self._on_cluster_person_context_menu
        )
        right_layout.addWidget(self._cluster_persons_list, stretch=1)

        # Right lower: notes
        notes_label = QLabel("Anteckningar:")
        right_layout.addWidget(notes_label)

        self._cluster_notes_edit = QTextEdit()
        self._cluster_notes_edit.setObjectName("cluster_notes_edit")
        self._cluster_notes_edit.setPlaceholderText("Klusteranteckningar...")
        # Minimum height for 3 visible text lines (~60px)
        self._cluster_notes_edit.setMinimumHeight(60)
        right_layout.addWidget(self._cluster_notes_edit, stretch=0)

        # Save notes button
        self._cluster_save_notes_button = QPushButton("Spara anteckningar")
        self._cluster_save_notes_button.setObjectName("cluster_save_notes_button")
        self._cluster_save_notes_button.setEnabled(False)
        self._cluster_save_notes_button.clicked.connect(self._on_save_cluster_notes)
        right_layout.addWidget(self._cluster_save_notes_button)

        # Add panels to splitter
        self._cluster_splitter.addWidget(left_widget)
        self._cluster_splitter.addWidget(right_widget)

        # Set stretch factors for approximately 30%/70% split
        self._cluster_splitter.setStretchFactor(0, 30)
        self._cluster_splitter.setStretchFactor(1, 70)

        new_layout.addWidget(self._cluster_splitter)

        # Set initial empty state (Req 8.6)
        self._cluster_notes_edit.setEnabled(False)

        # Track the previously selected cluster for notes persistence
        self._previous_cluster_id: str | None = None

        # Track DNA match filter state (Req 9.3–9.6)
        self._cluster_filter_active: bool = False
        self._cluster_filter_person_id: str | None = None

    def _resolve_person_display_name(self, person_id: str) -> str:
        """Resolve a person_id to a display name string.

        Returns 'given surname' if found, or the raw person_id string
        if the person is not in the project data (Req 4.1, 4.2).
        """
        for person in self._project_data.persons:
            if person.id == person_id:
                if person.names:
                    name = person.names[0]
                    given = name.given.replace("*", "")
                    return f"{given} {name.surname}".strip()
                return f"(Person {person.id})"
        # Person not found — display raw id (Req 4.2)
        return person_id

    def _populate_combos(self) -> None:
        """Fill all combo boxes with their fixed option values."""
        # Test type combo
        self._ui.profile_test_type_combo.clear()
        for tt in TEST_TYPES:
            self._ui.profile_test_type_combo.addItem(tt, tt)

        # Admin status combo
        self._ui.profile_admin_status_combo.clear()
        self._ui.profile_admin_status_combo.addItem("", "")
        for status in ADMIN_STATUSES:
            self._ui.profile_admin_status_combo.addItem(status, status)

        # Match source combo
        self._ui.match_source_combo.clear()
        for src in MATCH_SOURCES:
            self._ui.match_source_combo.addItem(src, src)

        # Chromosome combos
        for combo in (
            self._ui.segment_chromosome_combo,
            self._ui.triangulation_chromosome_combo,
        ):
            combo.clear()
            for ch in CHROMOSOMES:
                combo.addItem(ch, ch)

        # Populate dynamic combos (companies, profiles, matches, clusters)
        self._refresh_company_combos()
        self._refresh_profile_combos()
        self._refresh_match_combos()
        self._refresh_cluster_combos()

    def _refresh_company_combos(self) -> None:
        """Refresh all combo boxes that list companies."""
        for combo in (
            self._ui.profile_company_combo,
            self._ui.triangulation_company_combo,
        ):
            combo.clear()
            for company in self._project_data.dna_companies:
                combo.addItem(company.name or company.id, company.id)

    def _refresh_profile_combos(self) -> None:
        """Refresh all combo boxes that list profiles."""
        for combo in (
            self._ui.match_profile1_combo,
            self._ui.match_profile2_combo,
        ):
            combo.clear()
            for profile in self._project_data.dna_profiles:
                display = profile.kit_name or profile.id
                combo.addItem(f"{display} ({profile.test_type})", profile.id)

    def _refresh_match_combos(self) -> None:
        """Refresh all combo boxes that list matches."""
        for combo in (
            self._ui.segment_match_combo,
            self._ui.cluster_match_combo,
        ):
            combo.clear()
            for match in self._project_data.dna_matches:
                display = f"{match.id[:8]}... ({match.shared_cm} cM)"
                combo.addItem(display, match.id)

    def _refresh_cluster_combos(self) -> None:
        """Refresh combo boxes that list clusters."""
        self._ui.triangulation_cluster_combo.clear()
        self._ui.triangulation_cluster_combo.addItem("(inget)", "")
        for cluster in self._project_data.dna_clusters:
            self._ui.triangulation_cluster_combo.addItem(
                cluster.name or cluster.id, cluster.id
            )

    def _connect_signals(self) -> None:
        """Wire up UI signals to handler slots."""
        # Companies tab
        self._ui.companies_list.currentItemChanged.connect(
            self._on_company_selected
        )
        self._ui.add_company_button.clicked.connect(self._on_add_company)
        self._ui.remove_company_button.clicked.connect(self._on_remove_company)
        self._ui.save_company_button.clicked.connect(self._on_save_company)

        # Profiles tab
        self._ui.profiles_list.currentItemChanged.connect(
            self._on_profile_selected
        )
        self._ui.add_profile_button.clicked.connect(self._on_add_profile)
        self._ui.remove_profile_button.clicked.connect(self._on_remove_profile)
        self._ui.save_profile_button.clicked.connect(self._on_save_profile)

        # Matches tab
        self._ui.matches_list.currentItemChanged.connect(
            self._on_match_selected
        )
        self._ui.add_match_button.clicked.connect(self._on_add_match)
        self._ui.remove_match_button.clicked.connect(self._on_remove_match)
        self._ui.save_match_button.clicked.connect(self._on_save_match)
        self._ui.match_filter_input.textChanged.connect(
            self._on_match_filter_changed
        )
        self._chromosome_view_button.clicked.connect(
            self._on_chromosome_view
        )

        # Segments tab (removed from UI; signals disabled)
        # self._ui.segments_list.currentItemChanged.connect(
        #     self._on_segment_selected
        # )
        # self._ui.add_segment_button.clicked.connect(self._on_add_segment)
        # self._ui.remove_segment_button.clicked.connect(self._on_remove_segment)
        # self._ui.save_segment_button.clicked.connect(self._on_save_segment)

        # Clusters tab — use the new split-panel cluster list widget
        self._cluster_list_widget.currentItemChanged.connect(
            self._on_cluster_selected
        )

        # Triangulations tab
        self._ui.triangulations_list.currentItemChanged.connect(
            self._on_triangulation_selected
        )
        self._ui.add_triangulation_button.clicked.connect(
            self._on_add_triangulation
        )
        self._ui.remove_triangulation_button.clicked.connect(
            self._on_remove_triangulation
        )
        # Old form buttons are hidden — signals disconnected
        # self._ui.save_triangulation_button.clicked.connect(
        #     self._on_save_triangulation
        # )
        # self._ui.add_triangulation_segment_button.clicked.connect(
        #     self._on_add_triangulation_segment
        # )
        # self._ui.remove_triangulation_segment_button.clicked.connect(
        #     self._on_remove_triangulation_segment
        # )
        # self._ui.add_triangulation_profile_button.clicked.connect(
        #     self._on_add_triangulation_profile
        # )
        # self._ui.remove_triangulation_profile_button.clicked.connect(
        #     self._on_remove_triangulation_profile
        # )

    # ------------------------------------------------------------------
    # Private: refresh lists
    # ------------------------------------------------------------------

    def _refresh_all_lists(self) -> None:
        """Refresh all entity lists across all tabs."""
        self._refresh_companies_list()
        self._refresh_profiles_list()
        self._refresh_matches_list()
        self._refresh_clusters_list()
        self._refresh_triangulations_list()

    def _refresh_companies_list(self) -> None:
        """Rebuild the companies list widget."""
        self._ui.companies_list.clear()
        for company in self._project_data.dna_companies:
            item = QListWidgetItem(company.name or company.id)
            item.setData(Qt.ItemDataRole.UserRole, company.id)
            self._ui.companies_list.addItem(item)

    def _refresh_profiles_list(self) -> None:
        """Rebuild the profiles list widget."""
        self._ui.profiles_list.clear()
        self._ui.profiles_list.setIconSize(QSize(LOGO_ICON_SIZE, LOGO_ICON_SIZE))
        for profile in self._project_data.dna_profiles:
            display = profile.kit_name or profile.id
            display = f"{display} ({profile.test_type})"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, profile.id)
            icon = resolve_profile_logo_icon(
                profile, self._project_data, self._project_folder, LOGO_ICON_SIZE
            )
            item.setIcon(icon)
            self._ui.profiles_list.addItem(item)

    def _refresh_matches_list(self) -> None:
        """Rebuild the matches list widget."""
        self._ui.matches_list.clear()
        self._ui.matches_list.setIconSize(QSize(LOGO_ICON_SIZE, LOGO_ICON_SIZE))
        filter_text = self._ui.match_filter_input.text()
        filtered_matches = matches_filter(
            self._project_data.dna_matches, filter_text, self._project_data
        )
        for match in filtered_matches:
            display = format_match_entry(match, self._project_data)
            # Req 14.5: Check for missing segment file and add visual warning
            if match.segment_file and self._project_path:
                segment_path = self._project_path.parent / "dna" / match.segment_file
                if not segment_path.exists():
                    logger.warning(
                        "Segmentfil saknas för matchning %s: %s",
                        match.id,
                        segment_path,
                    )
                    display = f"⚠ {display} (saknar segmentfil)"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, match.id)
            icon = resolve_company_logo_icon(
                match, self._project_data, self._project_folder, LOGO_ICON_SIZE
            )
            item.setIcon(icon)
            self._ui.matches_list.addItem(item)

    def _refresh_segments_list(self) -> None:
        """Rebuild the segments list widget."""
        self._ui.segments_list.clear()
        for segment in self._project_data.dna_segments:
            display = f"Chr {segment.chromosome}: {segment.cm} cM"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, segment.id)
            self._ui.segments_list.addItem(item)

    def _refresh_clusters_list(self) -> None:
        """Rebuild the clusters list widget in the split panel."""
        self._cluster_list_widget.clear()
        for cluster in self._project_data.dna_clusters:
            display = cluster.name or cluster.id
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, cluster.id)
            self._cluster_list_widget.addItem(item)

    def _refresh_triangulations_list(self) -> None:
        """Rebuild the triangulations list widget.

        Uses format_triangulation_entry() for display text with ellipsis
        truncation and full-text tooltip for long entries.
        """
        self._ui.triangulations_list.clear()
        for tri in self._project_data.dna_triangulations:
            display = format_triangulation_entry(tri, self._project_data)
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, tri.id)
            item.setToolTip(display)
            self._ui.triangulations_list.addItem(item)
        # Enable ellipsis truncation on the list widget
        self._ui.triangulations_list.setTextElideMode(
            Qt.TextElideMode.ElideRight
        )

    # ------------------------------------------------------------------
    # Companies: selection, add, remove, save
    # ------------------------------------------------------------------

    def _on_choose_logo(self) -> None:
        """Handle the 'Välj logo...' button click.

        Orchestrates the full logo chooser workflow:
        1. Ensure logo folder exists
        2. Open file dialog for image selection
        3. Copy file to logo folder if external
        4. Create or reuse MediaItem
        5. Associate with current company
        6. Update UI
        """
        if self._editing_company is None or self._project_folder is None:
            return

        # Step 1: Ensure logo folder exists (Req 1.6)
        logo_folder = self._logo_folder
        if logo_folder is None:
            return
        try:
            logo_folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            return

        # Step 2: Open file dialog (Req 1.3, 1.4, 1.5)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Välj logo...",
            str(logo_folder),
            LOGO_FILE_FILTER,
        )

        # Step 3: If user cancels, return without changes (Req 4.5)
        if not file_path:
            return

        selected_path = Path(file_path)

        # Step 4: Determine if file is inside logo folder (Req 2.1)
        if _is_inside_logo_folder(selected_path, logo_folder):
            dest_path = selected_path
        else:
            # Step 5: Copy to logo folder (Req 3.1, 3.7)
            dest_path = _copy_to_logo_folder(selected_path, logo_folder)
            if dest_path is None:
                QMessageBox.warning(
                    self,
                    "Fel",
                    f"Kunde inte kopiera filen: {selected_path.name}",
                )
                return

        # Step 6: Compute relative path (Req 2.1)
        rel_path = _compute_relative_path(dest_path, self._project_folder)

        # Step 7: Search for existing MediaItem (Req 2.3, 3.6, 4.2)
        media_item = _find_media_by_path(self._project_data.media, rel_path)

        # Step 8: Create new MediaItem if needed (Req 2.2, 3.5, 4.1)
        if media_item is None:
            media_item = _create_logo_media_item(rel_path, dest_path.name)
            self._project_data.media.append(media_item)

        # Step 9: Set company logo_media_id (Req 2.4, 4.1, 4.4)
        self._editing_company.logo_media_id = media_item.id

        # Step 10: Update text field (Req 4.3)
        self._ui.company_logo_input.setText(media_item.id)

        # Step 11: Update logo preview (Req 5.2)
        self._update_logo_preview()

    def _update_logo_preview(self) -> None:
        """Update the logo preview label based on the current company's logo.

        Resolves the company's logo_media_id to a file path and displays
        the logo image scaled to 64×64, or shows an appropriate placeholder
        when no logo is assigned or the file is missing on disk.
        """
        # No company or no logo assigned → empty placeholder (Req 5.3)
        if (
            self._editing_company is None
            or not self._editing_company.logo_media_id
        ):
            self._logo_preview_label.clear()
            self._logo_preview_label.setStyleSheet("")
            return

        # Find the MediaItem by id
        media_item: MediaItem | None = None
        for item in self._project_data.media:
            if item.id == self._editing_company.logo_media_id:
                media_item = item
                break

        if media_item is None:
            self._logo_preview_label.clear()
            self._logo_preview_label.setStyleSheet("")
            return

        # Resolve absolute path
        if self._project_folder is None:
            self._logo_preview_label.clear()
            self._logo_preview_label.setStyleSheet("")
            return

        abs_path = self._project_folder / media_item.file

        # Normalize to NFC for consistent Swedish character handling
        import unicodedata
        normalized_file = unicodedata.normalize("NFC", media_item.file)
        abs_path = self._project_folder / normalized_file

        # Check if file exists on disk (Req 5.4)
        if not abs_path.exists():
            self._logo_preview_label.setText("?")
            self._logo_preview_label.setStyleSheet(
                "border: 2px solid red; color: red; font-size: 24px; "
                "qproperty-alignment: AlignCenter;"
            )
            return

        # Load and scale the image (Req 5.1, 5.2)
        pixmap = QPixmap(str(abs_path))
        if pixmap.isNull():
            self._logo_preview_label.setText("?")
            self._logo_preview_label.setStyleSheet(
                "border: 2px solid red; color: red; font-size: 24px; "
                "qproperty-alignment: AlignCenter;"
            )
            return

        scaled = pixmap.scaled(
            LOGO_PREVIEW_SIZE,
            LOGO_PREVIEW_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._logo_preview_label.setPixmap(scaled)
        self._logo_preview_label.setStyleSheet("")  # Clear any previous error style

    def _on_company_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        """Handle company list selection change.

        Args:
            current: The newly selected item, or None.
            _previous: The previously selected item (unused).
        """
        if current is None:
            self._logo_choose_button.setEnabled(False)
            self._update_logo_preview()
            return
        company_id = current.data(Qt.ItemDataRole.UserRole)
        for company in self._project_data.dna_companies:
            if company.id == company_id:
                self._editing_company = company
                self._load_company(company)
                self._update_logo_preview()
                self._logo_choose_button.setEnabled(
                    self._project_path is not None
                )
                break

    def _load_company(self, company: DnaCompany) -> None:
        """Populate company form fields from a DnaCompany instance.

        Args:
            company: The company to load into the form.
        """
        self._ui.company_name_input.setText(company.name)
        self._ui.company_notes_input.setPlainText(company.description)
        self._ui.company_logo_input.setText(company.logo_media_id or "")
        self._company_url_input.setText(company.url)

    def _on_add_company(self) -> None:
        """Clear form for new company entry."""
        self._editing_company = None
        self._ui.company_name_input.clear()
        self._ui.company_notes_input.clear()
        self._ui.company_logo_input.clear()
        self._company_url_input.clear()
        self._update_logo_preview()
        self._logo_choose_button.setEnabled(False)
        self._clear_status()

    def _on_remove_company(self) -> None:
        """Remove the selected company from project data."""
        current = self._ui.companies_list.currentItem()
        if not current:
            self._update_status("Välj ett företag att ta bort.")
            return
        company_id = current.data(Qt.ItemDataRole.UserRole)
        self._project_data.dna_companies = [
            c for c in self._project_data.dna_companies if c.id != company_id
        ]
        self._editing_company = None
        self._refresh_companies_list()
        self._refresh_company_combos()
        self._clear_status()

    def _on_save_company(self) -> None:
        """Validate and save the company form data."""
        name = self._ui.company_name_input.text().strip()
        if not name:
            self._update_status("Företagsnamn krävs.")
            return
        if len(name) > 200:
            self._update_status("Företagsnamn får vara max 200 tecken.")
            return

        logo_id = self._ui.company_logo_input.text().strip() or None
        if logo_id:
            if not any(m.id == logo_id for m in self._project_data.media):
                self._update_status(
                    f"Media-ID '{logo_id}' finns inte i projektet."
                )
                return

        description = self._ui.company_notes_input.toPlainText()
        url = self._company_url_input.text().strip()

        if self._editing_company:
            self._editing_company.name = name
            self._editing_company.description = description
            self._editing_company.logo_media_id = logo_id
            self._editing_company.url = url
        else:
            new_company = DnaCompany(
                id=str(uuid.uuid4()),
                name=name,
                logo_media_id=logo_id,
                description=description,
                url=url,
            )
            self._project_data.dna_companies.append(new_company)
            self._editing_company = new_company

        self._refresh_companies_list()
        self._refresh_company_combos()
        self._clear_status()
        logger.info("DNA-företag sparat: %s", name)

    # ------------------------------------------------------------------
    # Profiles: selection, add, remove, save
    # ------------------------------------------------------------------

    def _on_profile_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        """Handle profile list selection change.

        Args:
            current: The newly selected item, or None.
            _previous: The previously selected item (unused).
        """
        if current is None:
            return
        profile_id = current.data(Qt.ItemDataRole.UserRole)
        for profile in self._project_data.dna_profiles:
            if profile.id == profile_id:
                self._editing_profile = profile
                self._load_profile(profile)
                break

    def _load_profile(self, profile: DnaProfile) -> None:
        """Populate profile form fields from a DnaProfile instance.

        Args:
            profile: The profile to load into the form.
        """
        # Show person name as read-only label (Req 4.1, 4.2)
        self._ui.profile_person_input.setText(profile.person_id)
        self._profile_person_name_label.setText(
            self._resolve_person_display_name(profile.person_id)
        )
        idx = self._ui.profile_company_combo.findData(profile.company_id)
        if idx >= 0:
            self._ui.profile_company_combo.setCurrentIndex(idx)
        idx = self._ui.profile_test_type_combo.findData(profile.test_type)
        if idx >= 0:
            self._ui.profile_test_type_combo.setCurrentIndex(idx)
        # Load haplogroup values (Req 1.2–1.5, 1.7)
        self._y_haplogroup_input.setText(profile.y_haplogroup)
        self._mt_haplogroup_input.setText(profile.mt_haplogroup)
        self._update_haplogroup_visibility()

        self._ui.profile_kit_name_input.setText(profile.kit_name)
        self._ui.profile_kit_id_input.setText(profile.kit_id)
        # Populate admin person search widget (Req 4.3)
        self._admin_person_search.set_selected_person(
            profile.admin_person_id, self._project_data.persons
        )
        self._ui.profile_notes_input.setPlainText(profile.notes)

    def _on_add_profile(self) -> None:
        """Clear form for new profile entry."""
        self._editing_profile = None
        self._ui.profile_person_input.clear()
        self._profile_person_name_label.clear()
        self._ui.profile_company_combo.setCurrentIndex(0)
        self._ui.profile_test_type_combo.setCurrentIndex(0)
        self._y_haplogroup_input.clear()
        self._mt_haplogroup_input.clear()
        self._update_haplogroup_visibility()
        self._ui.profile_kit_name_input.clear()
        self._ui.profile_kit_id_input.clear()
        self._admin_person_search.clear_selection()
        self._ui.profile_notes_input.clear()
        self._clear_status()

    def _on_remove_profile(self) -> None:
        """Remove the selected profile from project data."""
        current = self._ui.profiles_list.currentItem()
        if not current:
            self._update_status("Välj en profil att ta bort.")
            return
        profile_id = current.data(Qt.ItemDataRole.UserRole)
        self._project_data.dna_profiles = [
            p for p in self._project_data.dna_profiles if p.id != profile_id
        ]
        self._editing_profile = None
        self._refresh_profiles_list()
        self._refresh_profile_combos()
        self._clear_status()

    def _on_save_profile(self) -> None:
        """Validate and save the profile form data."""
        person_id = self._ui.profile_person_input.text().strip()
        if not person_id:
            self._update_status("Person-ID krävs.")
            return
        if not any(p.id == person_id for p in self._project_data.persons):
            self._update_status(
                f"Person-ID '{person_id}' finns inte i projektet."
            )
            return

        company_id = self._ui.profile_company_combo.currentData()
        if not company_id:
            self._update_status("Välj ett företag.")
            return
        if not any(c.id == company_id for c in self._project_data.dna_companies):
            self._update_status(
                f"Företags-ID '{company_id}' finns inte i projektet."
            )
            return

        test_type = self._ui.profile_test_type_combo.currentData() or ""
        kit_name = self._ui.profile_kit_name_input.text().strip()
        kit_id = self._ui.profile_kit_id_input.text().strip()
        # Read haplogroup values from the input fields (Req 1.7 — always save
        # even if the field is currently hidden)
        y_haplogroup = self._y_haplogroup_input.text().strip()
        mt_haplogroup = self._mt_haplogroup_input.text().strip()
        # Use PersonSearchWidget for admin_person_id (Req 4.3, 4.4)
        admin_person_id = self._admin_person_search.selected_person_id()
        if admin_person_id:
            if not any(
                p.id == admin_person_id for p in self._project_data.persons
            ):
                self._update_status(
                    f"Admin person-ID '{admin_person_id}' finns inte."
                )
                return

        notes = self._ui.profile_notes_input.toPlainText()

        if self._editing_profile:
            self._editing_profile.person_id = person_id
            self._editing_profile.company_id = company_id
            self._editing_profile.test_type = test_type
            self._editing_profile.kit_name = kit_name
            self._editing_profile.kit_id = kit_id
            self._editing_profile.y_haplogroup = y_haplogroup
            self._editing_profile.mt_haplogroup = mt_haplogroup
            self._editing_profile.admin_person_id = admin_person_id
            self._editing_profile.notes = notes
        else:
            new_profile = DnaProfile(
                id=str(uuid.uuid4()),
                person_id=person_id,
                company_id=company_id,
                test_type=test_type,
                kit_name=kit_name,
                kit_id=kit_id,
                y_haplogroup=y_haplogroup,
                mt_haplogroup=mt_haplogroup,
                admin_person_id=admin_person_id,
                notes=notes,
            )
            self._project_data.dna_profiles.append(new_profile)
            self._editing_profile = new_profile

        self._refresh_profiles_list()
        self._refresh_profile_combos()
        self._clear_status()
        logger.info("DNA-profil sparad: %s", kit_name or person_id)

    # ------------------------------------------------------------------
    # Matches: selection, add, remove, save
    # ------------------------------------------------------------------

    def _on_match_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        """Handle match list selection change.

        Args:
            current: The newly selected item, or None.
            _previous: The previously selected item (unused).
        """
        if current is None:
            return
        match_id = current.data(Qt.ItemDataRole.UserRole)
        for match in self._project_data.dna_matches:
            if match.id == match_id:
                self._editing_match = match
                self._load_match(match)
                break

    def _load_match(self, match: DnaMatch) -> None:
        """Populate match form fields from a DnaMatch instance.

        Args:
            match: The match to load into the form.
        """
        idx = self._ui.match_profile1_combo.findData(match.profile1_id)
        if idx >= 0:
            self._ui.match_profile1_combo.setCurrentIndex(idx)
        idx = self._ui.match_profile2_combo.findData(match.profile2_id)
        if idx >= 0:
            self._ui.match_profile2_combo.setCurrentIndex(idx)
        self._ui.match_shared_cm_input.setValue(match.shared_cm)
        self._ui.match_percentage_input.setValue(match.shared_percentage)
        self._ui.match_segment_count_input.setValue(match.segment_count)
        self._ui.match_largest_segment_input.setValue(match.largest_segment_cm)
        idx = self._ui.match_source_combo.findData(match.match_source)
        if idx >= 0:
            self._ui.match_source_combo.setCurrentIndex(idx)
        self._ui.match_notes_input.setPlainText(match.notes)

        # Enable Kromosomvy button only when segment data is available (Req 15.1, 15.2)
        self._chromosome_view_button.setEnabled(match.segment_file is not None)

    def _on_add_match(self) -> None:
        """Clear form for new match entry."""
        self._editing_match = None
        self._ui.match_profile1_combo.setCurrentIndex(0)
        self._ui.match_profile2_combo.setCurrentIndex(0)
        self._ui.match_shared_cm_input.setValue(0.0)
        self._ui.match_percentage_input.setValue(0.0)
        self._ui.match_segment_count_input.setValue(0)
        self._ui.match_largest_segment_input.setValue(0.0)
        self._ui.match_source_combo.setCurrentIndex(0)
        self._ui.match_notes_input.clear()
        self._chromosome_view_button.setEnabled(False)
        self._clear_status()

    def _on_remove_match(self) -> None:
        """Remove the selected match from project data."""
        current = self._ui.matches_list.currentItem()
        if not current:
            self._update_status("Välj en matchning att ta bort.")
            return
        match_id = current.data(Qt.ItemDataRole.UserRole)

        # Delete associated segment file if present
        match_to_remove = next(
            (m for m in self._project_data.dna_matches if m.id == match_id), None
        )
        if match_to_remove and match_to_remove.segment_file and self._project_path:
            delete_dna_file(self._project_path, match_to_remove.segment_file)

        self._project_data.dna_matches = [
            m for m in self._project_data.dna_matches if m.id != match_id
        ]
        self._editing_match = None
        self._refresh_matches_list()
        self._refresh_match_combos()
        self._clear_status()

    def _on_save_match(self) -> None:
        """Validate and save the match form data."""
        profile1_id = self._ui.match_profile1_combo.currentData()
        profile2_id = self._ui.match_profile2_combo.currentData()
        if not profile1_id or not profile2_id:
            self._update_status("Välj två profiler för matchningen.")
            return
        if profile1_id == profile2_id:
            self._update_status("Profil 1 och Profil 2 måste vara olika.")
            return

        # Validate profile references
        if not any(p.id == profile1_id for p in self._project_data.dna_profiles):
            self._update_status(f"Profil-ID '{profile1_id}' finns inte.")
            return
        if not any(p.id == profile2_id for p in self._project_data.dna_profiles):
            self._update_status(f"Profil-ID '{profile2_id}' finns inte.")
            return

        shared_cm = self._ui.match_shared_cm_input.value()
        shared_percentage = self._ui.match_percentage_input.value()
        segment_count = self._ui.match_segment_count_input.value()
        largest_segment_cm = self._ui.match_largest_segment_input.value()
        match_source = self._ui.match_source_combo.currentData() or "internal"
        notes = self._ui.match_notes_input.toPlainText()

        if self._editing_match:
            self._editing_match.profile1_id = profile1_id
            self._editing_match.profile2_id = profile2_id
            self._editing_match.shared_cm = shared_cm
            self._editing_match.shared_percentage = shared_percentage
            self._editing_match.segment_count = segment_count
            self._editing_match.largest_segment_cm = largest_segment_cm
            self._editing_match.match_source = match_source
            self._editing_match.notes = notes
        else:
            new_match = DnaMatch(
                id=str(uuid.uuid4()),
                profile1_id=profile1_id,
                profile2_id=profile2_id,
                shared_cm=shared_cm,
                shared_percentage=shared_percentage,
                segment_count=segment_count,
                largest_segment_cm=largest_segment_cm,
                match_source=match_source,
                notes=notes,
            )
            self._project_data.dna_matches.append(new_match)
            self._editing_match = new_match

        self._refresh_matches_list()
        self._refresh_match_combos()
        self._clear_status()
        logger.info("DNA-matchning sparad: %s cM", shared_cm)

    def _on_match_filter_changed(self, text: str) -> None:
        """Re-filter matches list when filter text changes."""
        self._refresh_matches_list()

    def _on_chromosome_view(self) -> None:
        """Open the chromosome browser dialog for the selected match.

        Loads segment data from disk and resolves the person name for Profile 2.
        Shows an error message if segments cannot be loaded.
        Req 15.1, 15.2.
        """
        match = self._editing_match
        if not match or not match.segment_file:
            return

        if not self._project_path:
            self._update_status("Kan inte läsa segmentfil – inget projektfilsökväg.")
            return

        # Load segments from the dna/ subfolder
        try:
            segments = load_match_segments(self._project_path, match.segment_file)
        except (FileNotFoundError, Exception) as exc:
            self._update_status(f"Kunde inte läsa segmentfil: {exc}")
            return

        # Resolve person names for both profiles
        person1_name = "(okänd)"
        person2_name = "(okänd)"
        for profile in self._project_data.dna_profiles:
            if profile.id == match.profile1_id:
                person1_name = self._resolve_person_display_name(profile.person_id)
            if profile.id == match.profile2_id:
                person2_name = self._resolve_person_display_name(profile.person_id)

        match_title = f"{person1_name} och {person2_name}"

        dialog = ChromosomeBrowserDialog(
            segments=segments, person_name=person2_name, title=match_title, parent=self
        )
        dialog.exec()

    # ------------------------------------------------------------------
    # Segments: selection, add, remove, save
    # ------------------------------------------------------------------

    def _on_segment_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        """Handle segment list selection change.

        Args:
            current: The newly selected item, or None.
            _previous: The previously selected item (unused).
        """
        if current is None:
            return
        segment_id = current.data(Qt.ItemDataRole.UserRole)
        for segment in self._project_data.dna_segments:
            if segment.id == segment_id:
                self._editing_segment = segment
                self._load_segment(segment)
                break

    def _load_segment(self, segment: DnaSegment) -> None:
        """Populate segment form fields from a DnaSegment instance.

        Args:
            segment: The segment to load into the form.
        """
        idx = self._ui.segment_match_combo.findData(segment.match_id)
        if idx >= 0:
            self._ui.segment_match_combo.setCurrentIndex(idx)
        idx = self._ui.segment_chromosome_combo.findData(segment.chromosome)
        if idx >= 0:
            self._ui.segment_chromosome_combo.setCurrentIndex(idx)
        self._ui.segment_start_input.setValue(segment.start_position)
        self._ui.segment_end_input.setValue(segment.end_position)
        self._ui.segment_cm_input.setValue(segment.cm)
        self._ui.segment_snp_input.setValue(segment.snp_count)

    def _on_add_segment(self) -> None:
        """Clear form for new segment entry."""
        self._editing_segment = None
        self._ui.segment_match_combo.setCurrentIndex(0)
        self._ui.segment_chromosome_combo.setCurrentIndex(0)
        self._ui.segment_start_input.setValue(0)
        self._ui.segment_end_input.setValue(0)
        self._ui.segment_cm_input.setValue(0.0)
        self._ui.segment_snp_input.setValue(0)
        self._clear_status()

    def _on_remove_segment(self) -> None:
        """Remove the selected segment from project data."""
        current = self._ui.segments_list.currentItem()
        if not current:
            self._update_status("Välj ett segment att ta bort.")
            return
        segment_id = current.data(Qt.ItemDataRole.UserRole)
        self._project_data.dna_segments = [
            s for s in self._project_data.dna_segments if s.id != segment_id
        ]
        self._editing_segment = None
        self._refresh_segments_list()
        self._clear_status()

    def _on_save_segment(self) -> None:
        """Validate and save the segment form data."""
        match_id = self._ui.segment_match_combo.currentData()
        if not match_id:
            self._update_status("Välj en matchning för segmentet.")
            return
        if not any(m.id == match_id for m in self._project_data.dna_matches):
            self._update_status(f"Matchnings-ID '{match_id}' finns inte.")
            return

        chromosome = self._ui.segment_chromosome_combo.currentData() or ""
        start_pos = self._ui.segment_start_input.value()
        end_pos = self._ui.segment_end_input.value()
        cm = self._ui.segment_cm_input.value()
        snp_count = self._ui.segment_snp_input.value()

        if start_pos >= end_pos:
            self._update_status("Startposition måste vara mindre än slutposition.")
            return
        if cm <= 0:
            self._update_status("cM måste vara större än 0.")
            return

        if self._editing_segment:
            self._editing_segment.match_id = match_id
            self._editing_segment.chromosome = chromosome
            self._editing_segment.start_position = start_pos
            self._editing_segment.end_position = end_pos
            self._editing_segment.cm = cm
            self._editing_segment.snp_count = snp_count
        else:
            new_segment = DnaSegment(
                id=str(uuid.uuid4()),
                match_id=match_id,
                chromosome=chromosome,
                start_position=start_pos,
                end_position=end_pos,
                cm=cm,
                snp_count=snp_count,
            )
            self._project_data.dna_segments.append(new_segment)
            self._editing_segment = new_segment

        self._refresh_segments_list()
        self._clear_status()
        logger.info("DNA-segment sparat: Chr %s, %s cM", chromosome, cm)

    # ------------------------------------------------------------------
    # Clusters: selection, add, remove, save, member/match management
    # ------------------------------------------------------------------

    def _on_cluster_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        """Handle cluster list selection change in the split panel.

        Persists notes from previously selected cluster before loading
        the new one (Req 8.7). Updates persons list and notes (Req 8.4).
        Shows empty state when no cluster selected (Req 8.6).
        Exits filter mode on cluster change (Req 9.6).

        Args:
            current: The newly selected item, or None.
            _previous: The previously selected item (unused).
        """
        # Persist notes for the previously selected cluster (Req 8.7)
        self._persist_cluster_notes()

        # Exit filter mode on cluster change (Req 9.6)
        if self._cluster_filter_active:
            self._exit_cluster_filter()

        if current is None:
            # Empty state (Req 8.6)
            self._editing_cluster = None
            self._previous_cluster_id = None
            self._cluster_persons_list.clear()
            self._cluster_notes_edit.clear()
            self._cluster_notes_edit.setEnabled(False)
            self._cluster_save_notes_button.setEnabled(False)
            return

        cluster_id = current.data(Qt.ItemDataRole.UserRole)
        for cluster in self._project_data.dna_clusters:
            if cluster.id == cluster_id:
                self._editing_cluster = cluster
                self._previous_cluster_id = cluster.id
                self._load_cluster_panel(cluster)
                break

    def _persist_cluster_notes(self) -> None:
        """Save current notes text to the previously selected cluster.

        Req 8.5, 8.7: Auto-persist notes on cluster switch.
        """
        if self._previous_cluster_id is None:
            return
        notes_text = self._cluster_notes_edit.toPlainText()
        for cluster in self._project_data.dna_clusters:
            if cluster.id == self._previous_cluster_id:
                cluster.notes = notes_text
                break

    def _on_save_cluster_notes(self) -> None:
        """Explicitly save the current cluster's notes via the save button."""
        if self._editing_cluster is None:
            return
        notes_text = self._cluster_notes_edit.toPlainText()
        self._editing_cluster.notes = notes_text
        self._update_status("Anteckningar sparade.")

    def _load_cluster_panel(self, cluster: DnaCluster) -> None:
        """Populate the split panel right side from a DnaCluster.

        Shows person names in the persons list and loads notes (Req 8.2, 8.4).

        Args:
            cluster: The cluster to display.
        """
        # Enable notes area and save button
        self._cluster_notes_edit.setEnabled(True)
        self._cluster_save_notes_button.setEnabled(True)

        # Populate persons list with resolved names
        self._cluster_persons_list.clear()
        for person_id in cluster.person_ids:
            display_name = self._resolve_person_display_name(person_id)
            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, person_id)
            self._cluster_persons_list.addItem(item)

        # Load notes
        self._cluster_notes_edit.setPlainText(cluster.notes)

    def _on_cluster_person_context_menu(self, position) -> None:
        """Show context menu on right-click in the cluster persons list.

        Req 9.1: Show "Filtrera på DNA-träffar" option.
        Req 9.2: Disable if person has no DnaProfile.

        Args:
            position: The position where the context menu was requested.
        """
        item = self._cluster_persons_list.itemAt(position)
        if item is None:
            return

        person_id = item.data(Qt.ItemDataRole.UserRole)
        if not person_id:
            return

        menu = QMenu(self._cluster_persons_list)
        filter_action = QAction("Filtrera på DNA-träffar", menu)

        # Check if person has at least one DnaProfile (Req 9.2)
        has_profile = any(
            p.person_id == person_id for p in self._project_data.dna_profiles
        )
        filter_action.setEnabled(has_profile)

        filter_action.triggered.connect(
            lambda: self._apply_cluster_dna_filter(person_id)
        )
        menu.addAction(filter_action)
        menu.exec(self._cluster_persons_list.mapToGlobal(position))

    def _apply_cluster_dna_filter(self, person_id: str) -> None:
        """Apply DNA match filter for the given person.

        Req 9.3: Filter person list to only those with a DnaMatch linking
        to the right-clicked person's profiles.
        Req 9.4: Show empty list if no matches found.

        Args:
            person_id: The person to filter DNA matches for.
        """
        if self._editing_cluster is None:
            return

        self._cluster_filter_active = True
        self._cluster_filter_person_id = person_id

        # Set the toggle to checked (Req 9.3)
        self._cluster_filter_toggle.setChecked(True)

        # Apply filter using pure logic function
        filtered_person_ids = get_dna_match_filtered_persons(
            person_id=person_id,
            cluster_person_ids=self._editing_cluster.person_ids,
            profiles=self._project_data.dna_profiles,
            matches=self._project_data.dna_matches,
        )

        # Update the persons list with filtered results
        self._cluster_persons_list.clear()
        for pid in filtered_person_ids:
            display_name = self._resolve_person_display_name(pid)
            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, pid)
            self._cluster_persons_list.addItem(item)

    def _on_cluster_filter_toggle(self) -> None:
        """Handle the 'Visa filtrerade' toggle button state change.

        Req 9.5: When unchecked, exit filter mode and show all persons.
        """
        if not self._cluster_filter_toggle.isChecked():
            # Exit filter mode (Req 9.5)
            self._cluster_filter_active = False
            self._cluster_filter_person_id = None
            # Restore full persons list for the current cluster
            if self._editing_cluster is not None:
                self._load_cluster_panel(self._editing_cluster)

    def _exit_cluster_filter(self) -> None:
        """Exit filter mode, uncheck toggle, and reset state.

        Req 9.6: Called on cluster change while filtered.
        """
        self._cluster_filter_active = False
        self._cluster_filter_person_id = None
        self._cluster_filter_toggle.setChecked(False)

    def _load_cluster(self, cluster: DnaCluster) -> None:
        """Legacy cluster form loader — delegates to the new panel.

        Args:
            cluster: The cluster to load into the panel.
        """
        self._load_cluster_panel(cluster)

    def _on_add_cluster(self) -> None:
        """Clear selection for new cluster entry (no longer used in split panel)."""
        self._editing_cluster = None
        self._previous_cluster_id = None
        self._cluster_list_widget.clearSelection()
        self._cluster_persons_list.clear()
        self._cluster_notes_edit.clear()
        self._cluster_notes_edit.setEnabled(False)
        self._clear_status()

    def _on_remove_cluster(self) -> None:
        """Remove the selected cluster from project data."""
        current = self._cluster_list_widget.currentItem()
        if not current:
            self._update_status("Välj ett kluster att ta bort.")
            return
        cluster_id = current.data(Qt.ItemDataRole.UserRole)
        self._project_data.dna_clusters = [
            c for c in self._project_data.dna_clusters if c.id != cluster_id
        ]
        self._editing_cluster = None
        self._previous_cluster_id = None
        self._cluster_persons_list.clear()
        self._cluster_notes_edit.clear()
        self._cluster_notes_edit.setEnabled(False)
        self._refresh_clusters_list()
        self._refresh_cluster_combos()
        self._clear_status()

    def _on_add_cluster_member(self) -> None:
        """Add a person ID to the cluster members list (legacy, not used in split panel)."""
        pass

    def _on_remove_cluster_member(self) -> None:
        """Remove the selected member from the cluster members list (legacy, not used in split panel)."""
        pass

    def _on_add_cluster_match(self) -> None:
        """Add a match to the cluster matches list (legacy, not used in split panel)."""
        pass

    def _on_remove_cluster_match(self) -> None:
        """Remove the selected match from the cluster matches list (legacy, not used in split panel)."""
        pass

    def _on_save_cluster(self) -> None:
        """Persist current cluster notes (auto-persist on split panel).

        In the new split-panel layout, notes are auto-persisted on cluster switch.
        This method can also be called explicitly to save the current notes.
        """
        self._persist_cluster_notes()

    # ------------------------------------------------------------------
    # Triangulations: selection, add, remove, save, segment/profile mgmt
    # ------------------------------------------------------------------

    def _on_triangulation_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        """Handle triangulation list selection change.

        Populates the read-only detail view and enables the Redigera button.

        Args:
            current: The newly selected item, or None.
            _previous: The previously selected item (unused).
        """
        if current is None:
            self._editing_triangulation = None
            self._clear_triangulation_detail()
            self._tri_edit_button.setEnabled(False)
            return
        tri_id = current.data(Qt.ItemDataRole.UserRole)
        for tri in self._project_data.dna_triangulations:
            if tri.id == tri_id:
                self._editing_triangulation = tri
                self._load_triangulation_detail(tri)
                self._tri_edit_button.setEnabled(True)
                break

    def _clear_triangulation_detail(self) -> None:
        """Clear the read-only triangulation detail view to default state."""
        self._tri_detail_company_label.setText("—")
        self._tri_detail_shared_cm_label.setText("—")
        self._tri_detail_segment_count_label.setText("—")
        self._tri_detail_largest_segment_label.setText("—")
        self._tri_detail_notes_label.setText("—")
        self._tri_detail_profiles_list.clear()

    def _load_triangulation_detail(self, tri: DnaTriangulation) -> None:
        """Populate the read-only triangulation detail view.

        Displays: Företag (company name), Delad cM (2 decimals),
        Antal segment, Största segment (2 decimals), Anteckningar,
        and a list of profile display names.

        Args:
            tri: The triangulation to display.
        """
        # Resolve company name
        company_name = "(okänt företag)"
        for c in self._project_data.dna_companies:
            if c.id == tri.company_id:
                company_name = c.name
                break
        self._tri_detail_company_label.setText(company_name)

        self._tri_detail_shared_cm_label.setText(f"{tri.shared_cm:.2f}")
        self._tri_detail_segment_count_label.setText(str(tri.segment_count))
        self._tri_detail_largest_segment_label.setText(
            f"{tri.largest_segment_cm:.2f}"
        )
        self._tri_detail_notes_label.setText(tri.notes or "—")

        # Populate profiles list with resolved person names
        self._tri_detail_profiles_list.clear()
        for profile_id in tri.profile_ids:
            display_name = self._resolve_profile_display_name(profile_id)
            self._tri_detail_profiles_list.addItem(display_name)

    def _resolve_profile_display_name(self, profile_id: str) -> str:
        """Resolve a profile_id to a human-readable display name.

        Resolution: profile_id → DnaProfile → person_id → Person → names[0]
        Falls back to "(okänd)" if resolution fails at any step.
        """
        profile = None
        for p in self._project_data.dna_profiles:
            if p.id == profile_id:
                profile = p
                break
        if profile is None:
            return "(okänd)"

        person = None
        for per in self._project_data.persons:
            if per.id == profile.person_id:
                person = per
                break
        if person is None:
            return "(okänd)"

        if not person.names:
            return "(okänd)"

        name = person.names[0]
        return f"{name.given} {name.surname}"

    def _on_edit_triangulation(self) -> None:
        """Open DnaTriangulationDialog in edit mode for the selected triangulation.

        Req 7.3: Pre-populated with current triangulation data.
        Req 7.4: Refresh detail view on dialog accept.
        Req 7.5: No change on cancel.
        """
        if self._editing_triangulation is None:
            return

        from slaktbusken.ui.dialogs.dna_triangulation_dialog import (
            DnaTriangulationDialog,
        )

        # Use an empty person_id since the DNA editor doesn't have a single
        # "active person" context — the dialog needs it for eligibility filtering
        # but in edit mode it's mainly informational.
        # We pick the first profile's person_id if available.
        person_id = ""
        if self._editing_triangulation.profile_ids:
            first_profile_id = self._editing_triangulation.profile_ids[0]
            for p in self._project_data.dna_profiles:
                if p.id == first_profile_id:
                    person_id = p.person_id
                    break

        dialog = DnaTriangulationDialog(
            project_data=self._project_data,
            person_id=person_id,
            existing_triangulation=self._editing_triangulation,
            parent=self,
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:
            edited = dialog.edited_triangulation
            if edited is not None:
                # Update triangulation in project data
                for i, t in enumerate(self._project_data.dna_triangulations):
                    if t.id == edited.id:
                        self._project_data.dna_triangulations[i] = edited
                        break
                self._editing_triangulation = edited
                # Refresh list and detail view
                self._refresh_triangulations_list()
                self._load_triangulation_detail(edited)
        # If cancelled, do nothing (Req 7.5)

    def _on_add_triangulation(self) -> None:
        """Open DnaTriangulationDialog in create mode to add a new triangulation."""
        from slaktbusken.ui.dialogs.dna_triangulation_dialog import (
            DnaTriangulationDialog,
        )

        # Use an empty person_id — the dialog will allow selecting profiles
        person_id = ""
        if self._project_data.persons:
            person_id = self._project_data.persons[0].id

        dialog = DnaTriangulationDialog(
            project_data=self._project_data,
            person_id=person_id,
            existing_triangulation=None,
            parent=self,
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:
            created = dialog.created_triangulation
            if created is not None:
                self._project_data.dna_triangulations.append(created)
                self._editing_triangulation = created
                self._refresh_triangulations_list()
                self._load_triangulation_detail(created)
                self._tri_edit_button.setEnabled(True)
        self._clear_status()

    def _on_remove_triangulation(self) -> None:
        """Remove the selected triangulation from project data."""
        current = self._ui.triangulations_list.currentItem()
        if not current:
            self._update_status("Välj en triangulering att ta bort.")
            return
        tri_id = current.data(Qt.ItemDataRole.UserRole)
        self._project_data.dna_triangulations = [
            t for t in self._project_data.dna_triangulations if t.id != tri_id
        ]
        self._editing_triangulation = None
        self._clear_triangulation_detail()
        self._tri_edit_button.setEnabled(False)
        self._refresh_triangulations_list()
        self._clear_status()

    def _on_add_triangulation_segment(self) -> None:
        """Add a segment ID to the triangulation segments list."""
        seg_id = self._ui.triangulation_segment_input.text().strip()
        if not seg_id:
            self._update_status("Ange ett segment-ID.")
            return
        if not any(s.id == seg_id for s in self._project_data.dna_segments):
            self._update_status(f"Segment-ID '{seg_id}' finns inte.")
            return
        item = QListWidgetItem(seg_id)
        item.setData(Qt.ItemDataRole.UserRole, seg_id)
        self._ui.triangulation_segments_list.addItem(item)
        self._ui.triangulation_segment_input.clear()
        self._clear_status()

    def _on_remove_triangulation_segment(self) -> None:
        """Remove the selected segment from the triangulation segments list."""
        current = self._ui.triangulation_segments_list.currentItem()
        if not current:
            self._update_status("Välj ett segment att ta bort.")
            return
        row = self._ui.triangulation_segments_list.row(current)
        self._ui.triangulation_segments_list.takeItem(row)
        self._clear_status()

    def _on_add_triangulation_profile(self) -> None:
        """Add a profile ID to the triangulation profiles list."""
        prof_id = self._ui.triangulation_profile_input.text().strip()
        if not prof_id:
            self._update_status("Ange ett profil-ID.")
            return
        if not any(p.id == prof_id for p in self._project_data.dna_profiles):
            self._update_status(f"Profil-ID '{prof_id}' finns inte.")
            return
        item = QListWidgetItem(prof_id)
        item.setData(Qt.ItemDataRole.UserRole, prof_id)
        self._ui.triangulation_profiles_list.addItem(item)
        self._ui.triangulation_profile_input.clear()
        self._clear_status()

    def _on_remove_triangulation_profile(self) -> None:
        """Remove the selected profile from the triangulation profiles list."""
        current = self._ui.triangulation_profiles_list.currentItem()
        if not current:
            self._update_status("Välj en profil att ta bort.")
            return
        row = self._ui.triangulation_profiles_list.row(current)
        self._ui.triangulation_profiles_list.takeItem(row)
        self._clear_status()

    def _on_save_triangulation(self) -> None:
        """Validate and save the triangulation form data."""
        company_id = self._ui.triangulation_company_combo.currentData()
        if not company_id:
            self._update_status("Välj ett företag för trianguleringen.")
            return

        shared_cm = self._ui.triangulation_shared_cm_input.value()
        segment_count = self._ui.triangulation_segment_count_input.value()
        largest_segment_cm = self._ui.triangulation_largest_segment_input.value()

        # Collect profile IDs
        profile_ids: list[str] = []
        for i in range(self._ui.triangulation_profiles_list.count()):
            item = self._ui.triangulation_profiles_list.item(i)
            if item:
                pid = item.data(Qt.ItemDataRole.UserRole)
                if pid:
                    profile_ids.append(pid)

        if len(profile_ids) < 3:
            self._update_status("Minst 3 profil-ID krävs.")
            return

        cluster_id = self._ui.triangulation_cluster_combo.currentData() or None
        notes = self._ui.triangulation_notes_input.toPlainText()

        if self._editing_triangulation:
            self._editing_triangulation.company_id = company_id
            self._editing_triangulation.shared_cm = shared_cm
            self._editing_triangulation.segment_count = segment_count
            self._editing_triangulation.largest_segment_cm = largest_segment_cm
            self._editing_triangulation.profile_ids = profile_ids
            self._editing_triangulation.cluster_id = cluster_id
            self._editing_triangulation.notes = notes
        else:
            new_tri = DnaTriangulation(
                id=str(uuid.uuid4()),
                company_id=company_id,
                profile_ids=profile_ids,
                shared_cm=shared_cm,
                segment_count=segment_count,
                largest_segment_cm=largest_segment_cm,
                cluster_id=cluster_id,
                notes=notes,
            )
            self._project_data.dna_triangulations.append(new_tri)
            self._editing_triangulation = new_tri

        self._refresh_triangulations_list()
        self._clear_status()
        logger.info(
            "DNA-triangulering sparad: %.2f cM, %d profiler",
            shared_cm, len(profile_ids),
        )

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    def _update_status(self, message: str) -> None:
        """Update the status label text with an error/info message.

        Args:
            message: The status message to display.
        """
        self._ui.status_label.setText(message)

    def _clear_status(self) -> None:
        """Clear the status label."""
        self._ui.status_label.setText("")
