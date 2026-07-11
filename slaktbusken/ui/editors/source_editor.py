"""Source editor widget.

Provides a split-panel editor for Source records: a filterable source
list on the left, and a form on the right with provider, source_type,
title, reference_text, dynamic structured_reference fields based on
source type, media linking, and repository references.
Validates that title and type are set before save. All UI text is in Swedish.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QListWidgetItem,
    QMessageBox,
    QWidget,
)

from slaktbusken.model.media import MediaItem
from slaktbusken.model.project import ProjectData
from slaktbusken.model.source import RepositoryRef, Source, StructuredReference
from slaktbusken.parsing.reference_parser import ParsedReference, parse_reference
from slaktbusken.services.media_utils import resolve_filename_conflict
from slaktbusken.services.source_formatting import format_source_title
from slaktbusken.services.source_links import generate_direct_link
from slaktbusken.services.source_stats import compute_usage_stats
from slaktbusken.ui.dialogs.usage_detail_dialog import UsageDetailDialog
from slaktbusken.ui.generated.ui_source_editor import Ui_SourceEditor

logger = logging.getLogger(__name__)

# Source type mapping: internal key -> Swedish display name
SOURCE_TYPE_MAP: dict[str, str] = {
    "church_book": "Kyrkobok",
    "database": "Databas",
    "death_notice": "Dödsannons",
    "newspaper": "Tidning",
    "photograph": "Fotografi",
    "census": "Folkräkning",
    "other": "Övrigt",
}

# Reverse mapping: Swedish display name -> internal key
SOURCE_TYPE_REVERSE: dict[str, str] = {v: k for k, v in SOURCE_TYPE_MAP.items()}

# Structured reference fields by source type
STRUCTURED_FIELDS: dict[str, list[str]] = {
    "church_book": ["parish", "county_code", "series", "volume", "years", "image", "page"],
    "database": ["database_name", "record_id"],
    "death_notice": ["newspaper", "publication_date", "page"],
    "newspaper": ["newspaper", "date", "page", "article_title"],
}

# File extensions for media attachment
IMAGE_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
DOCUMENT_EXTENSIONS: set[str] = {".pdf", ".docx", ".rtf", ".odt"}


class SourceEditor(QWidget):
    """Editor widget for Source records with list and form panels.

    Displays a filterable source list on the left and a full edit form on the
    right. The structured reference group dynamically shows/hides fields
    depending on the selected source_type.

    Signals:
        save_requested: Emitted when the user saves successfully.
        cancel_requested: Emitted when the user cancels editing.

    Args:
        project_data: The current project data containing all entities.
        source: Optional existing Source to edit. If None, creates a new source.
        parent: Optional parent widget.
    """

    save_requested = Signal()
    cancel_requested = Signal()

    def __init__(
        self,
        project_data: ProjectData,
        source: Optional[Source] = None,
        project_folder: Optional[Path] = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the source editor.

        Args:
            project_data: The current project data containing all entities.
            source: Optional existing Source to edit. If None, creates a new source.
            project_folder: Optional path to the project folder for media file operations.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._project_data = project_data
        self._source = source
        self._project_folder = project_folder
        self._saved_source: Optional[Source] = None
        self._pending_arkivreferens: str = ""
        self._pending_leverantor_id: str = ""
        self._pending_kalltyp_id: str = ""
        self._inhibit_reference_parse: bool = False

        # Set up UI from generated form
        self._ui = Ui_SourceEditor()
        self._ui.setupUi(self)

        # Add direct link label programmatically (after basic_group)
        self._direct_link_label = QLabel(self._ui.scroll_content)
        self._direct_link_label.setObjectName("direct_link_label")
        self._direct_link_label.setOpenExternalLinks(False)
        self._direct_link_label.setTextFormat(Qt.TextFormat.RichText)
        self._direct_link_label.setWordWrap(True)
        self._direct_link_label.linkActivated.connect(self._on_direct_link_clicked)
        self._direct_link_label.setVisible(False)
        # Insert after basic_group (index 0) in scroll_content_layout
        self._ui.scroll_content_layout.insertWidget(1, self._direct_link_label)

        self._populate_type_combo()
        self._connect_signals()
        self._update_structured_fields()
        self._refresh_source_list()

        if self._source is not None:
            self._load_source()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def saved_source(self) -> Optional[Source]:
        """The saved Source result, or None if not yet saved."""
        return self._saved_source

    def get_source(self) -> Optional[Source]:
        """Return the saved source, or None if save was not performed.

        Returns:
            The Source object if save was successful, None otherwise.
        """
        return self._saved_source

    # ------------------------------------------------------------------
    # Private: setup
    # ------------------------------------------------------------------

    def _populate_type_combo(self) -> None:
        """Fill the source type combo box with Swedish display names."""
        self._ui.source_type_combo.clear()
        for internal_key, display_name in SOURCE_TYPE_MAP.items():
            self._ui.source_type_combo.addItem(display_name, internal_key)

    def _connect_signals(self) -> None:
        """Wire up UI signals to handler slots."""
        # Source type change -> update structured fields visibility
        self._ui.source_type_combo.currentIndexChanged.connect(
            self._update_structured_fields
        )

        # Search filter
        self._ui.search_input.textChanged.connect(self._on_search_changed)

        # List buttons
        self._ui.add_source_button.clicked.connect(self._on_add_source)
        self._ui.delete_source_button.clicked.connect(self._on_delete_source)

        # Source list selection
        self._ui.source_list.currentItemChanged.connect(self._on_source_selected)

        # Media buttons
        self._ui.add_media_button.clicked.connect(self._on_add_media)
        self._ui.remove_media_button.clicked.connect(self._on_remove_media)

        # Repository buttons
        self._ui.add_repository_button.clicked.connect(self._on_add_repository)
        self._ui.remove_repository_button.clicked.connect(self._on_remove_repository)

        # Save/Cancel
        self._ui.save_button.clicked.connect(self._on_save)
        self._ui.cancel_button.clicked.connect(self._on_cancel)

        # Reference text parsing on paste/change
        self._ui.reference_text_input.textChanged.connect(
            self._on_reference_text_changed
        )

        # Double-click on source list to show usage detail dialog
        self._ui.source_list.itemDoubleClicked.connect(self._on_source_usage_detail)

    # ------------------------------------------------------------------
    # Private: structured fields visibility
    # ------------------------------------------------------------------

    def _update_structured_fields(self) -> None:
        """Show/hide structured reference fields based on selected source type."""
        current_type = self._ui.source_type_combo.currentData() or ""

        # Church book fields
        church_visible = current_type == "church_book"
        self._ui.parish_label.setVisible(church_visible)
        self._ui.parish_input.setVisible(church_visible)
        self._ui.county_code_label.setVisible(church_visible)
        self._ui.county_code_input.setVisible(church_visible)
        self._ui.series_label.setVisible(church_visible)
        self._ui.series_input.setVisible(church_visible)
        self._ui.volume_label.setVisible(church_visible)
        self._ui.volume_input.setVisible(church_visible)
        self._ui.years_label.setVisible(church_visible)
        self._ui.years_input.setVisible(church_visible)
        self._ui.image_label.setVisible(church_visible)
        self._ui.image_input.setVisible(church_visible)
        self._ui.page_label.setVisible(church_visible)
        self._ui.page_input.setVisible(church_visible)

        # Database fields
        db_visible = current_type == "database"
        self._ui.database_name_label.setVisible(db_visible)
        self._ui.database_name_input.setVisible(db_visible)
        self._ui.record_id_label.setVisible(db_visible)
        self._ui.record_id_input.setVisible(db_visible)

        # Death notice fields
        dn_visible = current_type == "death_notice"
        self._ui.dn_newspaper_label.setVisible(dn_visible)
        self._ui.dn_newspaper_input.setVisible(dn_visible)
        self._ui.publication_date_label.setVisible(dn_visible)
        self._ui.publication_date_input.setVisible(dn_visible)
        self._ui.dn_page_label.setVisible(dn_visible)
        self._ui.dn_page_input.setVisible(dn_visible)

        # Newspaper fields
        np_visible = current_type == "newspaper"
        self._ui.np_newspaper_label.setVisible(np_visible)
        self._ui.np_newspaper_input.setVisible(np_visible)
        self._ui.np_date_label.setVisible(np_visible)
        self._ui.np_date_input.setVisible(np_visible)
        self._ui.np_page_label.setVisible(np_visible)
        self._ui.np_page_input.setVisible(np_visible)
        self._ui.article_title_label.setVisible(np_visible)
        self._ui.article_title_input.setVisible(np_visible)

        # Hide entire group if no structured fields for this type
        has_fields = current_type in STRUCTURED_FIELDS
        self._ui.structured_ref_group.setVisible(has_fields)

    # ------------------------------------------------------------------
    # Private: source list management
    # ------------------------------------------------------------------

    def _refresh_source_list(self, filter_text: str = "") -> None:
        """Rebuild the source list, optionally filtering by title or provider.

        Each list item displays inline usage statistics:
        "{title} ({provider}) [{person_count} pers, {event_count} händ]"

        Args:
            filter_text: Case-insensitive filter string for title or provider.
        """
        self._ui.source_list.clear()
        filter_lower = filter_text.lower()

        for source in self._project_data.sources:
            if filter_lower:
                title_match = filter_lower in source.title.lower()
                provider_match = filter_lower in source.provider.lower()
                if not title_match and not provider_match:
                    continue

            # Compute usage stats for this source
            stats = compute_usage_stats(source.id, self._project_data.events)

            display = source.title or source.id
            if source.provider:
                display = f"{display} ({source.provider})"
            display = f"{display} [{stats.person_count} pers, {stats.event_count} händ]"

            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, source.id)
            self._ui.source_list.addItem(item)

    def _on_search_changed(self, text: str) -> None:
        """Handle search input text changes.

        Args:
            text: The current search text.
        """
        self._refresh_source_list(text)

    def _on_source_usage_detail(self, item: QListWidgetItem) -> None:
        """Handle double-click on source list item to show usage detail dialog.

        Opens a dialog listing distinct persons referencing the source,
        with each person's events grouped beneath their name.

        Args:
            item: The double-clicked list item.
        """
        source_id = item.data(Qt.ItemDataRole.UserRole)
        source = None
        for s in self._project_data.sources:
            if s.id == source_id:
                source = s
                break

        if source is None:
            return

        dialog = UsageDetailDialog(
            self,
            source=source,
            events=self._project_data.events,
            persons=self._project_data.persons,
        )
        dialog.exec()

    def _on_source_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        """Handle source list selection change.

        Args:
            current: The newly selected item, or None.
            _previous: The previously selected item (unused).
        """
        if current is None:
            return

        source_id = current.data(Qt.ItemDataRole.UserRole)
        for source in self._project_data.sources:
            if source.id == source_id:
                self._source = source
                self._load_source()
                break

    def _on_add_source(self) -> None:
        """Clear the form to create a new source."""
        self._source = None
        self._clear_form()
        self._clear_status()

    def _on_delete_source(self) -> None:
        """Remove the selected source from the project data."""
        current = self._ui.source_list.currentItem()
        if not current:
            self._update_status("Välj en källa att ta bort.")
            return

        source_id = current.data(Qt.ItemDataRole.UserRole)

        # Check for referencing events (source_refs in date or place)
        referencing_events = self._find_referencing_events(source_id)
        if referencing_events:
            event_lines: list[str] = []
            for e in referencing_events:
                parts = [e.type]
                if e.date:
                    parts.append(e.date.value)
                if e.participants:
                    participant_names = ", ".join(
                        p.person_id for p in e.participants
                    )
                    parts.append(participant_names)
                event_lines.append(f"  • {' — '.join(parts)}")
            event_list = "\n".join(event_lines)
            reply = QMessageBox.warning(
                self,
                "Varning",
                f"Denna källa refereras av följande händelser:\n\n"
                f"{event_list}\n\n"
                "Vill du verkligen ta bort källan?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._project_data.sources = [
            s for s in self._project_data.sources if s.id != source_id
        ]
        self._source = None
        self._clear_form()
        self._refresh_source_list(self._ui.search_input.text())
        self._clear_status()

    def _find_referencing_events(self, source_id: str) -> list:
        """Find all events that reference a given source via source_refs.

        Checks both date.source_refs and place.source_refs on each event.

        Args:
            source_id: The source ID to search for.

        Returns:
            List of Event objects referencing this source.
        """
        referencing = []
        for event in self._project_data.events:
            found = False
            if event.date and event.date.source_refs:
                for sr in event.date.source_refs:
                    if sr.source_id == source_id:
                        found = True
                        break
            if not found and event.place and event.place.source_refs:
                for sr in event.place.source_refs:
                    if sr.source_id == source_id:
                        found = True
                        break
            if found:
                referencing.append(event)
        return referencing

    # ------------------------------------------------------------------
    # Private: load source data
    # ------------------------------------------------------------------

    def _load_source(self) -> None:
        """Populate all fields from the current source."""
        if self._source is None:
            return

        # Inhibit reference parsing while loading existing source data
        self._inhibit_reference_parse = True
        try:
            # Provider
            self._ui.provider_input.setText(self._source.provider)

            # Source type
            type_index = self._ui.source_type_combo.findData(self._source.source_type)
            if type_index >= 0:
                self._ui.source_type_combo.setCurrentIndex(type_index)

            # Title
            self._ui.title_input.setText(self._source.title)

            # Reference text
            self._ui.reference_text_input.setText(self._source.reference_text)

            # Provider ref
            self._ui.provider_ref_input.setText(self._source.provider_ref)

            # Short note
            self._ui.short_note_input.setText(self._source.short_note)

            # Free note
            self._ui.free_note_input.setPlainText(self._source.free_note)

            # Load pending fields from source
            self._pending_leverantor_id = self._source.leverantor_id
            self._pending_kalltyp_id = self._source.kalltyp_id
            self._pending_arkivreferens = self._source.arkivreferens

            # Structured reference fields
            self._load_structured_reference()

            # Media
            self._refresh_media_list()

            # Repository refs
            self._refresh_repository_list()

            # Direct link
            self._update_direct_link()
        finally:
            self._inhibit_reference_parse = False

    def _load_structured_reference(self) -> None:
        """Populate structured reference fields from the source data."""
        if self._source is None:
            return

        fields = self._source.structured_reference.fields
        source_type = self._source.source_type

        if source_type == "church_book":
            self._ui.parish_input.setText(str(fields.get("parish", "") or ""))
            self._ui.county_code_input.setText(str(fields.get("county_code", "") or ""))
            self._ui.series_input.setText(str(fields.get("series", "") or ""))
            self._ui.volume_input.setText(str(fields.get("volume", "") or ""))
            self._ui.years_input.setText(str(fields.get("years", "") or ""))
            self._ui.image_input.setText(str(fields.get("image", "") or ""))
            self._ui.page_input.setText(str(fields.get("page", "") or ""))
        elif source_type == "database":
            self._ui.database_name_input.setText(str(fields.get("database_name", "") or ""))
            self._ui.record_id_input.setText(str(fields.get("record_id", "") or ""))
        elif source_type == "death_notice":
            self._ui.dn_newspaper_input.setText(str(fields.get("newspaper", "") or ""))
            self._ui.publication_date_input.setText(str(fields.get("publication_date", "") or ""))
            self._ui.dn_page_input.setText(str(fields.get("page", "") or ""))
        elif source_type == "newspaper":
            self._ui.np_newspaper_input.setText(str(fields.get("newspaper", "") or ""))
            self._ui.np_date_input.setText(str(fields.get("date", "") or ""))
            self._ui.np_page_input.setText(str(fields.get("page", "") or ""))
            self._ui.article_title_input.setText(str(fields.get("article_title", "") or ""))

    # ------------------------------------------------------------------
    # Private: media management
    # ------------------------------------------------------------------

    def _refresh_media_list(self) -> None:
        """Populate the media list with items linked to this source."""
        self._ui.media_list.clear()

        if self._source is None:
            return

        for media_id in self._source.media_ids:
            display = media_id
            for media in self._project_data.media:
                if media.id == media_id:
                    display = media.title or media.file or media.id
                    break
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, media_id)
            self._ui.media_list.addItem(item)

    def _on_add_media(self) -> None:
        """Attach a media file to the source via file chooser dialog.

        Opens a file chooser filtered to image and document types, copies the
        selected file to the project media directory (resolving filename conflicts),
        creates a MediaItem record, and appends its ID to the source's media list.
        """
        if self._project_folder is None:
            self._update_status("Inget projekt öppet — kan inte lägga till media.")
            return

        # Build file filter string
        image_exts = " ".join(f"*{ext}" for ext in sorted(IMAGE_EXTENSIONS))
        doc_exts = " ".join(f"*{ext}" for ext in sorted(DOCUMENT_EXTENSIONS))
        all_exts = f"{image_exts} {doc_exts}"
        file_filter = (
            f"Alla mediatyper ({all_exts});;"
            f"Bilder ({image_exts});;"
            f"Dokument ({doc_exts})"
        )

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Lägg till media",
            "",
            file_filter,
        )

        if not file_path:
            # User cancelled — take no action (Requirement 4.2)
            return

        source_path = Path(file_path)
        ext = source_path.suffix.lower()

        # Determine media type
        if ext in IMAGE_EXTENSIONS:
            media_type = "photo"
            subfolder = "source-image"
        elif ext in DOCUMENT_EXTENSIONS:
            media_type = "document"
            subfolder = "document"
        else:
            self._update_status("Filtypen stöds inte.")
            return

        # Determine target directory
        media_dir = self._project_folder / "media" / subfolder
        media_dir.mkdir(parents=True, exist_ok=True)

        # Resolve filename conflicts
        existing_names = {f.name for f in media_dir.iterdir() if f.is_file()}
        target_name = resolve_filename_conflict(source_path.name, existing_names)
        target_path = media_dir / target_name

        # Copy file to media directory
        try:
            shutil.copy2(str(source_path), str(target_path))
        except OSError as e:
            QMessageBox.warning(
                self,
                "Fel",
                f"Kunde inte kopiera filen: {e}",
            )
            return

        # Compute relative path from media directory root (media/subfolder/filename)
        relative_path = f"media/{subfolder}/{target_name}"

        # Derive title from source title
        title = self._ui.title_input.text().strip() or source_path.stem

        # Create media record
        media_id = str(uuid.uuid4())
        media_item = MediaItem(
            id=media_id,
            type=media_type,
            file=relative_path,
            title=title,
        )

        # Add to project data
        self._project_data.media.append(media_item)

        # Add to the media list UI
        display = media_item.title or media_item.file or media_item.id
        list_item = QListWidgetItem(display)
        list_item.setData(Qt.ItemDataRole.UserRole, media_id)
        self._ui.media_list.addItem(list_item)
        self._clear_status()

    def _on_remove_media(self) -> None:
        """Remove the currently selected media item from the list."""
        current = self._ui.media_list.currentItem()
        if not current:
            self._update_status("Välj ett mediaobjekt att ta bort.")
            return

        row = self._ui.media_list.row(current)
        self._ui.media_list.takeItem(row)
        self._clear_status()

    # ------------------------------------------------------------------
    # Private: repository refs management
    # ------------------------------------------------------------------

    def _refresh_repository_list(self) -> None:
        """Populate the repository list with refs linked to this source."""
        self._ui.repository_list.clear()

        if self._source is None:
            return

        for repo_ref in self._source.repository_refs:
            display = repo_ref.repository_id
            for repo in self._project_data.repositories:
                if repo.id == repo_ref.repository_id:
                    display = repo.name or repo.id
                    break
            if repo_ref.call_number:
                display = f"{display} [{repo_ref.call_number}]"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, repo_ref.repository_id)
            self._ui.repository_list.addItem(item)

    def _on_add_repository(self) -> None:
        """Add a repository reference from the project's available repositories.

        Adds the first repository not already linked.
        """
        # Collect currently linked repository IDs
        linked_ids: set[str] = set()
        for i in range(self._ui.repository_list.count()):
            item = self._ui.repository_list.item(i)
            if item:
                linked_ids.add(item.data(Qt.ItemDataRole.UserRole))

        # Find first unlinked repository
        for repo in self._project_data.repositories:
            if repo.id not in linked_ids:
                display = repo.name or repo.id
                item = QListWidgetItem(display)
                item.setData(Qt.ItemDataRole.UserRole, repo.id)
                self._ui.repository_list.addItem(item)
                self._clear_status()
                return

        self._update_status("Inga fler arkiv tillgängliga.")

    def _on_remove_repository(self) -> None:
        """Remove the currently selected repository reference."""
        current = self._ui.repository_list.currentItem()
        if not current:
            self._update_status("Välj ett arkiv att ta bort.")
            return

        row = self._ui.repository_list.row(current)
        self._ui.repository_list.takeItem(row)
        self._clear_status()

    # ------------------------------------------------------------------
    # Private: reference text parsing
    # ------------------------------------------------------------------

    def _on_reference_text_changed(self, text: str) -> None:
        """Handle reference text input changes by parsing and auto-populating fields.

        Strips GEDCOM "ArkivDigital:" prefix before parsing. If parse succeeds,
        auto-populates provider, source type, title, structured fields, and
        arkivreferens.

        Args:
            text: The current reference text input value.
        """
        if self._inhibit_reference_parse:
            return

        text = text.strip()
        if not text:
            return

        # Handle GEDCOM import: strip "ArkivDigital:" prefix
        if text.startswith("ArkivDigital:"):
            text = text[len("ArkivDigital:"):].strip()

        parsed = parse_reference(text)
        if parsed is None:
            return

        # Use guard flag to prevent recursive signal triggers
        self._inhibit_reference_parse = True
        try:
            self._apply_parsed_reference(parsed)
        finally:
            self._inhibit_reference_parse = False

    def _apply_parsed_reference(self, parsed: ParsedReference) -> None:
        """Apply parsed reference data to the form fields.

        Args:
            parsed: The successfully parsed reference data.
        """
        # Set provider
        self._ui.provider_input.setText(parsed.leverantor_name)

        # Look up Leverantör ID from project data
        leverantor_id = ""
        for lev in self._project_data.leverantorer:
            if lev.name == parsed.leverantor_name:
                leverantor_id = lev.id
                break

        # Look up Källtyp and set source type combo
        kalltyp_id = ""
        for kt in self._project_data.kalltyper:
            if kt.name == parsed.kalltyp_name and (
                not leverantor_id or kt.leverantor_id == leverantor_id
            ):
                kalltyp_id = kt.id
                break

        # Map kalltyp_name to internal source type for the combo box
        source_type_key = self._map_kalltyp_to_source_type(parsed.kalltyp_name)
        if source_type_key:
            type_index = self._ui.source_type_combo.findData(source_type_key)
            if type_index >= 0:
                self._ui.source_type_combo.setCurrentIndex(type_index)

        # Format title: use format_source_title for church book fields
        title = parsed.title
        fields = parsed.structured_fields
        if fields.get("parish") or fields.get("series") or fields.get("volume") or fields.get("page"):
            formatted = format_source_title(
                {k: str(v) if v is not None else "" for k, v in fields.items()}
            )
            if formatted:
                title = formatted

        self._ui.title_input.setText(title)

        # Store arkivreferens and IDs for save
        self._pending_arkivreferens = parsed.arkivreferens
        self._pending_leverantor_id = leverantor_id
        self._pending_kalltyp_id = kalltyp_id

        # Fill structured reference fields
        self._fill_structured_fields(fields)

    def _map_kalltyp_to_source_type(self, kalltyp_name: str) -> str:
        """Map a Källtyp name to an internal source type key.

        Args:
            kalltyp_name: The Swedish källtyp name (e.g., "Husförhörslängd").

        Returns:
            The internal source type key (e.g., "church_book"), or empty string
            if no mapping is found.
        """
        # Church book types
        church_book_types = {
            "Husförhörslängd",
            "Födelse- och dopbok",
            "Lysnings- och vigselbok",
            "Död- och begravningsbok",
            "Inflyttningslängd",
            "Utflyttningslängd",
            "In- och Utflyttningslängd",
            "Konfirmationsbok",
            "Mantalslängd",
        }
        if kalltyp_name in church_book_types:
            return "church_book"

        # Census
        if kalltyp_name == "Folkräkning":
            return "census"

        # Database types
        if kalltyp_name in ("Sveriges Dödbok Webb",):
            return "database"

        # If "Övrigt" or unrecognized, default to "other"
        if kalltyp_name == "Övrigt":
            return "other"

        return ""

    def _fill_structured_fields(self, fields: dict) -> None:
        """Fill structured reference input fields from parsed data.

        Args:
            fields: Dictionary of parsed structured field values.
        """
        # Church book fields
        if "parish" in fields:
            self._ui.parish_input.setText(str(fields.get("parish", "") or ""))
        if "county_code" in fields:
            self._ui.county_code_input.setText(str(fields.get("county_code", "") or ""))
        if "series" in fields:
            self._ui.series_input.setText(str(fields.get("series", "") or ""))
        if "volume" in fields:
            self._ui.volume_input.setText(str(fields.get("volume", "") or ""))
        if "years" in fields:
            self._ui.years_input.setText(str(fields.get("years", "") or ""))
        if "image" in fields:
            self._ui.image_input.setText(str(fields.get("image", "") or ""))
        if "page" in fields:
            self._ui.page_input.setText(str(fields.get("page", "") or ""))

        # Database fields
        if "database_name" in fields:
            self._ui.database_name_input.setText(str(fields.get("database_name", "") or ""))
        if "record_id" in fields:
            self._ui.record_id_input.setText(str(fields.get("record_id", "") or ""))

    # ------------------------------------------------------------------
    # Private: save / cancel
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        """Validate and save the source data.

        Validates that title and source_type are set.
        On success, stores the result in saved_source.
        """
        # Validate: title required
        title = self._ui.title_input.text().strip()
        if not title:
            self._update_status("Titel krävs.")
            return

        # Validate: source type required
        source_type = self._ui.source_type_combo.currentData()
        if not source_type:
            self._update_status("Källtyp krävs.")
            return

        # Collect basic fields
        provider = self._ui.provider_input.text().strip()
        reference_text = self._ui.reference_text_input.text().strip()
        provider_ref = self._ui.provider_ref_input.text().strip()
        short_note = self._ui.short_note_input.text().strip()
        free_note = self._ui.free_note_input.toPlainText()

        # Collect structured reference
        structured_reference = self._collect_structured_reference(source_type)

        # Collect media IDs
        media_ids: list[str] = []
        for i in range(self._ui.media_list.count()):
            item = self._ui.media_list.item(i)
            if item:
                media_id = item.data(Qt.ItemDataRole.UserRole)
                if media_id:
                    media_ids.append(media_id)

        # Collect repository refs
        repository_refs: list[RepositoryRef] = []
        for i in range(self._ui.repository_list.count()):
            item = self._ui.repository_list.item(i)
            if item:
                repo_id = item.data(Qt.ItemDataRole.UserRole)
                if repo_id:
                    repository_refs.append(RepositoryRef(repository_id=repo_id))

        # Determine source ID
        source_id = self._source.id if self._source else str(uuid.uuid4())

        # Determine leverantor_id, kalltyp_id, arkivreferens
        leverantor_id = self._pending_leverantor_id
        kalltyp_id = self._pending_kalltyp_id
        arkivreferens = self._pending_arkivreferens

        # Preserve existing values if not overridden by parsing
        if self._source:
            if not leverantor_id:
                leverantor_id = self._source.leverantor_id
            if not kalltyp_id:
                kalltyp_id = self._source.kalltyp_id
            if not arkivreferens:
                arkivreferens = self._source.arkivreferens

        self._saved_source = Source(
            id=source_id,
            provider=provider,
            source_type=source_type,
            title=title,
            reference_text=reference_text,
            provider_ref=provider_ref,
            short_note=short_note,
            free_note=free_note,
            structured_reference=structured_reference,
            media_ids=media_ids,
            repository_refs=repository_refs,
            leverantor_id=leverantor_id,
            kalltyp_id=kalltyp_id,
            arkivreferens=arkivreferens,
        )

        self._clear_status()
        logger.info("Källa sparad: %s", source_id)
        self.save_requested.emit()
        self.close()

    def _on_cancel(self) -> None:
        """Close the editor without saving."""
        self._saved_source = None
        self.cancel_requested.emit()
        self.close()

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    def _collect_structured_reference(self, source_type: str) -> StructuredReference:
        """Collect structured reference fields based on the current source type.

        Args:
            source_type: The internal source type key.

        Returns:
            A StructuredReference with the appropriate fields populated.
        """
        fields: dict[str, str] = {}

        if source_type == "church_book":
            parish = self._ui.parish_input.text().strip()
            if parish:
                fields["parish"] = parish
            county_code = self._ui.county_code_input.text().strip()
            if county_code:
                fields["county_code"] = county_code
            series = self._ui.series_input.text().strip()
            if series:
                fields["series"] = series
            volume = self._ui.volume_input.text().strip()
            if volume:
                fields["volume"] = volume
            years = self._ui.years_input.text().strip()
            if years:
                fields["years"] = years
            image = self._ui.image_input.text().strip()
            if image:
                fields["image"] = image
            page = self._ui.page_input.text().strip()
            if page:
                fields["page"] = page
        elif source_type == "database":
            database_name = self._ui.database_name_input.text().strip()
            if database_name:
                fields["database_name"] = database_name
            record_id = self._ui.record_id_input.text().strip()
            if record_id:
                fields["record_id"] = record_id
        elif source_type == "death_notice":
            newspaper = self._ui.dn_newspaper_input.text().strip()
            if newspaper:
                fields["newspaper"] = newspaper
            pub_date = self._ui.publication_date_input.text().strip()
            if pub_date:
                fields["publication_date"] = pub_date
            page = self._ui.dn_page_input.text().strip()
            if page:
                fields["page"] = page
        elif source_type == "newspaper":
            newspaper = self._ui.np_newspaper_input.text().strip()
            if newspaper:
                fields["newspaper"] = newspaper
            date = self._ui.np_date_input.text().strip()
            if date:
                fields["date"] = date
            page = self._ui.np_page_input.text().strip()
            if page:
                fields["page"] = page
            article_title = self._ui.article_title_input.text().strip()
            if article_title:
                fields["article_title"] = article_title

        return StructuredReference(fields=fields)

    def _clear_form(self) -> None:
        """Reset all form fields to empty/default state."""
        self._inhibit_reference_parse = True
        try:
            self._ui.provider_input.clear()
            self._ui.source_type_combo.setCurrentIndex(0)
            self._ui.title_input.clear()
            self._ui.reference_text_input.clear()
            self._ui.provider_ref_input.clear()
            self._ui.short_note_input.clear()
            self._ui.free_note_input.clear()

            # Clear structured fields
            self._ui.parish_input.clear()
            self._ui.county_code_input.clear()
            self._ui.series_input.clear()
            self._ui.volume_input.clear()
            self._ui.years_input.clear()
            self._ui.image_input.clear()
            self._ui.page_input.clear()
            self._ui.database_name_input.clear()
            self._ui.record_id_input.clear()
            self._ui.dn_newspaper_input.clear()
            self._ui.publication_date_input.clear()
            self._ui.dn_page_input.clear()
            self._ui.np_newspaper_input.clear()
            self._ui.np_date_input.clear()
            self._ui.np_page_input.clear()
            self._ui.article_title_input.clear()

            # Clear lists
            self._ui.media_list.clear()
            self._ui.repository_list.clear()

            # Reset pending parsed data
            self._pending_arkivreferens = ""
            self._pending_leverantor_id = ""
            self._pending_kalltyp_id = ""

            # Hide direct link
            self._direct_link_label.setVisible(False)
        finally:
            self._inhibit_reference_parse = False

    def _update_status(self, message: str) -> None:
        """Update the status label text with an error/info message.

        Args:
            message: The status message to display.
        """
        self._ui.status_label.setText(message)

    def _clear_status(self) -> None:
        """Clear the status label."""
        self._ui.status_label.setText("")

    # ------------------------------------------------------------------
    # Private: direct link
    # ------------------------------------------------------------------

    def _update_direct_link(self) -> None:
        """Update the direct link label based on current source data.

        Generates a direct link if the source's Källtyp has a root_url
        and the source has an arkivreferens. Shows the link as a clickable
        hyperlink or hides the label if conditions are not met.
        """
        if self._source is None:
            self._direct_link_label.setVisible(False)
            return

        try:
            url = generate_direct_link(self._source, self._project_data.kalltyper)
        except Exception:
            logger.warning("Länk kunde inte genereras", exc_info=True)
            self._direct_link_label.setText(
                '<span style="color: red;">Länk kunde inte genereras</span>'
            )
            self._direct_link_label.setVisible(True)
            return

        if url:
            self._direct_link_label.setText(f'<a href="{url}">{url}</a>')
            self._direct_link_label.setVisible(True)
        else:
            self._direct_link_label.setVisible(False)

    def _on_direct_link_clicked(self, url: str) -> None:
        """Handle click on the direct link label.

        Opens the URL in the system default browser via QDesktopServices.

        Args:
            url: The URL string from the link's href attribute.
        """
        try:
            QDesktopServices.openUrl(QUrl(url))
        except Exception:
            logger.warning("Kunde inte öppna URL: %s", url, exc_info=True)
