"""Message boxes for merge outcomes and the Recovery_Refusal (Requirement 27.25)."""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QWidget

logger = logging.getLogger(__name__)

REFUSAL_TITLE = "Projektet kunde inte öppnas"
MERGE_TITLE = "Slå samman personer"
SHOW_HISTORY_TEXT = "Visa sammanslagningshistorik"
CLOSE_TEXT = "Stäng"


def log_recovery_refusal(refusal: object) -> None:
    """Write the refusal details to the application log (outside the project)."""
    logger.error(
        "Återställning vägrades (%s). Projektfil: %s, journal: %s, temporära filer: %s, "
        "säkerhetskopia: %s",
        getattr(refusal, "code", "?"),
        getattr(refusal, "project_path", None),
        getattr(refusal, "journal_path", None),
        [str(p) for p in getattr(refusal, "temp_paths", ())],
        getattr(refusal, "backup_dir", None),
    )


def build_refusal_box(parent: Optional[QWidget], message: str) -> QMessageBox:
    """A modal critical box whose full text is selectable and copyable."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(REFUSAL_TITLE)
    box.setText(message)
    box.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
        | Qt.TextInteractionFlag.TextSelectableByKeyboard
    )
    for label in box.findChildren(QLabel):
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
    box.addButton(CLOSE_TEXT, QMessageBox.ButtonRole.AcceptRole)
    box.setModal(True)
    return box


def show_recovery_refusal(parent: Optional[QWidget], message: str) -> None:
    """Show the Recovery_Refusal message in a modal box."""
    build_refusal_box(parent, message).exec()


def show_recovery_outcome(parent: Optional[QWidget], message: str) -> None:
    """Inform the user that a recovery finished (for example "Sammanslagningen slutfördes.")."""
    if message:
        QMessageBox.information(parent, MERGE_TITLE, message)


def ask_show_history(parent: Optional[QWidget], text: str) -> bool:
    """Success box with an option to open the Merge_History view. True = open it."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(MERGE_TITLE)
    box.setText(text)
    history: QPushButton = box.addButton(SHOW_HISTORY_TEXT, QMessageBox.ButtonRole.AcceptRole)
    box.addButton(CLOSE_TEXT, QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is history
