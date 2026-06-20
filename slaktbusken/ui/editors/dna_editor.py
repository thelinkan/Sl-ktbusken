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
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
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
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.dna_match_display import format_match_entry, matches_filter
from slaktbusken.ui.generated.ui_dna_editor import Ui_DnaEditor

logger = logging.getLogger(__name__)

# Valid chromosome values
CHROMOSOMES: list[str] = [str(i) for i in range(1, 23)] + ["X", "Y"]

# Test type options
TEST_TYPES: list[str] = ["autosomal", "y-dna", "mtdna"]

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
    abs_path = project_folder / Path(media_item.file)

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

    Provides management of DNA companies, profiles, matches, segments,
    clusters, and triangulations via a six-tab interface. Each tab
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

        # Add logo choose button and preview label to company form
        self._logo_choose_button = QPushButton("Välj logo...")
        self._logo_choose_button.setEnabled(False)
        self._logo_preview_label = QLabel()
        self._logo_preview_label.setFixedSize(LOGO_PREVIEW_SIZE, LOGO_PREVIEW_SIZE)

        logo_row_layout = QHBoxLayout()
        logo_row_layout.addWidget(self._logo_choose_button)
        logo_row_layout.addWidget(self._logo_preview_label)

        self._ui.company_form_layout.insertRow(3, "", logo_row_layout)

        self._logo_choose_button.clicked.connect(self._on_choose_logo)

        self._populate_combos()
        self._connect_signals()
        self._refresh_all_lists()

    # ------------------------------------------------------------------
    # Private: setup
    # ------------------------------------------------------------------

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

        # Segments tab
        self._ui.segments_list.currentItemChanged.connect(
            self._on_segment_selected
        )
        self._ui.add_segment_button.clicked.connect(self._on_add_segment)
        self._ui.remove_segment_button.clicked.connect(self._on_remove_segment)
        self._ui.save_segment_button.clicked.connect(self._on_save_segment)

        # Clusters tab
        self._ui.clusters_list.currentItemChanged.connect(
            self._on_cluster_selected
        )
        self._ui.add_cluster_button.clicked.connect(self._on_add_cluster)
        self._ui.remove_cluster_button.clicked.connect(self._on_remove_cluster)
        self._ui.save_cluster_button.clicked.connect(self._on_save_cluster)
        self._ui.add_cluster_member_button.clicked.connect(
            self._on_add_cluster_member
        )
        self._ui.remove_cluster_member_button.clicked.connect(
            self._on_remove_cluster_member
        )
        self._ui.add_cluster_match_button.clicked.connect(
            self._on_add_cluster_match
        )
        self._ui.remove_cluster_match_button.clicked.connect(
            self._on_remove_cluster_match
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
        self._ui.save_triangulation_button.clicked.connect(
            self._on_save_triangulation
        )
        self._ui.add_triangulation_segment_button.clicked.connect(
            self._on_add_triangulation_segment
        )
        self._ui.remove_triangulation_segment_button.clicked.connect(
            self._on_remove_triangulation_segment
        )
        self._ui.add_triangulation_profile_button.clicked.connect(
            self._on_add_triangulation_profile
        )
        self._ui.remove_triangulation_profile_button.clicked.connect(
            self._on_remove_triangulation_profile
        )

    # ------------------------------------------------------------------
    # Private: refresh lists
    # ------------------------------------------------------------------

    def _refresh_all_lists(self) -> None:
        """Refresh all entity lists across all tabs."""
        self._refresh_companies_list()
        self._refresh_profiles_list()
        self._refresh_matches_list()
        self._refresh_segments_list()
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
        """Rebuild the clusters list widget."""
        self._ui.clusters_list.clear()
        for cluster in self._project_data.dna_clusters:
            display = cluster.name or cluster.id
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, cluster.id)
            self._ui.clusters_list.addItem(item)

    def _refresh_triangulations_list(self) -> None:
        """Rebuild the triangulations list widget."""
        self._ui.triangulations_list.clear()
        for tri in self._project_data.dna_triangulations:
            display = f"Chr {tri.chromosome}: {tri.overlap_start}-{tri.overlap_end}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, tri.id)
            self._ui.triangulations_list.addItem(item)

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

    def _on_add_company(self) -> None:
        """Clear form for new company entry."""
        self._editing_company = None
        self._ui.company_name_input.clear()
        self._ui.company_notes_input.clear()
        self._ui.company_logo_input.clear()
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

        if self._editing_company:
            self._editing_company.name = name
            self._editing_company.description = description
            self._editing_company.logo_media_id = logo_id
        else:
            new_company = DnaCompany(
                id=str(uuid.uuid4()),
                name=name,
                logo_media_id=logo_id,
                description=description,
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
        self._ui.profile_person_input.setText(profile.person_id)
        idx = self._ui.profile_company_combo.findData(profile.company_id)
        if idx >= 0:
            self._ui.profile_company_combo.setCurrentIndex(idx)
        idx = self._ui.profile_test_type_combo.findData(profile.test_type)
        if idx >= 0:
            self._ui.profile_test_type_combo.setCurrentIndex(idx)
        self._ui.profile_kit_name_input.setText(profile.kit_name)
        self._ui.profile_kit_id_input.setText(profile.kit_id)
        self._ui.profile_admin_person_input.setText(
            profile.admin_person_id or ""
        )
        idx = self._ui.profile_admin_status_combo.findData(profile.admin_status)
        if idx >= 0:
            self._ui.profile_admin_status_combo.setCurrentIndex(idx)
        self._ui.profile_notes_input.setPlainText(profile.notes)

    def _on_add_profile(self) -> None:
        """Clear form for new profile entry."""
        self._editing_profile = None
        self._ui.profile_person_input.clear()
        self._ui.profile_company_combo.setCurrentIndex(0)
        self._ui.profile_test_type_combo.setCurrentIndex(0)
        self._ui.profile_kit_name_input.clear()
        self._ui.profile_kit_id_input.clear()
        self._ui.profile_admin_person_input.clear()
        self._ui.profile_admin_status_combo.setCurrentIndex(0)
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
        admin_person_id = (
            self._ui.profile_admin_person_input.text().strip() or None
        )
        if admin_person_id:
            if not any(
                p.id == admin_person_id for p in self._project_data.persons
            ):
                self._update_status(
                    f"Admin person-ID '{admin_person_id}' finns inte."
                )
                return

        admin_status = self._ui.profile_admin_status_combo.currentData() or ""
        notes = self._ui.profile_notes_input.toPlainText()

        if self._editing_profile:
            self._editing_profile.person_id = person_id
            self._editing_profile.company_id = company_id
            self._editing_profile.test_type = test_type
            self._editing_profile.kit_name = kit_name
            self._editing_profile.kit_id = kit_id
            self._editing_profile.admin_person_id = admin_person_id
            self._editing_profile.admin_status = admin_status
            self._editing_profile.notes = notes
        else:
            new_profile = DnaProfile(
                id=str(uuid.uuid4()),
                person_id=person_id,
                company_id=company_id,
                test_type=test_type,
                kit_name=kit_name,
                kit_id=kit_id,
                admin_person_id=admin_person_id,
                admin_status=admin_status,
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
        self._clear_status()

    def _on_remove_match(self) -> None:
        """Remove the selected match from project data."""
        current = self._ui.matches_list.currentItem()
        if not current:
            self._update_status("Välj en matchning att ta bort.")
            return
        match_id = current.data(Qt.ItemDataRole.UserRole)
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
        """Handle cluster list selection change.

        Args:
            current: The newly selected item, or None.
            _previous: The previously selected item (unused).
        """
        if current is None:
            return
        cluster_id = current.data(Qt.ItemDataRole.UserRole)
        for cluster in self._project_data.dna_clusters:
            if cluster.id == cluster_id:
                self._editing_cluster = cluster
                self._load_cluster(cluster)
                break

    def _load_cluster(self, cluster: DnaCluster) -> None:
        """Populate cluster form fields from a DnaCluster instance.

        Args:
            cluster: The cluster to load into the form.
        """
        self._ui.cluster_name_input.setText(cluster.name)
        self._ui.cluster_notes_input.setPlainText(cluster.notes)
        self._ui.cluster_color_input.setText(cluster.color or "")

        # Populate members list
        self._ui.cluster_members_list.clear()
        for person_id in cluster.person_ids:
            item = QListWidgetItem(person_id)
            item.setData(Qt.ItemDataRole.UserRole, person_id)
            self._ui.cluster_members_list.addItem(item)

        # Populate matches list
        self._ui.cluster_matches_list.clear()
        for match_id in cluster.dna_match_ids:
            item = QListWidgetItem(match_id)
            item.setData(Qt.ItemDataRole.UserRole, match_id)
            self._ui.cluster_matches_list.addItem(item)

    def _on_add_cluster(self) -> None:
        """Clear form for new cluster entry."""
        self._editing_cluster = None
        self._ui.cluster_name_input.clear()
        self._ui.cluster_notes_input.clear()
        self._ui.cluster_color_input.clear()
        self._ui.cluster_members_list.clear()
        self._ui.cluster_matches_list.clear()
        self._clear_status()

    def _on_remove_cluster(self) -> None:
        """Remove the selected cluster from project data."""
        current = self._ui.clusters_list.currentItem()
        if not current:
            self._update_status("Välj ett kluster att ta bort.")
            return
        cluster_id = current.data(Qt.ItemDataRole.UserRole)
        self._project_data.dna_clusters = [
            c for c in self._project_data.dna_clusters if c.id != cluster_id
        ]
        self._editing_cluster = None
        self._refresh_clusters_list()
        self._refresh_cluster_combos()
        self._clear_status()

    def _on_add_cluster_member(self) -> None:
        """Add a person ID to the cluster members list."""
        person_id = self._ui.cluster_member_input.text().strip()
        if not person_id:
            self._update_status("Ange ett person-ID.")
            return
        if not any(p.id == person_id for p in self._project_data.persons):
            self._update_status(f"Person-ID '{person_id}' finns inte.")
            return
        item = QListWidgetItem(person_id)
        item.setData(Qt.ItemDataRole.UserRole, person_id)
        self._ui.cluster_members_list.addItem(item)
        self._ui.cluster_member_input.clear()
        self._clear_status()

    def _on_remove_cluster_member(self) -> None:
        """Remove the selected member from the cluster members list."""
        current = self._ui.cluster_members_list.currentItem()
        if not current:
            self._update_status("Välj en medlem att ta bort.")
            return
        row = self._ui.cluster_members_list.row(current)
        self._ui.cluster_members_list.takeItem(row)
        self._clear_status()

    def _on_add_cluster_match(self) -> None:
        """Add a match to the cluster matches list."""
        match_id = self._ui.cluster_match_combo.currentData()
        if not match_id:
            self._update_status("Välj en matchning att lägga till.")
            return
        item = QListWidgetItem(match_id)
        item.setData(Qt.ItemDataRole.UserRole, match_id)
        self._ui.cluster_matches_list.addItem(item)
        self._clear_status()

    def _on_remove_cluster_match(self) -> None:
        """Remove the selected match from the cluster matches list."""
        current = self._ui.cluster_matches_list.currentItem()
        if not current:
            self._update_status("Välj en matchning att ta bort.")
            return
        row = self._ui.cluster_matches_list.row(current)
        self._ui.cluster_matches_list.takeItem(row)
        self._clear_status()

    def _on_save_cluster(self) -> None:
        """Validate and save the cluster form data."""
        name = self._ui.cluster_name_input.text().strip()
        if not name:
            self._update_status("Klusternamn krävs.")
            return
        if len(name) > 200:
            self._update_status("Klusternamn får vara max 200 tecken.")
            return

        notes = self._ui.cluster_notes_input.toPlainText()
        color = self._ui.cluster_color_input.text().strip() or None

        # Collect person IDs from members list
        person_ids: list[str] = []
        for i in range(self._ui.cluster_members_list.count()):
            item = self._ui.cluster_members_list.item(i)
            if item:
                pid = item.data(Qt.ItemDataRole.UserRole)
                if pid:
                    person_ids.append(pid)

        # Collect match IDs from matches list
        match_ids: list[str] = []
        for i in range(self._ui.cluster_matches_list.count()):
            item = self._ui.cluster_matches_list.item(i)
            if item:
                mid = item.data(Qt.ItemDataRole.UserRole)
                if mid:
                    match_ids.append(mid)

        if self._editing_cluster:
            self._editing_cluster.name = name
            self._editing_cluster.notes = notes
            self._editing_cluster.color = color
            self._editing_cluster.person_ids = person_ids
            self._editing_cluster.dna_match_ids = match_ids
        else:
            new_cluster = DnaCluster(
                id=str(uuid.uuid4()),
                name=name,
                notes=notes,
                company_ids=[],
                person_ids=person_ids,
                dna_match_ids=match_ids,
                color=color,
            )
            self._project_data.dna_clusters.append(new_cluster)
            self._editing_cluster = new_cluster

        self._refresh_clusters_list()
        self._refresh_cluster_combos()
        self._clear_status()
        logger.info("DNA-kluster sparat: %s", name)

    # ------------------------------------------------------------------
    # Triangulations: selection, add, remove, save, segment/profile mgmt
    # ------------------------------------------------------------------

    def _on_triangulation_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        """Handle triangulation list selection change.

        Args:
            current: The newly selected item, or None.
            _previous: The previously selected item (unused).
        """
        if current is None:
            return
        tri_id = current.data(Qt.ItemDataRole.UserRole)
        for tri in self._project_data.dna_triangulations:
            if tri.id == tri_id:
                self._editing_triangulation = tri
                self._load_triangulation(tri)
                break

    def _load_triangulation(self, tri: DnaTriangulation) -> None:
        """Populate triangulation form fields from a DnaTriangulation instance.

        Args:
            tri: The triangulation to load into the form.
        """
        idx = self._ui.triangulation_company_combo.findData(tri.company_id)
        if idx >= 0:
            self._ui.triangulation_company_combo.setCurrentIndex(idx)
        idx = self._ui.triangulation_chromosome_combo.findData(tri.chromosome)
        if idx >= 0:
            self._ui.triangulation_chromosome_combo.setCurrentIndex(idx)
        self._ui.triangulation_start_input.setValue(tri.overlap_start)
        self._ui.triangulation_end_input.setValue(tri.overlap_end)
        idx = self._ui.triangulation_cluster_combo.findData(tri.cluster_id or "")
        if idx >= 0:
            self._ui.triangulation_cluster_combo.setCurrentIndex(idx)
        self._ui.triangulation_notes_input.setPlainText(tri.notes)

        # Populate segment IDs list
        self._ui.triangulation_segments_list.clear()
        for seg_id in tri.segment_ids:
            item = QListWidgetItem(seg_id)
            item.setData(Qt.ItemDataRole.UserRole, seg_id)
            self._ui.triangulation_segments_list.addItem(item)

        # Populate profile IDs list
        self._ui.triangulation_profiles_list.clear()
        for prof_id in tri.profile_ids:
            item = QListWidgetItem(prof_id)
            item.setData(Qt.ItemDataRole.UserRole, prof_id)
            self._ui.triangulation_profiles_list.addItem(item)

    def _on_add_triangulation(self) -> None:
        """Clear form for new triangulation entry."""
        self._editing_triangulation = None
        self._ui.triangulation_company_combo.setCurrentIndex(0)
        self._ui.triangulation_chromosome_combo.setCurrentIndex(0)
        self._ui.triangulation_start_input.setValue(0)
        self._ui.triangulation_end_input.setValue(0)
        self._ui.triangulation_cluster_combo.setCurrentIndex(0)
        self._ui.triangulation_notes_input.clear()
        self._ui.triangulation_segments_list.clear()
        self._ui.triangulation_profiles_list.clear()
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

        chromosome = self._ui.triangulation_chromosome_combo.currentData() or ""
        overlap_start = self._ui.triangulation_start_input.value()
        overlap_end = self._ui.triangulation_end_input.value()

        if overlap_start >= overlap_end:
            self._update_status(
                "Överlappning start måste vara mindre än slut."
            )
            return

        # Collect segment IDs
        segment_ids: list[str] = []
        for i in range(self._ui.triangulation_segments_list.count()):
            item = self._ui.triangulation_segments_list.item(i)
            if item:
                sid = item.data(Qt.ItemDataRole.UserRole)
                if sid:
                    segment_ids.append(sid)

        if len(segment_ids) < 2:
            self._update_status("Minst 2 segment-ID krävs.")
            return

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
            self._editing_triangulation.chromosome = chromosome
            self._editing_triangulation.overlap_start = overlap_start
            self._editing_triangulation.overlap_end = overlap_end
            self._editing_triangulation.segment_ids = segment_ids
            self._editing_triangulation.profile_ids = profile_ids
            self._editing_triangulation.cluster_id = cluster_id
            self._editing_triangulation.notes = notes
        else:
            new_tri = DnaTriangulation(
                id=str(uuid.uuid4()),
                company_id=company_id,
                chromosome=chromosome,
                overlap_start=overlap_start,
                overlap_end=overlap_end,
                segment_ids=segment_ids,
                profile_ids=profile_ids,
                cluster_id=cluster_id,
                notes=notes,
            )
            self._project_data.dna_triangulations.append(new_tri)
            self._editing_triangulation = new_tri

        self._refresh_triangulations_list()
        self._clear_status()
        logger.info(
            "DNA-triangulering sparad: Chr %s, %s-%s",
            chromosome, overlap_start, overlap_end,
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
