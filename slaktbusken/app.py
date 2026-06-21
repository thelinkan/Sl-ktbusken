"""Application shell — thin wiring layer between services and UI.

Instantiates all services, creates the main window, and forwards
UI events (menu actions) to the appropriate service methods.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox, QVBoxLayout

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

        # Application-level settings service
        from slaktbusken.persistence.app_settings_io import AppSettingsService

        self.app_settings_service = AppSettingsService()
        self.app_settings_service.load()

        # Main window (receives self for action callbacks)
        self.main_window = MainWindow(self)

        # Populate recent projects submenu
        self._refresh_recent_projects_menu()

        # Auto-open default project if configured
        self._auto_open_default_project()

        # Connect person list selection to diagram panel navigation
        self.main_window.person_list_panel.person_selected.connect(
            self.main_window.diagram_panel.set_active_person
        )

        # Connect double-click signals to open person editor
        self.main_window.person_list_panel.person_edit_requested.connect(
            self.open_person_editor
        )
        self.main_window.diagram_panel.person_double_clicked.connect(
            self.open_person_editor
        )

        # Connect placeholder click to add new person
        self.main_window.diagram_panel.placeholder_clicked.connect(
            self.handle_placeholder_click
        )

        # Connect context menu actions from diagram panel
        self.main_window.diagram_panel.context_menu_action.connect(
            self.handle_context_menu_action
        )

        # Connect context menu actions from person list panel
        self.main_window.person_list_panel.context_menu_action.connect(
            self.handle_context_menu_action
        )

    # ------------------------------------------------------------------
    # Action callbacks (invoked by MainWindow actions)
    # ------------------------------------------------------------------

    def open_person_editor(self, person_id: str) -> None:
        """Open the person editor dialog for the given person.

        Finds the person by ID, creates a PersonEditor wrapped in a
        QDialog, and shows it modally. On save, updates project data
        and refreshes the UI.

        Args:
            person_id: The ID of the person to edit.
        """
        from slaktbusken.ui.editors.person_editor import PersonEditor

        # Find the person
        person = None
        for p in self.project_service.data.persons:
            if p.id == person_id:
                person = p
                break

        if person is None:
            logger.warning("Person med ID '%s' hittades inte.", person_id)
            return

        # Create dialog wrapper
        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Redigera person")
        dialog.setMinimumSize(600, 700)
        dialog.resize(700, 850)
        layout = QVBoxLayout(dialog)

        # Create editor widget
        editor = PersonEditor(
            project_data=self.project_service.data,
            person=person,
            parent=dialog,
            project_folder=self.project_service.project_path.parent if self.project_service.project_path else None,
        )
        layout.addWidget(editor)

        # Connect editor signals to dialog accept/reject
        editor.save_requested.connect(dialog.accept)
        editor.cancel_requested.connect(dialog.reject)

        # Show modal dialog
        if dialog.exec() == QDialog.DialogCode.Accepted:
            saved = editor.saved_person
            if saved is not None:
                self.main_window.show_progress("Uppdaterar...")
                QApplication.processEvents()
                try:
                    # Replace the person in project data
                    persons = self.project_service.data.persons
                    for i, existing in enumerate(persons):
                        if existing.id == saved.id:
                            persons[i] = saved
                            break

                    # Mark project as dirty and refresh UI without resetting active person
                    self.project_service._dirty = True
                    self._update_status()

                    # Refresh person list and re-render diagram preserving active person
                    self.main_window.person_list_panel.refresh()
                    panel = self.main_window.diagram_panel
                    panel.set_project_folder(self.project_service.project_path.parent if self.project_service.project_path else None)
                    panel.set_project_data(self.project_service.data)
                    settings = self.project_service.settings
                    if settings:
                        panel.set_person_box_config(settings.person_box_config)
                finally:
                    self.main_window.hide_progress()

    def add_standalone_person(self) -> None:
        """Create a new person with no family affiliations.

        Opens the person editor for a new person. On save, adds the person
        to project data and sets them as the active person in the diagram.
        """
        from slaktbusken.model.person import Person, Name
        from slaktbusken.model.id_generator import IDGenerator
        from slaktbusken.ui.editors.person_editor import PersonEditor

        if self.project_service.data is None:
            return

        # Collect existing IDs for generator
        data = self.project_service.data
        existing_ids: set[str] = set()
        for p in data.persons:
            existing_ids.add(p.id)
        for f in data.families:
            existing_ids.add(f.id)
        for e in data.events:
            existing_ids.add(e.id)
        for pl in data.places:
            existing_ids.add(pl.id)
        for s in data.sources:
            existing_ids.add(s.id)

        id_gen = IDGenerator(existing_ids)
        new_id = id_gen.generate("person")

        new_person = Person(
            id=new_id,
            sex="U",
            names=[Name(type="birth", given="", surname="")],
        )

        # Open editor
        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Lägg till person")
        dialog.setMinimumSize(600, 700)
        layout = QVBoxLayout(dialog)

        editor = PersonEditor(
            project_data=data,
            person=new_person,
            parent=dialog,
            project_folder=self.project_service.project_path.parent if self.project_service.project_path else None,
        )
        layout.addWidget(editor)
        editor.save_requested.connect(dialog.accept)
        editor.cancel_requested.connect(dialog.reject)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        saved = editor.saved_person
        if saved is None:
            return

        self.main_window.show_progress("Uppdaterar...")
        QApplication.processEvents()
        try:
            # Add person to project (no family affiliations)
            data.persons.append(saved)

            # Mark dirty and refresh
            self.project_service._dirty = True
            self._update_status()
            self.main_window.person_list_panel.refresh()

            # Set the new person as active
            panel = self.main_window.diagram_panel
            panel.set_project_folder(self.project_service.project_path.parent if self.project_service.project_path else None)
            panel.set_project_data(data)
            settings = self.project_service.settings
            if settings:
                panel.set_person_box_config(settings.person_box_config)
            panel.set_active_person(saved.id)
        finally:
            self.main_window.hide_progress()

    def handle_context_menu_action(self, action_type: str, person_id: str) -> None:
        """Route context menu actions to the appropriate handler.

        Dispatches actions triggered from the DiagramPanel or
        PersonListPanel context menus.

        Args:
            action_type: The action identifier (e.g. 'make_active',
                'edit_person', 'new_partner', etc.).
            person_id: The ID of the person the action applies to.
        """
        if action_type == "make_active":
            self.main_window.diagram_panel.set_active_person(person_id)
        elif action_type == "edit_person":
            self.open_person_editor(person_id)
        elif action_type == "new_partner":
            self._handle_context_add_relative("partner", person_id)
        elif action_type == "new_father":
            self._handle_context_add_relative("father", person_id)
        elif action_type == "new_mother":
            self._handle_context_add_relative("mother", person_id)
        elif action_type == "new_child":
            self._handle_context_add_relative("child", person_id)
        elif action_type == "show_relationship":
            self._show_relationship_for_person(person_id)
        else:
            logger.warning("Unknown context menu action: %s", action_type)

    def _handle_context_add_relative(self, role: str, person_id: str) -> None:
        """Handle adding a relative via context menu.

        Temporarily sets the active person to the right-clicked person
        so that handle_placeholder_click links the new person correctly,
        then restores the original active person afterward.

        Args:
            role: The relationship role ('partner', 'father', 'mother', 'child').
            person_id: The ID of the person to add the relative to.
        """
        panel = self.main_window.diagram_panel
        original_active = panel.active_person_id

        # Set the context person as active so placeholder logic links correctly
        panel._active_person_id = person_id

        # Use empty family_id — handle_placeholder_click will create a new family
        self.handle_placeholder_click(role, "")

        # Restore original active person (diagram was refreshed by handle_placeholder_click)
        if original_active:
            panel._active_person_id = original_active

    def _show_relationship_for_person(self, person_id: str) -> None:
        """Open relationship calculator with the person pre-selected.

        Opens the RelationshipDialog and pre-selects person A as the
        right-clicked person and person B as the main person.

        Args:
            person_id: The ID of the right-clicked person.
        """
        from slaktbusken.ui.dialogs.relationship_dialog import RelationshipDialog

        if self.project_service.data is None:
            return

        main_person_id = self.project_service.data.project.main_person_id

        dialog = RelationshipDialog(
            data=self.project_service.data,
            parent=self.main_window,
        )

        # Pre-select person A (right-clicked) and person B (main person)
        if person_id:
            for idx, pid in dialog._person_id_map.items():
                if pid == person_id:
                    dialog._combo_a.setCurrentIndex(idx)
                    break
        if main_person_id:
            for idx, pid in dialog._person_id_map.items():
                if pid == main_person_id:
                    dialog._combo_b.setCurrentIndex(idx)
                    break

        dialog.exec()

    def handle_placeholder_click(self, role: str, family_id: str) -> None:
        """Handle click on a placeholder box to add a new person.

        Creates a new person via the person editor, then links them
        to the appropriate family based on the placeholder role.

        Args:
            role: The placeholder role ('father', 'mother', 'child', 'partner').
            family_id: The associated family ID, or empty string if none.
        """
        from slaktbusken.model.family import Family, FamilyPartner
        from slaktbusken.model.id_generator import IDGenerator
        from slaktbusken.model.person import Name, Person
        from slaktbusken.ui.editors.person_editor import PersonEditor

        if self.project_service.data is None:
            return

        # Determine default sex based on role
        if role == "father":
            default_sex = "M"
        elif role == "mother":
            default_sex = "F"
        else:
            default_sex = "U"

        # Collect all existing IDs for the generator
        data = self.project_service.data
        existing_ids: set[str] = set()
        for p in data.persons:
            existing_ids.add(p.id)
        for f in data.families:
            existing_ids.add(f.id)
        for e in data.events:
            existing_ids.add(e.id)
        for pl in data.places:
            existing_ids.add(pl.id)
        for s in data.sources:
            existing_ids.add(s.id)

        id_gen = IDGenerator(existing_ids)
        new_id = id_gen.generate("person")

        new_person = Person(
            id=new_id,
            sex=default_sex,
            names=[Name(type="birth", given="", surname="")],
        )

        # Open editor for the new person
        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Lägg till person")
        dialog.setMinimumSize(600, 700)
        layout = QVBoxLayout(dialog)

        editor = PersonEditor(
            project_data=data,
            person=new_person,
            parent=dialog,
            project_folder=self.project_service.project_path.parent if self.project_service.project_path else None,
        )
        layout.addWidget(editor)
        editor.save_requested.connect(dialog.accept)
        editor.cancel_requested.connect(dialog.reject)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        saved = editor.saved_person
        if saved is None:
            return

        # Add the new person to project data
        data.persons.append(saved)

        # Link to appropriate family
        active_id = self.main_window.diagram_panel.active_person_id

        if role in ("father", "mother"):
            if family_id:
                # Add as partner to existing family
                fam = next(
                    (f for f in data.families if f.id == family_id), None
                )
                if fam:
                    partner_role = "father" if role == "father" else "mother"
                    fam.partners.append(
                        FamilyPartner(person_id=saved.id, role=partner_role)
                    )
            else:
                # Create a new parent family with active person as child
                fam_id = id_gen.generate("family")
                partner_role = "father" if role == "father" else "mother"
                new_family = Family(
                    id=fam_id,
                    partners=[FamilyPartner(person_id=saved.id, role=partner_role)],
                    children=[active_id] if active_id else [],
                )
                data.families.append(new_family)

        elif role == "child":
            if family_id:
                fam = next(
                    (f for f in data.families if f.id == family_id), None
                )
                if fam:
                    fam.children.append(saved.id)
            else:
                # Create new family with active person as partner and new person as child
                if active_id:
                    fam_id = id_gen.generate("family")
                    new_family = Family(
                        id=fam_id,
                        partners=[FamilyPartner(person_id=active_id, role="partner")],
                        children=[saved.id],
                    )
                    data.families.append(new_family)

        elif role == "partner":
            # Create a new family with active person and new person as partners
            if active_id:
                fam_id = id_gen.generate("family")
                new_family = Family(
                    id=fam_id,
                    partners=[
                        FamilyPartner(person_id=active_id, role="partner"),
                        FamilyPartner(person_id=saved.id, role="partner"),
                    ],
                    children=[],
                )
                data.families.append(new_family)

        # Mark dirty and refresh UI
        self.main_window.show_progress("Uppdaterar...")
        QApplication.processEvents()
        try:
            self.project_service._dirty = True
            self._update_status()
            self.main_window.person_list_panel.refresh()
            panel = self.main_window.diagram_panel
            panel.set_project_folder(self.project_service.project_path.parent if self.project_service.project_path else None)
            panel.set_project_data(data)
            settings = self.project_service.settings
            if settings:
                panel.set_person_box_config(settings.person_box_config)
        finally:
            self.main_window.hide_progress()

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
            # Record in recent projects
            project_path = self.project_service.project_path
            if project_path is not None:
                self.app_settings_service.add_recent_project(str(project_path))
                self._refresh_recent_projects_menu()

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

        self.main_window.show_progress("Laddar projekt...")
        QApplication.processEvents()
        try:
            self.project_service.open_project(Path(path))
            # Record in recent projects
            self.app_settings_service.add_recent_project(path)
            self._refresh_recent_projects_menu()

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
        finally:
            self.main_window.hide_progress()

    def save_project(self) -> None:
        """Save the current project."""
        self.main_window.show_progress("Sparar projekt...")
        QApplication.processEvents()
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
        finally:
            self.main_window.hide_progress()

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

        self.main_window.show_progress("Importerar GEDCOM...")
        QApplication.processEvents()
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

            # Prompt user to select main person if not already set
            if (
                project_data.project.main_person_id is None
                and project_data.persons
            ):
                self._prompt_select_main_person(project_data)

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
        finally:
            self.main_window.hide_progress()

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

        self.main_window.show_progress("Exporterar GEDCOM...")
        QApplication.processEvents()
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
        finally:
            self.main_window.hide_progress()

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
        panel, and marks the project as dirty. Also handles default project
        set/clear actions from the dialog.
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

        # Determine current project path for default project UI
        current_project_path = self.project_service.project_path

        dialog = SettingsDialog(
            person_box_config=settings.person_box_config,
            diagram_settings=settings.diagram_settings,
            app_settings_service=self.app_settings_service,
            current_project_path=current_project_path,
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

    def show_source_editor(self) -> None:
        """Open the source editor dialog.

        Creates a SourceEditor wrapped in a QDialog, showing the current
        project's sources for viewing, editing, and linking.
        """
        from slaktbusken.ui.editors.source_editor import SourceEditor

        project_data = self.project_service.data

        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Källredigerare")
        dialog.setMinimumSize(800, 600)
        layout = QVBoxLayout(dialog)

        editor = SourceEditor(
            project_data=project_data,
            parent=dialog,
        )
        layout.addWidget(editor)

        # Connect editor signals to dialog accept/reject
        editor.save_requested.connect(dialog.accept)
        editor.cancel_requested.connect(dialog.reject)

        dialog.exec()

        # If a source was saved via the editor, update project state
        if editor.saved_source is not None:
            saved = editor.saved_source
            # Update or add the source in project data
            found = False
            for i, existing in enumerate(project_data.sources):
                if existing.id == saved.id:
                    project_data.sources[i] = saved
                    found = True
                    break
            if not found:
                project_data.sources.append(saved)

            self.project_service._dirty = True
            self._update_status()

    def show_place_editor(self) -> None:
        """Open the place editor dialog.

        Creates a PlaceEditor wrapped in a QDialog, showing the current
        project's places for viewing, editing, and linking.
        """
        from slaktbusken.ui.editors.place_editor import PlaceEditor

        project_data = self.project_service.data

        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Platsredigerare")
        dialog.setMinimumSize(800, 600)
        layout = QVBoxLayout(dialog)

        editor = PlaceEditor(
            project_data=project_data,
            parent=dialog,
        )
        layout.addWidget(editor)

        # Connect editor signals to dialog accept/reject
        editor.save_requested.connect(dialog.accept)
        editor.cancel_requested.connect(dialog.reject)

        # Connect person open signal to open person editor
        editor.person_open_requested.connect(self.open_person_editor)

        dialog.exec()

        # If a place was saved via the editor, update project state
        if editor.saved_place is not None:
            saved = editor.saved_place
            # Update or add the place in project data
            found = False
            for i, existing in enumerate(project_data.places):
                if existing.id == saved.id:
                    project_data.places[i] = saved
                    found = True
                    break
            if not found:
                project_data.places.append(saved)

            self.project_service._dirty = True
            self._update_status()

    def show_place_translation_editor(self) -> None:
        """Open the place translation editor dialog.

        Creates a PlaceTranslationEditor wrapped in a QDialog, allowing
        the user to view, add, edit, and remove GEDCOM-to-App_JSON place
        translation mappings.
        """
        from slaktbusken.ui.editors.place_translation_editor import (
            PlaceTranslationEditor,
        )

        project_data = self.project_service.data
        project_path = self.project_service.project_path
        if project_path is None:
            return

        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Platsöversättningar")
        dialog.setMinimumSize(700, 500)
        layout = QVBoxLayout(dialog)

        editor = PlaceTranslationEditor(
            translation_service=self.translation_service,
            project_data=project_data,
            project_path=project_path.parent,
            parent=dialog,
        )
        layout.addWidget(editor)

        # Load existing translation data
        try:
            editor.load_data()
        except Exception as e:
            logger.warning("Kunde inte ladda platsöversättningar: %s", e)

        dialog.exec()

        # If the editor saved changes, mark project dirty
        if editor.is_dirty:
            self.project_service._dirty = True
            self._update_status()

    def show_source_translation_editor(self) -> None:
        """Open the source translation editor dialog.

        Creates a SourceTranslationEditor wrapped in a QDialog, allowing
        the user to view, add, edit, and remove GEDCOM-to-App_JSON source
        translation mappings.
        """
        from slaktbusken.ui.editors.source_translation_editor import (
            SourceTranslationEditor,
        )

        project_data = self.project_service.data
        project_path = self.project_service.project_path
        if project_path is None:
            return

        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Källöversättningar")
        dialog.setMinimumSize(700, 500)
        layout = QVBoxLayout(dialog)

        editor = SourceTranslationEditor(
            translation_service=self.translation_service,
            project_data=project_data,
            project_path=project_path.parent,
            parent=dialog,
        )
        layout.addWidget(editor)

        # Load existing translation data
        try:
            editor.load_data()
        except Exception as e:
            logger.warning("Kunde inte ladda källöversättningar: %s", e)

        dialog.exec()

        # If the editor saved changes, mark project dirty
        if editor.is_dirty:
            self.project_service._dirty = True
            self._update_status()

    def show_dna_editor(self) -> None:
        """Open the DNA editor dialog.

        Creates a DnaEditor wrapped in a QDialog, showing the current
        project's DNA companies, profiles, matches, segments, clusters,
        and triangulations for viewing, editing, and management.
        """
        from slaktbusken.ui.editors.dna_editor import DnaEditor

        project_data = self.project_service.data

        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("DNA-redigerare")
        dialog.setMinimumSize(900, 650)
        layout = QVBoxLayout(dialog)

        editor = DnaEditor(
            project_data=project_data,
            project_path=self.project_service.project_path,
            parent=dialog,
        )
        layout.addWidget(editor)

        dialog.exec()

        # Mark project dirty if any DNA data was modified
        self.project_service._dirty = True
        self._update_status()

    def confirm_close(self) -> bool:
        """Check if the application can close (confirm unsaved changes).

        Returns:
            True if the application may close, False to cancel.
        """
        return self._confirm_discard_changes()

    def open_recent_project(self, path: str) -> None:
        """Open a project from the recent projects list.

        Follows the same procedure as the regular open-project action
        but uses the provided path directly instead of a file dialog.

        Args:
            path: The file path of the project to open.
        """
        if not self._confirm_discard_changes():
            return

        self.main_window.show_progress("Laddar projekt...")
        QApplication.processEvents()
        try:
            self.project_service.open_project(Path(path))
            # Record in recent projects (moves to top)
            self.app_settings_service.add_recent_project(path)
            self._refresh_recent_projects_menu()

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
        finally:
            self.main_window.hide_progress()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _prompt_select_main_person(self, project_data: "ProjectData") -> None:
        """Visa dialog för att välja huvudperson efter första GEDCOM-import.

        Öppnar SelectMainPersonDialog med alla importerade personer.
        Om användaren väljer en person sätts den som main_person_id,
        projektet markeras som ändrat, och diagrammet uppdateras.

        Args:
            project_data: Aktuell projektdata med importerade personer.
        """
        from slaktbusken.ui.dialogs.select_main_person_dialog import (
            SelectMainPersonDialog,
        )

        dialog = SelectMainPersonDialog(
            persons=project_data.persons,
            events=project_data.events,
            parent=self.main_window,
        )

        if dialog.exec() == SelectMainPersonDialog.DialogCode.Accepted:
            selected_id = dialog.selected_person_id
            if selected_id:
                project_data.project.main_person_id = selected_id
                self.project_service._dirty = True
                self._update_status()
                self._update_diagram_panel()

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

    def _refresh_recent_projects_menu(self) -> None:
        """Refresh the recent projects submenu in the main window."""
        recent = self.app_settings_service.get_recent_projects()
        self.main_window.refresh_recent_projects_menu(recent)

    def _auto_open_default_project(self) -> None:
        """Auto-open the default project on startup if configured.

        If the default project path is set and the file exists, opens
        the project automatically. If set but the file is missing,
        shows a Swedish notification, clears the setting, and continues
        to the normal empty state.
        """
        default_path = self.app_settings_service.get_default_project()
        if default_path is None:
            return

        p = Path(default_path)
        if p.exists():
            self.main_window.show_progress("Laddar projekt...")
            QApplication.processEvents()
            try:
                self.project_service.open_project(p)
                self.app_settings_service.add_recent_project(default_path)
                self._refresh_recent_projects_menu()
                self._update_status()
                self._update_diagram_panel()
                self.main_window.statusBar().showMessage(
                    "Standardprojekt öppnat", 5000
                )
            except Exception as e:
                logger.warning("Kunde inte öppna standardprojektet: %s", e)
                QMessageBox.warning(
                    self.main_window,
                    "Standardprojekt",
                    f"Kunde inte öppna standardprojektet:\n{e}",
                )
            finally:
                self.main_window.hide_progress()
        else:
            # File missing — notify, clear setting, continue
            QMessageBox.information(
                self.main_window,
                "Standardprojekt",
                f"Standardprojektet kunde inte hittas:\n{default_path}\n\n"
                "Inställningen rensas.",
            )
            self.app_settings_service.set_default_project(None)

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
        """Uppdatera diagrampanelen och personlistan med aktuell projektdata.

        Sätter projektdata, personbox-konfiguration och aktiv person
        på DiagramPanel så att familjediagrammet renderas korrekt.
        Uppdaterar även personlistan så att den visar alla personer.
        """
        panel = self.main_window.diagram_panel
        settings = self.project_service.settings

        if self.project_service.project_path is not None:
            project_data = self.project_service.data
            panel.set_project_folder(self.project_service.project_path.parent)
            panel.set_project_data(project_data)

            if settings:
                panel.set_person_box_config(settings.person_box_config)

            # Set active person to main_person_id if available
            main_person = project_data.project.main_person_id
            if main_person:
                panel.set_active_person(main_person)
            elif project_data.persons:
                panel.set_active_person(project_data.persons[0].id)

            # Refresh the person list panel with current project data
            self.main_window.person_list_panel.refresh()
        else:
            panel.set_project_folder(None)
            panel.set_project_data(None)
            # Clear the person list when no project is open
            self.main_window.person_list_panel._display_list = []
            self.main_window.person_list_panel._apply_current_view()



