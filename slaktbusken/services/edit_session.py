"""Edit session: snapshot, deferred change marking, commit and in-place rollback.

An ``EditSession`` is created by ``ProjectService.begin_edit_session`` when the
person editor opens. Editors keep mutating the live ``ProjectData``. On Spara
the session compares the snapshot with the current state and tells the service
about the change once. On Avbryt it restores the snapshot in place, so every
reference to an entity stays valid.

Snapshot scope decision (Requirements 1.1, 1.12, 1.13)
------------------------------------------------------
The snapshot is ALWAYS the full snapshot: every list field of ``ProjectData``
except ``SESSION_EXCLUDED_FIELDS``, plus ``project`` and
``connection_overrides``. A nested editor can create or change any place,
source, media item, repository, provider, source type or research object, and a
smaller snapshot can only protect what was registered in advance. A reduced
scope may be introduced only with the proof and the user approval required by
Requirement 1.13 (every Nested_Editor mutation routed through the session,
Property 1 re-run with the reduced snapshot giving the same Canonical_Form as
the full snapshot, and approval after seeing the measured figure). None of that
is implemented here.

Performance: task 1.2 measured the full snapshot and restore at 2.6-2.8 s on the
10,000-person project (figures in ``scripts/measure_edit_session.py``). That
exceeds the 1.5 s goal. The goal is reported, not enforced, and the full
snapshot is kept.
"""

from __future__ import annotations

import copy
import dataclasses
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from slaktbusken.model.project import ProjectData

if TYPE_CHECKING:  # pragma: no cover
    from slaktbusken.services.project_service import ProjectService

logger = logging.getLogger(__name__)

#: ProjectData fields that the snapshot does not cover, with the reason.
SESSION_EXCLUDED_FIELDS: dict[str, str] = {
    "format": "constant",
    "version": "set by the file loader",
    "merge_load_findings": "transient, never serialised",
    "unreadable_merge_items": "raw stored items, not edited by any editor",
    "id_high_water_marks": "monotonic; rolling back would re-issue ids",
}

#: Fields held as a single object or dict rather than a list of entities.
_SCALAR_FIELDS = ("project", "connection_overrides")

MSG_BUSY = "En annan redigering pågår. Spara eller avbryt den först."
MSG_UNSAVED_EDITOR = 'Spara eller stäng "{title}" innan du öppnar personredigeraren.'
MSG_MERGE = "En sammanslagning pågår eller har avbrutits. Öppna projektet på nytt."
MSG_IMPORT_SAVE_UNFINISHED = (
    "En sparning av en import är inte avslutad. Starta om Släktbusken för att "
    "slutföra eller kontrollera filerna."
)
MSG_IMPORT_RUNNING = "En import pågår. Vänta tills den är klar."
MSG_NO_PROJECT = "Inget projekt är öppet."
MSG_SNAPSHOT_FAILED = "Det gick inte att förbereda redigeringen. Inget har ändrats."
MSG_CONFLICT = (
    "Projektet har ändrats utanför redigeringen. Ändringarna kan inte ångras "
    "utan att förlora andra ändringar."
)


#: The session that is currently active, so nested editors without a service
#: handle can register files they copy into the project.
_current_session: "EditSession | None" = None


def register_created_file_in_active_session(path: Path) -> None:
    """Register *path* with the active edit session, if there is one.

    Used by nested editors (source editor, DNA logo copy) that have no handle
    to the project service. Does nothing outside a session.
    """
    session = _current_session
    if session is not None and not session._closed:
        session.register_created_file(Path(path))


class EditSessionBusy(Exception):
    """Another edit session is already active (condition a)."""

    def __init__(self, message: str = MSG_BUSY) -> None:
        super().__init__(message)


class UnsavedEditorsBlock(Exception):
    """Registered editors hold unsaved changes (condition b).

    Attributes:
        titles: The Swedish ``editor_title`` of every blocking editor.
    """

    def __init__(self, titles: list[str]) -> None:
        self.titles = list(titles)
        super().__init__("\n".join(MSG_UNSAVED_EDITOR.format(title=t) for t in self.titles))


class EditSessionRefused(Exception):
    """A Session_Start_Condition (c) to (f) holds; the message is user-facing."""


