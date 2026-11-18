"""Confirmation for deleting a research case.

One shared path for the research overview and the case editor. Deleting a case
also deletes its hypotheses, comments and actions, so the dialog names them by
count. The wording says "ta bort forskningsärendet" and is deliberately distinct
from "ta bort kopplingen", which only removes a link to an entity.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtWidgets import QMessageBox, QWidget

from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.research_service import ResearchChildCounts, count_case_children

CONFIRM_TITLE = "Ta bort forskningsärendet"


def delete_case_message(counts: ResearchChildCounts) -> str:
    """Return the confirmation text naming what is deleted along with the case."""
    return (
        f"Att ta bort forskningsärendet tar även bort {counts.hypotheses} hypoteser, "
        f"{counts.comments} hypoteskommentarer och {counts.actions} forskningsåtgärder. "
        f"Detta kan inte ångras."
    )


def _ask_with_dialog(parent: Optional[QWidget], message: str) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(CONFIRM_TITLE)
    box.setText(message)
    cancel = box.addButton("Avbryt", QMessageBox.ButtonRole.RejectRole)
    confirm = box.addButton("Ta bort", QMessageBox.ButtonRole.DestructiveRole)
    box.setDefaultButton(cancel)
    box.exec()
    return box.clickedButton() is confirm


def confirm_and_delete_case(
    parent: Optional[QWidget],
    project_service: ProjectService,
    case_id: str,
    ask: Optional[Callable[[str], bool]] = None,
) -> bool:
    """Ask for confirmation and, if given, delete the case with its children.

    Args:
        parent: Parent widget for the dialog.
        project_service: The open project.
        case_id: The case to delete.
        ask: Replaces the dialog; receives the message and returns True to
            confirm. Used by tests.

    Returns:
        True if the case was deleted. Cancelling changes nothing and returns False.
    """
    counts = count_case_children(project_service.data, case_id)
    message = delete_case_message(counts)
    confirmed = ask(message) if ask is not None else _ask_with_dialog(parent, message)
    if not confirmed:
        return False
    return project_service.delete_research_case(case_id)
