"""Application shell — thin wiring layer between services and UI.

Instantiates all services, creates the main window, and forwards
UI events (menu actions) to the appropriate service methods.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from slaktbusken.relationship.calculator import RelationshipCalculator
from slaktbusken.services.export_service import ExportService
from slaktbusken.services.import_service import ImportService
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.report_service import ReportService
from slaktbusken.services.translation_service import TranslationService
from slaktbusken.services.validation_service import ValidationService
from slaktbusken.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


class Application:
    """Application shell that wires services to the UI.

    Creates all service instances, instantiates the main window, and
    provides callback methods invoked by menu/toolbar actions. Acts as
    the single coordination point between the UI layer and business logic.
    """

    def __init__(self) -> None:
        """Initialise services and create the main window."""
        # Core services
        self.project_service = ProjectService()
        self.validation_service = ValidationService()
        self.report_service = ReportService()
        self.import_service = ImportService(
            self.validation_service, self.report_service
        )
        self.export_service = ExportService(self.report_service)
        self.translation_service = TranslationService()

        # Main window (receives self for action callbacks)
        self.main_window = MainWindow(self)

    # ------------------------------------------------------------------
    # Action callbacks (invoked by MainWindow actions)
    # ------------------------------------------------------------------

    def new_project(self) -> None:
        """Create a new project via the New Project dialog."""
        if not self._confirm_discard_changes():
            return

        from slaktbusken.ui.dialogs.new_project_dialog import NewProjectDialog

        dialog = NewProjectDialog(parent=self.main_window)
        if dialog.exec() != NewProjectDialog.DialogCode.Accepted:
            return

        try:
            self.project_service.create_project(
                dialog.project_name, dialog.project_location
            )
            self._update_status()
            self._update_diagram_panel()
            self.main_window.statusBar().showMessage(
                f"Projekt '{dialog.project_name}' skapat", 5000
            )
        except OSError as e:
            QMessageBox.critical(
                self.main_window,
                "Fel",
                f"Kunde inte skapa projektet:\n{e}",
            )

    def open_project(self) -> None:
        """Open an existing project file."""
        if not self._confirm_discard_changes():
            return

        path, _ = QFileDialog.getOpenFileName(
            self.main_window,
            "Öppna projekt",
            "",
            "Släktbuske-filer (*.json.gz);;Alla filer (*)",
        )
        if not path:
            return

        try:
            self.project_service.open_project(Path(path))
            self._update_status()
            self._update_diagram_panel()
            self.main_window.statusBar().showMessage("Projekt öppnat", 5000)
        except FileNotFoundError:
            QMessageBox.critical(
                self.main_window,
                "Fel",
                "Filen hittades inte.",
            )
        except Exception as e:
            QMessageBox.critical(
                self.main_window,
                "Fel",
                f"Kunde inte öppna projektet:\n{e}",
            )

    def save_project(self) -> None:
        """Save the current project."""
        try:
            self.project_service.save_project()
            self._update_status()
            self.main_window.statusBar().showMessage("Projekt sparat", 5000)
        except Exception as e:
            QMessageBox.critical(
                self.main_window,
                "Fel",
                f"Kunde inte spara projektet:\n{e}",
            )

    def import_gedcom(self) -> None:
        """Import a GEDCOM file into the current project."""
        path, _ = QFileDialog.getOpenFileName(
            self.main_window,
            "Importera GEDCOM",
            "",
            "GEDCOM-filer (*.ged);;Alla filer (*)",
        )
        if not path:
            return

        try:
            project_data = self.project_service.data
            project_path = self.project_service.project_path
            if project_path is None:
                return

            result = self.import_service.run(
                project_data, Path(path), project_path.parent
            )
            summary = self.import_service.format_result(result)
            self._update_status()
            self._update_diagram_panel()

            QMessageBox.information(
                self.main_window,
                "Import slutförd",
                summary,
            )
        except FileNotFoundError as e:
            QMessageBox.critical(
                self.main_window,
                "Fel",
                str(e),
            )
        except Exception as e:
            QMessageBox.critical(
                self.main_window,
                "Importfel",
                f"Kunde inte importera GEDCOM-filen:\n{e}",
            )

    def export_gedcom(self) -> None:
        """Export the current project to a GEDCOM file."""
        path, _ = QFileDialog.getSaveFileName(
            self.main_window,
            "Exportera GEDCOM",
            "",
            "GEDCOM-filer (*.ged);;Alla filer (*)",
        )
        if not path:
            return

        try:
            project_data = self.project_service.data
            project_path = self.project_service.project_path
            if project_path is None:
                return

            result = self.export_service.run(
                project_data, Path(path), project_path.parent
            )
            summary = self.report_service.format_export_result(result)

            QMessageBox.information(
                self.main_window,
                "Export slutförd",
                summary,
            )
        except Exception as e:
            QMessageBox.critical(
                self.main_window,
                "Exportfel",
                f"Kunde inte exportera GEDCOM-filen:\n{e}",
            )

    def close_project(self) -> None:
        """Close the current project after confirming unsaved changes."""
        if not self._confirm_discard_changes():
            return

        self.project_service.close_project()
        self._update_status()
        self._update_diagram_panel()
        self.main_window.statusBar().showMessage("Projekt stängt", 5000)

    def show_relationship_calculator(self) -> None:
        """Open the relationship calculator dialog.

        Creates and displays the RelationshipDialog, passing the current
        project data for relationship computation.
        """
        from slaktbusken.ui.dialogs.relationship_dialog import RelationshipDialog

        dialog = RelationshipDialog(
            data=self.project_service.data,
            parent=self.main_window,
        )
        dialog.exec()

    def show_settings(self) -> None:
        """Open the settings dialog for person box config and diagram depth.

        Shows the SettingsDialog populated with current project settings.
        On accept: saves settings to file, applies config to the diagram
        panel, and marks the project as dirty.
        """
        from slaktbusken.ui.dialogs.settings_dialog import SettingsDialog
        from slaktbusken.persistence.settings_io import (
            DiagramSettings,
            PersonBoxConfig,
            write_settings,
        )

        settings = self.project_service.settings
        if settings is None:
            return

        dialog = SettingsDialog(
            person_box_config=settings.person_box_config,
            diagram_settings=settings.diagram_settings,
            parent=self.main_window,
        )

        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return

        # Retrieve updated values from the dialog.
        new_person_box_config = dialog.person_box_config
        new_diagram_settings = dialog.diagram_settings

        # Update the in-memory settings.
        settings.person_box_config = new_person_box_config
        settings.diagram_settings = new_diagram_settings

        # Persist settings to the project folder.
        project_path = self.project_service.project_path
        if project_path is not None:
            settings_file = project_path.parent / "settings.json"
            write_settings(settings, settings_file)

        # Apply to diagram panel for immediate re-render.
        panel = self.main_window.diagram_panel
        panel.set_person_box_config(new_person_box_config)
        panel.set_diagram_settings(new_diagram_settings)

        # Mark project as dirty.
        self.project_service._dirty = True
        self._update_status()

    def confirm_close(self) -> bool:
        """Check if the application can close (confirm unsaved changes).

        Returns:
            True if the application may close, False to cancel.
        """
        return self._confirm_discard_changes()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _confirm_discard_changes(self) -> bool:
        """Ask the user to save if the project has unsaved changes.

        Returns:
            True if it's safe to proceed (saved, discarded, or no changes).
            False if the user cancelled.
        """
        if not self.project_service.is_dirty:
            return True

        reply = QMessageBox.question(
            self.main_window,
            "Osparade ändringar",
            "Projektet har osparade ändringar.\nVill du spara innan du fortsätter?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )

        if reply == QMessageBox.StandardButton.Save:
            self.save_project()
            return True
        elif reply == QMessageBox.StandardButton.Discard:
            return True
        else:
            return False

    def _update_status(self) -> None:
        """Update the main window status bar with current project state."""
        project_path = self.project_service.project_path
        if project_path is not None:
            project_name = project_path.stem
            self.main_window.update_project_status(
                project_name, self.project_service.is_dirty
            )
        else:
            self.main_window.update_project_status(None)

    def _update_diagram_panel(self) -> None:
        """Uppdatera diagrampanelen med aktuell projektdata och inställningar.

        Sätter projektdata, personbox-konfiguration och aktiv person
        på DiagramPanel så att familjediagrammet renderas korrekt.
        """
        panel = self.main_window.diagram_panel
        settings = self.project_service.settings

        if self.project_service.project_path is not None:
            project_data = self.project_service.data
            panel.set_project_data(project_data)

            if settings:
                panel.set_person_box_config(settings.person_box_config)

            # Set active person to main_person_id if available
            main_person = project_data.project.main_person_id
            if main_person:
                panel.set_active_person(main_person)
            elif project_data.persons:
                panel.set_active_person(project_data.persons[0].id)
        else:
            panel.set_project_data(None)



