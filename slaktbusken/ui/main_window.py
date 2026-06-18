"""Main application window for Släktbusken.

Implements the QMainWindow with Swedish-language menus, toolbar,
left/right panel arrangement using QSplitter, and status bar.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QSplitter,
    QStatusBar,
    QToolBar,
    QWidget,
)

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
        self.action_view_family.triggered.connect(
            lambda: self._switch_view(ViewType.FAMILY)
        )

        self.action_view_ancestry = QAction("&Antavla", self)
        self.action_view_ancestry.setToolTip("Visa antavla (uppåt)")
        self.action_view_ancestry.triggered.connect(
            lambda: self._switch_view(ViewType.ANCESTRY)
        )

        self.action_view_descendants = QAction("&Ättlingar", self)
        self.action_view_descendants.setToolTip("Visa ättlingar (nedåt)")
        self.action_view_descendants.triggered.connect(
            lambda: self._switch_view(ViewType.DESCENDANTS)
        )

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

        # Verktyg (Tools)
        self.action_relationship = QAction("&Släktskapsberäknare...", self)
        self.action_relationship.setToolTip("Beräkna släktskap mellan två personer")
        self.action_relationship.triggered.connect(self._app.show_relationship_calculator)

        self.action_settings = QAction("&Inställningar...", self)
        self.action_settings.setToolTip("Öppna inställningar")
        self.action_settings.triggered.connect(self._app.show_settings)

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
        self.menu_edit.addAction(self.action_place_editor)
        self.menu_edit.addAction(self.action_place_translation_editor)

        # Person
        self.menu_person = menu_bar.addMenu("&Person")
        self.menu_person.addAction(self.action_add_person)

        # Visa (View)
        self.menu_view = menu_bar.addMenu("&Visa")
        self.menu_view.addAction(self.action_view_family)
        self.menu_view.addAction(self.action_view_ancestry)
        self.menu_view.addAction(self.action_view_descendants)

        # Verktyg (Tools)
        self.menu_tools = menu_bar.addMenu("V&erktyg")
        self.menu_tools.addAction(self.action_relationship)
        self.menu_tools.addAction(self.action_settings)

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
        self.addToolBar(self.toolbar)

        self.toolbar.addAction(self.action_new)
        self.toolbar.addAction(self.action_open)
        self.toolbar.addAction(self.action_save)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.action_import)
        self.toolbar.addAction(self.action_export)

    # ------------------------------------------------------------------
    # Central Widget
    # ------------------------------------------------------------------

    def _setup_central_widget(self) -> None:
        """Create left/right panel splitter with PersonListPanel and DiagramPanel."""
        from slaktbusken.ui.diagram_panel import DiagramPanel
        from slaktbusken.ui.person_list_panel import PersonListPanel

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Left panel: PersonListPanel
        self.person_list_panel = PersonListPanel(self._app)
        self.left_panel = self.person_list_panel

        # Right panel: DiagramPanel
        self.diagram_panel = DiagramPanel(self)
        self.diagram_panel.switch_view(ViewType.FAMILY)
        self.right_panel = self.diagram_panel

        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)

        self.setCentralWidget(self.splitter)

    # ------------------------------------------------------------------
    # Status Bar
    # ------------------------------------------------------------------

    def _setup_status_bar(self) -> None:
        """Create status bar with project status label."""
        self._status_label = QLabel("Inget projekt öppet")
        self.statusBar().addPermanentWidget(self._status_label)

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
        self.action_place_editor.setEnabled(project_open)
        self.action_place_translation_editor.setEnabled(project_open)
        self.action_view_family.setEnabled(project_open)
        self.action_view_ancestry.setEnabled(project_open)
        self.action_view_descendants.setEnabled(project_open)

    def _switch_view(self, view_type: ViewType) -> None:
        """Switch the diagram panel view type.

        Args:
            view_type: The view to switch to.
        """
        self._current_view = view_type
        self.diagram_panel.switch_view(view_type)
        view_names = {
            ViewType.FAMILY: "Familjevy",
            ViewType.ANCESTRY: "Antavla",
            ViewType.DESCENDANTS: "Ättlingar",
        }
        self.statusBar().showMessage(f"Växlade till {view_names[view_type]}", 3000)

    def _show_about(self) -> None:
        """Show the About dialog."""
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.about(
            self,
            "Om Släktbusken",
            "Släktbusken v0.1.0\n\n"
            "Ett skrivbordsverktyg för svensk släktforskning.\n\n"
            "Byggt med Python och PySide6.",
        )

    def closeEvent(self, event) -> None:
        """Handle window close — confirm save if project is dirty.

        Args:
            event: The close event.
        """
        if self._app.confirm_close():
            event.accept()
        else:
            event.ignore()