class EditSessionConflict(Exception):
    """The project changed outside the session; rollback restored nothing."""

    def __init__(self, message: str = MSG_CONFLICT) -> None:
        super().__init__(message)


def _restore_entity(entity: Any, saved: Any) -> None:
    """Restore *entity* in place from the deep copy *saved*."""
    entity.__dict__.clear()
    entity.__dict__.update(saved.__dict__)


def _list_field_names() -> list[str]:
    """Names of the ProjectData list fields covered by the snapshot."""
    probe = ProjectData()
    return [
        f.name
        for f in dataclasses.fields(ProjectData)
        if f.name not in SESSION_EXCLUDED_FIELDS
        and f.name not in _SCALAR_FIELDS
        and isinstance(getattr(probe, f.name), list)
    ]


class EditSession:
    """Full snapshot of the project taken when an edit starts."""

    def __init__(self, service: "ProjectService", owner_title: str) -> None:
        """Take the full snapshot.

        Raises:
            Exception: Anything the copy raises; ``begin_edit_session`` turns it
                into ``EditSessionRefused`` (condition f).
        """
        self._service = service
        self.owner_title = owner_title
        data = service.data
        self._data = data
        self._start_content_revision = service.content_revision
        self._pairs: dict[str, list[tuple[Any, Any]]] = {
            name: [(e, copy.deepcopy(e)) for e in getattr(data, name)]
            for name in _list_field_names()
        }
        # The list objects themselves: some editors assign a new list to the
        # field (``data.events = [...]``); rollback puts the original back.
        self._list_objects: dict[str, list] = {
            name: getattr(data, name) for name in self._pairs
        }
        self._project_copy = copy.deepcopy(data.project)
        self._overrides_copy = copy.deepcopy(data.connection_overrides)
        self._created_files: list[Path] = []
        self._reasons: list[str] = []
        self._closed = False
        global _current_session
        _current_session = self

    # ------------------------------------------------------------------

    def mark_changed(self, reason: str = "") -> None:
        """Deferred: record that a session-owned change happened."""
        self._reasons.append(reason)

    def register_created_file(self, path: Path) -> None:
        """Record a media or logo file copied into the project during the session."""
        self._created_files.append(Path(path))

    def has_changes(self) -> bool:
        """Whether the current state differs from the snapshot.

        Compares list membership and order by identity and each entity with its
        saved copy by dataclass equality.
        """
        data = self._data
        for name, pairs in self._pairs.items():
            current = getattr(data, name)
            if len(current) != len(pairs):
                return True
            for entity, (orig, saved) in zip(current, pairs):
                if entity is not orig or entity != saved:
                    return True
        if data.project != self._project_copy:
            return True
        return data.connection_overrides != self._overrides_copy

    def commit(self) -> bool:
        """Discard the snapshot and tell the service once when data changed.

        Returns:
            Whether the data differed from the snapshot.
        """
        changed = self.has_changes()
        reason = next((r for r in self._reasons if r), self.owner_title)
        self._finish()
        if changed:
            self._service.mark_changed(reason)
        return changed

    def rollback(self) -> None:
        """Restore the snapshot in place and notify listeners once.

        Dirty state and revision counters are not touched. Files registered with
        ``register_created_file`` are deleted.

        Raises:
            EditSessionConflict: The project changed outside the session. Nothing
                is restored and the session stays active.
        """
        if self._service.content_revision != self._start_content_revision:
            raise EditSessionConflict()
        data = self._data
        for name, pairs in self._pairs.items():
            original_list = self._list_objects[name]
            if getattr(data, name) is not original_list:
                setattr(data, name, original_list)
            original_list[:] = [entity for entity, _ in pairs]
            for entity, saved in pairs:
                if entity != saved:
                    _restore_entity(entity, saved)
        _restore_entity(data.project, self._project_copy)
        data.connection_overrides.clear()
        data.connection_overrides.update(copy.deepcopy(self._overrides_copy))
        for path in self._created_files:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning("Kunde inte ta bort filen %s", path)
        self._finish()
        self._service.notify_merge_changed()

    def _finish(self) -> None:
        """Drop the snapshot and release the service."""
        global _current_session
        if _current_session is self:
            _current_session = None
        self._closed = True
        self._pairs = {}
        self._list_objects = {}
        self._created_files = []
        self._service._release_edit_session(self)
