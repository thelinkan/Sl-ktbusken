"""Shared participation of the editors in the unsaved-changes registry.

Requirement 26.14 / 27.23 (design section 5a): every editor that can modify the
project registers itself in the ``EditorRegistry`` on construction and
unregisters when it is destroyed. The registry only asks ``has_unsaved_changes``.
``request_resolution`` runs only when the user presses "Gå till redigeraren" in
the merge wizard and lets the editor ask the user; nothing is saved or discarded
automatically.
"""

from __future__ import annotations

import weakref
from typing import Optional

from PySide6.QtWidgets import QMessageBox, QWidget

from slaktbusken.services.editor_registry import EditorRegistry, ResolutionResult

SAVE_CHOICE = "save"
DISCARD_CHOICE = "discard"
CANCEL_CHOICE = "cancel"


def prompt_resolution(parent: QWidget, title: str) -> str:
    """Ask the user how to resolve unsaved changes (modal, parented to the editor).

    Returns ``"save"``, ``"discard"`` or ``"cancel"``. Closing the box counts as
    cancel. Tests patch this function.
    """
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Osparade ändringar")
    box.setText(f"{title} har osparade ändringar.")
    save_button = box.addButton("Spara", QMessageBox.ButtonRole.AcceptRole)
    discard_button = box.addButton(
        "Kasta ändringar", QMessageBox.ButtonRole.DestructiveRole
    )
    cancel_button = box.addButton("Avbryt", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel_button)
    box.setEscapeButton(cancel_button)
    box.exec()
    clicked = box.clickedButton()
    if clicked is save_button:
        return SAVE_CHOICE
    if clicked is discard_button:
        return DISCARD_CHOICE
    return CANCEL_CHOICE


class EditorRegistryParticipant:
    """Mixin implementing ``UnsavedChangesParticipant`` for a ``QWidget`` editor.

    Defaults: ``has_unsaved_changes`` delegates to ``is_dirty`` (property or
    method) when the editor has one, otherwise it is False. Subclasses override
    ``_save_for_resolution`` and ``_discard_for_resolution`` to act on the
    user's choice in ``request_resolution``.
    """

    editor_title: str = "Redigerare"

    def _join_registry(
        self, registry: Optional[EditorRegistry], title: Optional[str] = None
    ) -> None:
        """Register on construction and unregister on ``destroyed``."""
        if title is not None:
            self.editor_title = title
        self._editor_registry = registry
        if registry is None:
            return
        registry.register(self)  # type: ignore[arg-type]
        ref = weakref.ref(self)

        def _unregister(*_args) -> None:
            obj = ref()
            if obj is not None:
                registry.unregister(obj)

        self.destroyed.connect(_unregister)  # type: ignore[attr-defined]

    def has_unsaved_changes(self) -> bool:
        dirty = getattr(self, "is_dirty", False)
        return bool(dirty() if callable(dirty) else dirty)

    def request_resolution(self) -> ResolutionResult:
        """Bring the editor forward and let the editor ask the user."""
        widget: QWidget = self  # type: ignore[assignment]
        window = widget.window()
        window.show()
        window.raise_()
        window.activateWindow()
        if not self.has_unsaved_changes():
            return ResolutionResult.SAVED
        choice = prompt_resolution(widget, self.editor_title)
        if choice == SAVE_CHOICE:
            self._save_for_resolution()
        elif choice == DISCARD_CHOICE:
            self._discard_for_resolution()
        return (
            ResolutionResult.STILL_UNSAVED
            if self.has_unsaved_changes()
            else (
                ResolutionResult.SAVED
                if choice == SAVE_CHOICE
                else ResolutionResult.DISCARDED
            )
        )

    def _save_for_resolution(self) -> None:
        save = getattr(self, "_on_save", None)
        if callable(save):
            save()

    def _discard_for_resolution(self) -> None:
        load = getattr(self, "load_data", None)
        if callable(load):
            load()
