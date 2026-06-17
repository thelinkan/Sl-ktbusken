"""New Project dialog for creating a Släktbusken genealogy project.

Prompts the user for a project name (1–100 characters) and a file system
location. Validates inputs and exposes the results via properties.
All UI text is in Swedish.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QDialog, QFileDialog, QWidget

from slaktbusken.ui.generated.ui_new_project_dialog import Ui_NewProjectDialog


class NewProjectDialog(QDialog):
    """Dialog for creating a new project.

    Provides input fields for project name and location with real-time
    validation. The OK button ("Skapa") is disabled until both fields
    are valid.

    Args:
        parent: Optional parent widget.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._ui = Ui_NewProjectDialog()
        self._ui.setupUi(self)

        self._location: str = ""

        # Rename the OK button to "Skapa"
        ok_button = self._ui.buttonBox.button(self._ui.buttonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText("Skapa")

        # Connect signals
        self._ui.buttonBrowse.clicked.connect(self._browse_location)
        self._ui.lineEditName.textChanged.connect(self._validate)
        self._ui.buttonBox.accepted.connect(self._on_accept)

        # Initial validation state
        self._validate()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def project_name(self) -> str:
        """The entered project name (stripped of leading/trailing whitespace)."""
        return self._ui.lineEditName.text().strip()

    @property
    def project_location(self) -> Path:
        """The selected project location as a Path."""
        return Path(self._location)

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _browse_location(self) -> None:
        """Open a directory picker and update the location label."""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Välj plats för projektet",
        )
        if directory:
            self._location = directory
            self._ui.labelLocationPath.setText(directory)
            self._validate()

    def _validate(self) -> None:
        """Validate inputs and update the error label and OK button state."""
        name = self._ui.lineEditName.text().strip()
        errors: list[str] = []

        if not name:
            errors.append("Projektnamnet måste vara 1\u2013100 tecken")
        elif len(name) > 100:
            errors.append("Projektnamnet måste vara 1\u2013100 tecken")

        if not self._location:
            errors.append("Välj en plats för projektet")

        self._ui.labelError.setText("\n".join(errors))

        ok_button = self._ui.buttonBox.button(self._ui.buttonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setEnabled(len(errors) == 0)

    def _on_accept(self) -> None:
        """Handle accept: final validation before closing the dialog."""
        name = self._ui.lineEditName.text().strip()
        if not name or len(name) > 100:
            self._ui.labelError.setText("Projektnamnet måste vara 1\u2013100 tecken")
            return
        if not self._location:
            self._ui.labelError.setText("Välj en plats för projektet")
            return
        self.accept()
