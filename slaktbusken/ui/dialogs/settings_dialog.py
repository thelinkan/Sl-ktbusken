"""Settings dialog for configuring person box fields and diagram depth.

Provides a modal dialog where the user can toggle visibility of each
of the 11 person box content fields and adjust the ancestry/descendants
depth for diagram rendering. Also provides default project management
(set/clear). All UI text is in Swedish.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.persistence.settings_io import (
    DiagramSettings,
    PersonBoxConfig,
)
from slaktbusken.ui.generated.ui_settings_dialog import Ui_SettingsDialog

if TYPE_CHECKING:
    from slaktbusken.persistence.app_settings_io import AppSettingsService


class SettingsDialog(QDialog):
    """Dialog for editing project settings (person box config and diagram depth).

    Loads current PersonBoxConfig and DiagramSettings values into the UI
    on construction. Also provides a "Standardprojekt" section for setting
    or clearing the default project. After the user clicks OK, the updated
    config and settings can be retrieved via the result properties.

    Args:
        person_box_config: Current person box configuration to populate the form.
        diagram_settings: Current diagram depth settings to populate the form.
        app_settings_service: Application settings service for default project management.
        current_project_path: Path to the currently open project, or None.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        person_box_config: PersonBoxConfig,
        diagram_settings: DiagramSettings,
        app_settings_service: Optional["AppSettingsService"] = None,
        current_project_path: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialise the settings dialog with current values.

        Args:
            person_box_config: Current person box field configuration.
            diagram_settings: Current diagram depth settings.
            app_settings_service: Application settings service for default project.
            current_project_path: Path to currently open project, or None.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._ui = Ui_SettingsDialog()
        self._ui.setupUi(self)

        self._app_settings_service = app_settings_service
        self._current_project_path = current_project_path

        self._load_person_box_config(person_box_config)
        self._load_diagram_settings(diagram_settings)
        self._setup_default_project_section()

    @property
    def person_box_config(self) -> PersonBoxConfig:
        """Build a PersonBoxConfig from the current checkbox states.

        Returns:
            A PersonBoxConfig reflecting the user's selections.
        """
        return PersonBoxConfig(
            name=self._ui.checkName.isChecked(),
            birth_date=self._ui.checkBirthDate.isChecked(),
            birth_place=self._ui.checkBirthPlace.isChecked(),
            death_date=self._ui.checkDeathDate.isChecked(),
            death_place=self._ui.checkDeathPlace.isChecked(),
            marriage_date=self._ui.checkMarriageDate.isChecked(),
            marriage_place=self._ui.checkMarriagePlace.isChecked(),
            occupation=self._ui.checkOccupation.isChecked(),
            photo=self._ui.checkPhoto.isChecked(),
            dna_info=self._ui.checkDnaInfo.isChecked(),
            notes=self._ui.checkNotes.isChecked(),
            cause_of_death=self._ui.checkCauseOfDeath.isChecked(),
            clusters=self._ui.checkClusters.isChecked(),
        )

    @property
    def diagram_settings(self) -> DiagramSettings:
        """Build a DiagramSettings from the current spinbox values.

        Returns:
            A DiagramSettings reflecting the user's selections.
        """
        return DiagramSettings(
            ancestry_depth=self._ui.spinAncestryDepth.value(),
            descendants_depth=self._ui.spinDescendantsDepth.value(),
        )

    def _load_person_box_config(self, config: PersonBoxConfig) -> None:
        """Populate checkboxes from a PersonBoxConfig.

        Args:
            config: The configuration to load into the UI.
        """
        self._ui.checkName.setChecked(config.name)
        self._ui.checkBirthDate.setChecked(config.birth_date)
        self._ui.checkBirthPlace.setChecked(config.birth_place)
        self._ui.checkDeathDate.setChecked(config.death_date)
        self._ui.checkDeathPlace.setChecked(config.death_place)
        self._ui.checkMarriageDate.setChecked(config.marriage_date)
        self._ui.checkMarriagePlace.setChecked(config.marriage_place)
        self._ui.checkOccupation.setChecked(config.occupation)
        self._ui.checkPhoto.setChecked(config.photo)
        self._ui.checkDnaInfo.setChecked(config.dna_info)
        self._ui.checkNotes.setChecked(config.notes)
        self._ui.checkCauseOfDeath.setChecked(config.cause_of_death)
        self._ui.checkClusters.setChecked(config.clusters)

    def _load_diagram_settings(self, settings: DiagramSettings) -> None:
        """Populate spinboxes from a DiagramSettings.

        Args:
            settings: The diagram settings to load into the UI.
        """
        self._ui.spinAncestryDepth.setValue(settings.ancestry_depth)
        self._ui.spinDescendantsDepth.setValue(settings.descendants_depth)

    def _setup_default_project_section(self) -> None:
        """Add the 'Standardprojekt' group box to the dialog layout.

        Creates a group box with a label showing the current default
        project, plus buttons to set or clear the default.
        """
        if self._app_settings_service is None:
            return

        # Find the main layout of the dialog (from setupUi)
        main_layout = self.layout()
        if main_layout is None:
            return

        # Create group box
        group_box = QGroupBox("Standardprojekt", self)
        vbox = QVBoxLayout(group_box)

        # Show current default project
        default_path = self._app_settings_service.get_default_project()
        if default_path:
            self._default_label = QLabel(f"Nuvarande: {default_path}")
        else:
            self._default_label = QLabel("Inget standardprojekt angivet")
        vbox.addWidget(self._default_label)

        # Buttons row
        btn_layout = QHBoxLayout()

        self._btn_set_default = QPushButton("Ange som standard")
        self._btn_set_default.setToolTip(
            "Ange det öppna projektet som standardprojekt vid uppstart"
        )
        self._btn_set_default.clicked.connect(self._on_set_default)
        # Disable if no project is open
        if self._current_project_path is None:
            self._btn_set_default.setEnabled(False)
            self._btn_set_default.setToolTip("Inget projekt öppet")
        btn_layout.addWidget(self._btn_set_default)

        self._btn_clear_default = QPushButton("Rensa standard")
        self._btn_clear_default.setToolTip("Ta bort standardprojektinställningen")
        self._btn_clear_default.clicked.connect(self._on_clear_default)
        # Disable if no default is set
        if default_path is None:
            self._btn_clear_default.setEnabled(False)
        btn_layout.addWidget(self._btn_clear_default)

        vbox.addLayout(btn_layout)

        # Insert the group box before the dialog button box (last item in layout)
        # The button box (OK/Cancel) is typically the last widget in the layout
        insert_index = main_layout.count() - 1
        if insert_index < 0:
            insert_index = 0
        main_layout.insertWidget(insert_index, group_box)

    def _on_set_default(self) -> None:
        """Set the current project as the default project."""
        if self._app_settings_service is None or self._current_project_path is None:
            return

        path_str = str(self._current_project_path)
        self._app_settings_service.set_default_project(path_str)
        self._default_label.setText(f"Nuvarande: {path_str}")
        self._btn_clear_default.setEnabled(True)

    def _on_clear_default(self) -> None:
        """Clear the default project setting."""
        if self._app_settings_service is None:
            return

        self._app_settings_service.set_default_project(None)
        self._default_label.setText("Inget standardprojekt angivet")
        self._btn_clear_default.setEnabled(False)
