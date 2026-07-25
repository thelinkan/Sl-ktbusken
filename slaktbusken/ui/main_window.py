"""Main application window for Släktbusken.

Implements the QMainWindow with Swedish-language menus, toolbar,
left/right panel arrangement using QSplitter, and status bar.
"""

from __future__ import annotations

from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QToolBar,
    QWidget,
)

from slaktbusken.ui.widgets.progress_overlay import ProgressOverlay

if TYPE_CHECKING:
    from slaktbusken.app import Application


class ViewType(Enum):
    """Diagram view types for the main panel."""

    FAMILY = auto()
    ANCESTRY = auto()
    DESCENDANTS = auto()


class MainWindow(QMainWindow):
    """Main application window for Släktbusken.

    Provides the full UI shell: menu bar (Arkiv, Redigera, Visa, Verktyg,
    Hjälp), toolbar with common actions, left/right panel splitter, and
    status bar showing project state. All UI text is in Swedish.

    Args:
        app: The Application instance that provides action callbacks.
    """

    def __init__(self, app: Application) -> None:
        """Initialise the main window.

        Args:
            app: Application instance for action callbacks.
        """
        super().__init__()
        self._app = app
        self._current_view = ViewType.FAMILY

        self.setWindowTitle("Släktbusken")
        self.resize(1200, 800)

        self._setup_actions()
        self._setup_menu_bar()
        self._setup_toolbar()
        self._setup_central_widget()
        self._setup_status_bar()
        self._progress_overlay = ProgressOverlay(self)
        self._update_project_actions(project_open=False)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _setup_actions(self) -> None:
        """Create all QActions used in menus and toolbar."""
        # Arkiv (File)
        self.action_new = QAction("&Nytt projekt", self)
        self.action_new.setShortcut(QKeySequence("Ctrl+N"))
        self.action_new.setToolTip("Skapa ett nytt projekt")
        self.action_new.triggered.connect(self._app.new_project)

        self.action_open = QAction("&Öppna projekt...", self)
        self.action_open.setShortcut(QKeySequence("Ctrl+O"))
        self.action_open.setToolTip("Öppna ett befintligt projekt")
        self.action_open.triggered.connect(self._app.open_project)

        self.action_save = QAction("&Spara", self)
        self.action_save.setShortcut(QKeySequence("Ctrl+S"))
        self.action_save.setToolTip("Spara aktuellt projekt")
        self.action_save.triggered.connect(self._app.save_project)

        self.action_import = QAction("&Importera GEDCOM...", self)
        self.action_import.setShortcut(QKeySequence("Ctrl+I"))
        self.action_import.setToolTip("Importera en GEDCOM-fil")
        self.action_import.triggered.connect(self._app.import_gedcom)

        self.action_export = QAction("&Exportera GEDCOM...", self)
        self.action_export.setShortcut(QKeySequence("Ctrl+E"))
        self.action_export.setToolTip("Exportera till GEDCOM-fil")
        self.action_export.triggered.connect(self._app.export_gedcom)

        self.action_close = QAction("Stäng pro&jekt", self)
        self.action_close.setShortcut(QKeySequence("Ctrl+W"))
        self.action_close.setToolTip("Stäng aktuellt projekt")
        self.action_close.triggered.connect(self._app.close_project)

        self.action_exit = QAction("A&vsluta", self)
        self.action_exit.setShortcut(QKeySequence("Ctrl+Q"))
        self.action_exit.setToolTip("Avsluta Släktbusken")
        self.action_exit.triggered.connect(self.close)

        # Visa (View)
        self.action_view_family = QAction("&Familjevy", self)
        self.action_view_family.setToolTip("Visa familjevy")
        self.action_view_family.setCheckable(True)
        self.action_view_family.setChecked(True)  # Default view
        self.action_view_family.triggered.connect(
            lambda: self._switch_view(ViewType.FAMILY)
        )

        self.action_view_ancestry = QAction("&Antavla", self)
        self.action_view_ancestry.setToolTip("Visa antavla (uppåt)")
        self.action_view_ancestry.setCheckable(True)
        self.action_view_ancestry.triggered.connect(
            lambda: self._switch_view(ViewType.ANCESTRY)
        )

        self.action_view_descendants = QAction("&Ättlingar", self)
        self.action_view_descendants.setToolTip("Visa ättlingar (nedåt)")
        self.action_view_descendants.setCheckable(True)
        self.action_view_descendants.triggered.connect(
            lambda: self._switch_view(ViewType.DESCENDANTS)
        )

        # Group view actions so only one can be checked at a time
        self._view_action_group = QActionGroup(self)
        self._view_action_group.setExclusive(True)
        self._view_action_group.addAction(self.action_view_family)
        self._view_action_group.addAction(self.action_view_ancestry)
        self._view_action_group.addAction(self.action_view_descendants)

        # Redigera (Edit)
        self.action_source_editor = QAction("&Källredigerare...", self)
        self.action_source_editor.setToolTip("Visa, redigera och hantera källor")
        self.action_source_editor.triggered.connect(self._app.show_source_editor)

        self.action_source_translation_editor = QAction(
            "Käll&översättningar...", self
        )
        self.action_source_translation_editor.setToolTip(
            "Redigera GEDCOM-till-App_JSON källöversättningar"
        )
        self.action_source_translation_editor.triggered.connect(
            self._app.show_source_translation_editor
        )

        self.action_provider_editor = QAction("Käll-leverantörer...", self)
        self.action_provider_editor.setToolTip(
            "Hantera käll-leverantörer och källtyper"
        )
        self.action_provider_editor.triggered.connect(
            self._app.show_provider_editor
        )

        self.action_place_editor = QAction("&Platsredigerare...", self)
        self.action_place_editor.setToolTip(
            "Visa, redigera och hantera platser"
        )
        self.action_place_editor.triggered.connect(self._app.show_place_editor)

        self.action_place_translation_editor = QAction(
            "Plats&översättningar...", self
        )
        self.action_place_translation_editor.setToolTip(
            "Redigera GEDCOM-till-App_JSON platsöversättningar"
        )
        self.action_place_translation_editor.triggered.connect(
            self._app.show_place_translation_editor
        )

        # Person
        self.action_add_person = QAction("&Lägg till person", self)
        self.action_add_person.setToolTip("Skapa en ny person utan kopplingar")
        self.action_add_person.triggered.connect(self._app.add_standalone_person)

        # DNA
        self.action_dna_editor = QAction("&DNA och Kluster", self)
        self.action_dna_editor.setToolTip(
            "Hantera DNA-företag, profiler, matchningar, segment, kluster och trianguleringar"
        )
        self.action_dna_editor.triggered.connect(self._app.show_dna_editor)

        # Verktyg (Tools)
        self.action_relationship = QAction("&Släktskapsberäknare...", self)
        self.action_relationship.setToolTip("Beräkna släktskap mellan två personer")
        self.action_relationship.triggered.connect(self._app.show_relationship_calculator)

        self.action_settings = QAction("&Inställningar...", self)
        self.action_settings.setToolTip("Öppna inställningar")
        self.action_settings.triggered.connect(self._app.show_settings)

        # Karta (Map)
        self.action_map_all_events = QAction("Alla händelser", self)
        self.action_map_all_events.setToolTip("Visa alla händelser på karta")
        self.action_map_all_events.triggered.connect(self._app.show_all_events_map)

        # Visa huvudperson
        self.action_show_main_person = QAction("Visa &huvudperson", self)
        self.action_show_main_person.setShortcut(QKeySequence("H"))
        self.action_show_main_person.setToolTip(
            "Navigera till huvudpersonen i aktuell vy"
        )
        self.action_show_main_person.triggered.connect(
            self._app.show_main_person
        )

        # Visa/dölj personlista
        self.action_toggle_person_list = QAction("&Personlista", self)
        self.action_toggle_person_list.setShortcut(QKeySequence("F9"))
        self.action_toggle_person_list.setCheckable(True)
        self.action_toggle_person_list.setChecked(True)
        self.action_toggle_person_list.setToolTip("Visa eller dölj personlistan (F9)")
        self.action_toggle_person_list.toggled.connect(self._toggle_person_list)

        # Visa/dölj detaljerad vy
        self.action_toggle_detail_panel = QAction("&Detaljerad vy", self)
        self.action_toggle_detail_panel.setShortcut(QKeySequence("F10"))
        self.action_toggle_detail_panel.setCheckable(True)
        self.action_toggle_detail_panel.setChecked(False)
        self.action_toggle_detail_panel.setToolTip("Visa eller dölj detaljerad vy (F10)")
        self.action_toggle_detail_panel.toggled.connect(self._toggle_detail_panel)

        self.action_goto_selected_person = QAction("M&arkerad person", self)
        self.action_goto_selected_person.setShortcut(QKeySequence("A"))
        self.action_goto_selected_person.setToolTip(
            "Gör markerad person till aktiv person i aktuell vy"
        )
        self.action_goto_selected_person.triggered.connect(
            self._activate_selected_person
        )

    # ------------------------------------------------------------------
    # Menu Bar
    # ------------------------------------------------------------------

    def _setup_menu_bar(self) -> None:
        """Build the Swedish-language menu bar."""
        menu_bar = self.menuBar()

        # Arkiv (File)
        self.menu_file = menu_bar.addMenu("&Arkiv")
        self.menu_file.addAction(self.action_new)
        self.menu_file.addAction(self.action_open)
        self.menu_file.addAction(self.action_save)
        self.menu_recent_projects = self.menu_file.addMenu("Senaste projekt")
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.action_import)
        self.menu_file.addAction(self.action_export)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.action_close)
        self.menu_file.addAction(self.action_exit)

        # Redigera (Edit)
        self.menu_edit = menu_bar.addMenu("&Redigera")
        self.menu_edit.addAction(self.action_source_editor)
        self.menu_edit.addAction(self.action_source_translation_editor)
        self.menu_edit.addAction(self.action_provider_editor)
        self.menu_edit.addAction(self.action_place_editor)
        self.menu_edit.addAction(self.action_place_translation_editor)
        self.menu_edit.addSeparator()
        self.menu_edit.addAction(self.action_dna_editor)

        # Person
        self.menu_person = menu_bar.addMenu("&Person")
        self.menu_person.addAction(self.action_add_person)
        self.menu_person.addSeparator()
        self.menu_goto = self.menu_person.addMenu("Gå till")
        self.menu_goto.addAction(self.action_show_main_person)
        self.menu_goto.addAction(self.action_goto_selected_person)

        # Visa (View)
        self.menu_view = menu_bar.addMenu("&Visa")
        self.menu_view.addAction(self.action_toggle_person_list)
        self.menu_view.addAction(self.action_toggle_detail_panel)
        self.menu_view.addSeparator()
        self.menu_view.addAction(self.action_view_family)
        self.menu_view.addAction(self.action_view_ancestry)
        self.menu_view.addAction(self.action_view_descendants)

        # Verktyg (Tools)
        self.menu_tools = menu_bar.addMenu("V&erktyg")
        self.menu_tools.addAction(self.action_relationship)
        self.menu_tools.addAction(self.action_settings)

        # Karta (Map)
        self.menu_map = menu_bar.addMenu("&Karta")
        self.menu_map.addAction(self.action_map_all_events)

        # Rapporter (Reports)
        from slaktbusken.ui.report_menu import ReportMenuBuilder

        self._report_menu_builder = ReportMenuBuilder()
        self._report_menu_builder.build(menu_bar, self._app)
        self._report_menu_builder.action_ansedel.triggered.connect(
            self._generate_ansedel
        )
        self._report_menu_builder.action_kallrapport.triggered.connect(
            self._generate_kallrapport
        )
        self._report_menu_builder.action_geographic.triggered.connect(
            self._generate_geographic
        )
        self._report_menu_builder.action_media.triggered.connect(
            self._generate_media
        )

        # Hjälp (Help)
        self.menu_help = menu_bar.addMenu("&Hjälp")
        action_about = QAction("&Om Släktbusken", self)
        action_about.triggered.connect(self._show_about)
        self.menu_help.addAction(action_about)

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------

    def _setup_toolbar(self) -> None:
        """Create toolbar with common actions."""
        self.toolbar = QToolBar("Huvudverktyg", self)
        self.toolbar.setObjectName("huvudverktyg")
        self.toolbar.setStyleSheet("""
            QToolButton:checked {
                border: 1px solid palette(mid);
                border-radius: 2px;
            }
        """)
        self.addToolBar(self.toolbar)

        self.toolbar.addAction(self.action_new)
        self.toolbar.addAction(self.action_open)
        self.toolbar.addAction(self.action_save)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.action_view_family)
        self.toolbar.addAction(self.action_view_ancestry)
        self.toolbar.addAction(self.action_view_descendants)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.action_show_main_person)

    # ------------------------------------------------------------------
    # Central Widget
    # ------------------------------------------------------------------

    def _setup_central_widget(self) -> None:
        """Create left/center/right panel splitter with PersonListPanel, DiagramPanel, and DetailPanel."""
        from slaktbusken.ui.diagram_panel import DiagramPanel
        from slaktbusken.ui.person_detail_panel import PersonDetailPanel
        from slaktbusken.ui.person_list_panel import PersonListPanel

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Left panel: PersonListPanel
        self.person_list_panel = PersonListPanel(self._app)
        self.person_list_panel.setMinimumWidth(250)
        self.left_panel = self.person_list_panel

        # Center panel: DiagramPanel
        self.diagram_panel = DiagramPanel(self)
        self.diagram_panel.switch_view(ViewType.FAMILY)

        # Right panel: PersonDetailPanel (hidden on startup)
        self.detail_panel = PersonDetailPanel(self._app)
        self.detail_panel.setMinimumWidth(250)
        self.detail_panel.hide()

        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.diagram_panel)
        self.splitter.addWidget(self.detail_panel)

        # Set initial sizes: ~40% for person list, 60% for diagram, 0% for detail (hidden)
        total = max(self.width(), 800)
        left_width = int(total * 0.4)
        self.splitter.setSizes([left_width, total - left_width, 0])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)

        self.setCentralWidget(self.splitter)

        # Store default panel widths for restore
        self._person_list_saved_width = left_width
        self._detail_panel_saved_width = 300

        # Connect diagram person activation to person list sync
        self.diagram_panel.person_activated.connect(
            self.person_list_panel.select_person_from_diagram
        )

    def _toggle_person_list(self, visible: bool) -> None:
        """Show or hide the person list panel by collapsing the splitter.

        Args:
            visible: True to show, False to hide.
        """
        if visible:
            current_sizes = self.splitter.sizes()
            total = sum(current_sizes)
            left_width = self._person_list_saved_width
            self.splitter.setSizes([left_width, total - left_width, current_sizes[2] if len(current_sizes) > 2 else 0])
            self.left_panel.show()
        else:
            current_sizes = self.splitter.sizes()
            if current_sizes[0] > 0:
                self._person_list_saved_width = current_sizes[0]
            self.left_panel.hide()

    def _toggle_detail_panel(self, visible: bool) -> None:
        """Show or hide the detail panel on the right side.

        Args:
            visible: True to show, False to hide.
        """
        if visible:
            current_sizes = self.splitter.sizes()
            total = sum(current_sizes)
            detail_width = self._detail_panel_saved_width
            # Shrink the center panel to make room
            center_width = current_sizes[1] - detail_width
            if center_width < 200:
                center_width = 200
                detail_width = total - current_sizes[0] - center_width
            self.splitter.setSizes([current_sizes[0], center_width, detail_width])
            self.detail_panel.show()
            # Refresh detail panel with currently selected person from list
            selected_id = self.person_list_panel.get_selected_person_id()
            if selected_id:
                self.detail_panel.set_person(selected_id)
        else:
            current_sizes = self.splitter.sizes()
            if len(current_sizes) > 2 and current_sizes[2] > 0:
                self._detail_panel_saved_width = current_sizes[2]
            self.detail_panel.hide()

    def _on_person_activated_for_detail(self, person_id: str) -> None:
        """Update the detail panel when a person is selected.

        Always updates the panel content regardless of visibility, so it's
        ready when toggled on.

        Args:
            person_id: The ID of the selected person.
        """
        self.detail_panel.set_person(person_id)

    # ------------------------------------------------------------------
    # Status Bar
    # ------------------------------------------------------------------

    def _setup_status_bar(self) -> None:
        """Create status bar with person count and project status (both permanent)."""
        self._person_count_label = QLabel("")
        self.statusBar().addPermanentWidget(self._person_count_label, 1)

        self._status_label = QLabel("Inget projekt öppet")
        self.statusBar().addPermanentWidget(self._status_label, 0)

    def update_person_count(self, total: int, filtered: int | None = None) -> None:
        """Update the person count display in the status bar.

        Args:
            total: Total number of persons in the project.
            filtered: Number of persons in the active filter, or None if not filtering.
        """
        if filtered is not None:
            self._person_count_label.setText(f"Antal personer: {total} ({filtered})")
        else:
            self._person_count_label.setText(f"Antal personer: {total}")

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def update_project_status(self, project_name: str | None, dirty: bool = False) -> None:
        """Update the status bar to reflect the current project state.

        Args:
            project_name: Name of the open project, or None if no project is open.
            dirty: Whether the project has unsaved changes.
        """
        if project_name is None:
            self._status_label.setText("Inget projekt öppet")
            self._update_project_actions(project_open=False)
        else:
            marker = " *" if dirty else ""
            self._status_label.setText(f"Projekt: {project_name}{marker}")
            self._update_project_actions(project_open=True)

    def show_progress(self, message: str) -> None:
        """Show the progress overlay with the given message.

        Args:
            message: The message to display on the overlay.
        """
        self._progress_overlay.show_with_message(message)

    def hide_progress(self) -> None:
        """Hide the progress overlay."""
        self._progress_overlay.hide()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _update_project_actions(self, project_open: bool) -> None:
        """Enable/disable actions based on whether a project is open.

        Args:
            project_open: True if a project is currently open.
        """
        self.action_save.setEnabled(project_open)
        self.action_import.setEnabled(project_open)
        self.action_export.setEnabled(project_open)
        self.action_close.setEnabled(project_open)
        self.action_relationship.setEnabled(project_open)
        self.action_source_editor.setEnabled(project_open)
        self.action_source_translation_editor.setEnabled(project_open)
        self.action_provider_editor.setEnabled(project_open)
        self.action_place_editor.setEnabled(project_open)
        self.action_place_translation_editor.setEnabled(project_open)
        self.action_dna_editor.setEnabled(project_open)
        self.action_view_family.setEnabled(project_open)
        self.action_view_ancestry.setEnabled(project_open)
        self.action_view_descendants.setEnabled(project_open)
        self.action_show_main_person.setEnabled(project_open)
        self.action_goto_selected_person.setEnabled(project_open)
        self.action_map_all_events.setEnabled(project_open)

        if hasattr(self, '_report_menu_builder'):
            self._report_menu_builder.update_project_state(project_open)

    def _activate_selected_person(self) -> None:
        """Make the currently selected (marked) person the active person."""
        selected_id = (
            self.diagram_panel._family_view.selected_person_id
            or self.diagram_panel._ancestry_view.selected_person_id
            or self.diagram_panel._descendants_view.selected_person_id
        )
        if selected_id:
            self.diagram_panel.person_activated.emit(selected_id)
            self.diagram_panel.set_active_person(selected_id)

    def _switch_view(self, view_type: ViewType) -> None:
        """Switch the diagram panel view type.

        Args:
            view_type: The view to switch to.
        """
        self._current_view = view_type
        self.diagram_panel.switch_view(view_type)

        # Update checked state on view actions
        action_map = {
            ViewType.FAMILY: self.action_view_family,
            ViewType.ANCESTRY: self.action_view_ancestry,
            ViewType.DESCENDANTS: self.action_view_descendants,
        }
        target_action = action_map.get(view_type)
        if target_action and not target_action.isChecked():
            target_action.setChecked(True)

        view_names = {
            ViewType.FAMILY: "Familjevy",
            ViewType.ANCESTRY: "Antavla",
            ViewType.DESCENDANTS: "Ättlingar",
        }
        self.statusBar().showMessage(f"Växlade till {view_names[view_type]}", 3000)

    def _generate_ansedel(self) -> None:
        """Generate and display the Ansedel report for the active person."""
        if self._app.project_service.project_path is None:
            return

        if self.diagram_panel.active_person_id is None:
            QMessageBox.warning(
                self,
                "Ansedel",
                "En person måste vara vald i diagrammet",
            )
            return

        from slaktbusken.reports.generator import ReportGeneratorService
        from slaktbusken.ui.dialogs.report_preview import ReportPreviewDialog

        data = self._app.project_service.data
        project_folder = self._app.project_service.project_path.parent
        person_id = self.diagram_panel.active_person_id

        service = ReportGeneratorService()
        content = service.generate_ansedel(data, person_id, project_folder)

        settings = self._app.project_service.settings
        dlg = ReportPreviewDialog(content, settings, parent=self)
        dlg.exec()

    def _generate_geographic(self) -> None:
        """Generate and display the Geographic Consistency report."""
        if self._app.project_service.project_path is None:
            return

        from slaktbusken.reports.generator import ReportGeneratorService
        from slaktbusken.ui.dialogs.report_preview import ReportPreviewDialog

        data = self._app.project_service.data

        service = ReportGeneratorService()
        content = service.generate_geographic_consistency(data)

        settings = self._app.project_service.settings
        dlg = ReportPreviewDialog(content, settings, parent=self)
        dlg.exec()

    def _generate_kallrapport(self) -> None:
        """Generate and display the Källrapport (Source Report)."""
        if self._app.project_service.project_path is None:
            return

        from slaktbusken.reports.generator import ReportGeneratorService
        from slaktbusken.ui.dialogs.report_preview import ReportPreviewDialog

        data = self._app.project_service.data

        service = ReportGeneratorService()
        content = service.generate_kallrapport(data)

        settings = self._app.project_service.settings
        dlg = ReportPreviewDialog(content, settings, parent=self)
        dlg.exec()

    def _generate_media(self) -> None:
        """Generate and display the Media Consistency report."""
        if self._app.project_service.project_path is None:
            return

        from slaktbusken.reports.generator import ReportGeneratorService
        from slaktbusken.ui.dialogs.report_preview import ReportPreviewDialog

        data = self._app.project_service.data
        project_folder = self._app.project_service.project_path.parent

        service = ReportGeneratorService()
        content = service.generate_media_consistency(data, project_folder)

        settings = self._app.project_service.settings
        dlg = ReportPreviewDialog(content, settings, parent=self)
        dlg.exec()

    def _show_about(self) -> None:
        """Show the About dialog."""
        QMessageBox.about(
            self,
            "Om Släktbusken",
            "<p>Släktbusken v0.1.0 (beta)</p>"
            "<p>Ett skrivbordsverktyg för svensk släktforskning.</p>"
            "<p>Byggt med Python och PySide6.</p>"
            "<p>Gjort av Linkan, med hjälp av Specdriven AI (KIRO)</p>"
            '<p><a href="https://github.com/thelinkan/Sl-ktbusken">'
            "https://github.com/thelinkan/Sl-ktbusken</a></p>",
        )

    def refresh_recent_projects_menu(self, recent_projects: list[str]) -> None:
        """Rebuild the 'Senaste projekt' submenu with current entries.

        Each entry shows the project filename (stem) and full path.
        Missing files are displayed as disabled with a tooltip.

        Args:
            recent_projects: List of project file paths, most recent first.
        """
        self.menu_recent_projects.clear()

        if not recent_projects:
            no_action = self.menu_recent_projects.addAction("(inga senaste projekt)")
            no_action.setEnabled(False)
            return

        for project_path_str in recent_projects:
            p = Path(project_path_str)
            # Show stem (filename without extension) and full path
            label = f"{p.stem}  —  {project_path_str}"
            action = self.menu_recent_projects.addAction(label)

            if p.exists():
                # Connect to open the project
                action.triggered.connect(
                    lambda checked=False, path=project_path_str: self._app.open_recent_project(path)
                )
            else:
                action.setEnabled(False)
                action.setToolTip("Filen hittades inte")

    def resizeEvent(self, event) -> None:
        """Constrain PersonListPanel max width to 50% of window width on resize.

        Args:
            event: The resize event.
        """
        super().resizeEvent(event)
        max_left_width = self.width() // 2
        self.person_list_panel.setMaximumWidth(max_left_width)

    def closeEvent(self, event) -> None:
        """Handle window close — confirm save if project is dirty.

        Args:
            event: The close event.
        """
        if self._app.confirm_close():
            event.accept()
        else:
            event.ignore()
