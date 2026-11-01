"""Registry of editors that may hold unsaved changes (Qt-free).

The registry only reports which editors hold unsaved changes. It never calls
a save or discard method of an editor; ``request_resolution`` is invoked only
by the user-facing wizard, never by the registry itself.
"""

from __future__ import annotations

import weakref
from enum import Enum
from typing import Protocol, runtime_checkable


class ResolutionResult(Enum):
    SAVED = "saved"
    DISCARDED = "discarded"
    STILL_UNSAVED = "still_unsaved"  # the user cancelled inside the editor


@runtime_checkable
class UnsavedChangesParticipant(Protocol):
    editor_title: str  # Swedish, e.g. "Personredigerare: Anna Svensson (person_12)"

    def has_unsaved_changes(self) -> bool: ...

    def request_resolution(self) -> ResolutionResult:
        """Bring the editor to the front and let the editor ask the user."""
        ...


class EditorRegistry:
    """Holds editors by weak reference, in registration order."""

    def __init__(self) -> None:
        self._refs: list[weakref.ref] = []

    def _alive(self) -> list[tuple[weakref.ref, UnsavedChangesParticipant]]:
        alive = []
        for ref in self._refs:
            obj = ref()
            if obj is not None:
                alive.append((ref, obj))
        self._refs = [ref for ref, _ in alive]
        return alive

    def register(self, editor: UnsavedChangesParticipant) -> None:
        if any(obj is editor for _, obj in self._alive()):
            return
        self._refs.append(weakref.ref(editor))

    def unregister(self, editor: UnsavedChangesParticipant) -> None:
        self._refs = [ref for ref, obj in self._alive() if obj is not editor]

    def unsaved_editors(self) -> list[UnsavedChangesParticipant]:
        return [obj for _, obj in self._alive() if obj.has_unsaved_changes()]
