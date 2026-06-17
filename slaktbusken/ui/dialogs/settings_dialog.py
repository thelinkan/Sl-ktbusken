"""Settings dialog for configuring person box fields and diagram depth.

Provides a modal dialog where the user can toggle visibility of each
of the 11 person box content fields and adjust the ancestry/descendants
depth for diagram rendering. All UI text is in Swedish.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QDialog, QWidget

from slaktbusken.persistence.settings_io import (
    DiagramSettings,
    PersonBoxConfig,
)
from slaktbusken.ui.generated.ui_settings_dialog import Ui_SettingsDialog


class SettingsDialog(QDialog):
    """Dialog for editing project settings (person box config and diagram depth).

    Loads current PersonBoxConfig and DiagramSettings values into the UI
    on construction. After the user clicks OK, the updated config and
    settings can be retrieved via the result properties.

    Args:
        person_box_config: Current person box configuration to populate the form.
        diagram_settings: Current diagram depth settings to populate the form.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        person_box_config: PersonBoxConfig,
        diagram_settings: DiagramSettings,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialise the settings dialog with current values.

        Args:
            person_box_config: Current person box field configuration.
            diagram_settings: Current diagram depth settings.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._ui = Ui_SettingsDialog()
        self._ui.setupUi(self)

        self._load_person_box_config(person_box_config)
        self._load_diagram_settings(diagram_settings)

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

    def _load_diagram_settings(self, settings: DiagramSettings) -> None:
        """Populate spinboxes from a DiagramSettings.

        Args:
            settings: The diagram settings to load into the UI.
        """
        self._ui.spinAncestryDepth.setValue(settings.ancestry_depth)
        self._ui.spinDescendantsDepth.setValue(settings.descendants_depth)
