"""MergeEngine: executes a :class:`MergePlan` as one atomic operation (Qt-free).

Implements design section 12 (Requirements 1.4, 1.6, 26.9, 27.1 to 27.5,
27.8 to 27.10, 27.15, 27.22 to 27.24, 28.1 to 28.3, 28.12, 29.11, 30.1, 30.10).

Order of ``execute``:

0. Saved_State_Precondition (project in saved state, no editor with unsaved
   changes). A refusal changes and saves nothing.
1. Validate the plan against the current data (executable, every inventory
   handler present, ``content_revision`` and fingerprint unchanged).
2. Build the new project data in memory (the live data is not touched).
3. Move translation mappings of the retired person into identity aliases.
4. Post-merge validation (no stale reference, information ledger).
5. Encode project and ``persons.json`` bytes.
6. Commit through :class:`MergeTransaction` (pre-flight, Recovery_Point,
   journal, replace; the recovery decision is run by the transaction).
7. Adopt: copy the committed data onto the existing ``ProjectData`` instance,
   then ``ProjectService.adopt_committed_state()`` (dirty flag false,
   ``revision`` and ``content_revision`` plus one, listeners notified once).

The Recovery_Point is the saved state on disk; step 0 guarantees that it equals
the in-memory state, so the commit never contains an unsaved edit. Any failure
before the adopt step leaves memory, the dirty flag and ``revision`` unchanged.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, Optional

from slaktbusken.model.project import ProjectData
from slaktbusken.persistence import translation_io
from slaktbusken.persistence.file_io import FilePersistence
from slaktbusken.persistence.translation_io import IdentityAlias, TranslationData
from slaktbusken.services import person_reference_index as pri
from slaktbusken.services.commit.fs_ops import CommitFs
from slaktbusken.services.commit.recovery import RecoveryRefusal, RecoveryRefusedError
from slaktbusken.services.commit.transaction import (
    CommitFailed,
    CommitRefused,
    MergeTransaction,
)
from slaktbusken.services.editor_registry import EditorRegistry
from slaktbusken.services.merge_planner import (
    MergePlan,
    apply_change_set,
    compute_fingerprint,
    compute_ledger,
)
from slaktbusken.services.project_service import ProjectService

logger = logging.getLogger(__name__)

__all__ = ["MergeEngine", "MergeOutcome", "Preconditions"]

NO_CHANGE = "Inga ändringar har gjorts i projektet."

DIRTY_MESSAGE = "Projektet har osparade ändringar. Spara projektet innan sammanslagningen."
PLAN_STALE_MESSAGE = "Projektet har ändrats; granska förhandsgranskningen igen."
PLAN_NOT_EXECUTABLE_MESSAGE = (
    "Sammanslagningen kan inte genomföras eftersom förhandsgranskningen har "
    "olösta val eller konflikter. " + NO_CHANGE
)
NO_PROJECT_MESSAGE = "Inget projekt är öppet. " + NO_CHANGE
_PERSON_PREFIX = "person_"


def _editors_message(titles: list[str]) -> str:
    return "\n".join(
        f"Redigeraren {title} har osparade ändringar. Spara eller kasta "
        "ändringarna i redigeraren och försök igen."
        for title in titles
    )


def _step_failed(step: str) -> str:
    return f"Sammanslagningen misslyckades i steget \"{step}\". {NO_CHANGE}"


@dataclass(frozen=True)
class MergeOutcome:
    """Result of :meth:`MergeEngine.execute`."""

    success: bool
    message: str = ""
    history_entry_id: Optional[str] = None
    step: str = ""
    #: True when the plan no longer matches the project (the wizard rebuilds it).
    stale: bool = False
    #: Set when the recovery decision after a commit error was a refusal.
    refusal: Optional[RecoveryRefusal] = None
    #: Swedish message from a recovery that completed the commit after an error.
    recovery_message: str = ""


class Preconditions:
    """The Saved_State_Precondition (Requirements 27.22, 27.23)."""

    @staticmethod
    def check(service: ProjectService, registry: Optional[EditorRegistry]) -> Optional[str]:
        """Swedish refusal text, or ``None`` when the merge may proceed.

        Only reads: ``is_saved_state`` and ``unsaved_editors``. Nothing is
        saved, committed, discarded or resolved.
        """
        if not service.is_saved_state():
            return DIRTY_MESSAGE
        if registry is not None:
            editors = registry.unsaved_editors()
            if editors:
                return _editors_message([e.editor_title for e in editors])
        return None


class _StepError(Exception):
    def __init__(self, step: str, message: Optional[str] = None) -> None:
        super().__init__(message or _step_failed(step))
        self.step = step
        self.message = message or _step_failed(step)


class MergeEngine:
    """Applies a merge plan to the open project, atomically."""

    def __init__(
        self,
        project_service: ProjectService,
        editor_registry: Optional[EditorRegistry] = None,
        fs: Optional[CommitFs] = None,
        app_version: str = "unknown",
    ) -> None:
        self._service = project_service
        self._registry = editor_registry
        self._fs = fs
        self._app_version = app_version

    # ------------------------------------------------------------------

    def execute(self, plan: MergePlan) -> MergeOutcome:
        """Run the merge. Never raises for expected failures."""
        service = self._service
        service.set_merge_in_progress(True)
        try:
            return self._execute(plan)
        except _StepError as exc:
            return MergeOutcome(False, exc.message, step=exc.step)
        except RecoveryRefusedError as exc:
            refusal = getattr(exc, "refusal", None)
            return MergeOutcome(False, str(exc), step="commit", refusal=refusal)
        except Exception:  # noqa: BLE001 - nothing was adopted
            logger.exception("Sammanslagningen misslyckades oväntat.")
            return MergeOutcome(False, _step_failed("okänt fel"), step="unknown")
        finally:
            service.set_merge_in_progress(False)

    # ------------------------------------------------------------------

    def _execute(self, plan: MergePlan) -> MergeOutcome:
        service = self._service

        # 0. Saved_State_Precondition.
        refusal_text = Preconditions.check(service, self._registry)
        if refusal_text is not None:
            return MergeOutcome(False, refusal_text, step="precondition")

        project_file = service.project_path
        if project_file is None:
            return MergeOutcome(False, NO_PROJECT_MESSAGE, step="precondition")
        data = service.data

        # 1. Validate the plan against the current data.
        translation = self._read_translation(project_file)
        stale = self._validate_plan(plan, data, translation)
        if stale is not None:
            return stale

        survivor, retired = plan.survivor_id, plan.retired_id
        assert survivor is not None and retired is not None

        # 2. Build the new data (the live data is not touched).
        try:
            new_data = apply_change_set(data, plan.change_set)
            new_data.id_high_water_marks = self._raised_marks(new_data, retired)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Sammanslagningen kunde inte tillämpas.")
            raise _StepError("tillämpa sammanslagningen") from exc
        entry = next((h for h in new_data.merge_history if h.merged_person_id == retired), None)
        if entry is None:
            raise _StepError("sammanslagningshistorik")

        # 3. Translation: mappings of the retired person become aliases.
        new_translation = self._merged_translation(plan, translation, retired, survivor)

        # 4. Post-merge validation.
        self._validate_result(plan, new_data, new_translation, retired)

        # 5. Encode.
        try:
            project_bytes = FilePersistence.encode(new_data)
            persons_bytes: Optional[bytes] = None
            if self._translation_changes(plan):
                persons_bytes = translation_io.dumps_persons(
                    new_translation.persons, new_translation.families,
                    new_translation.person_aliases,
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Sammanslagningen kunde inte kodas.")
            raise _StepError("skriva data") from exc

        # 6. Commit.
        transaction = MergeTransaction(
            project_file, self._fs, app_version=self._app_version
        )
        try:
            result = transaction.commit(
                project_bytes, persons_bytes, revision_before=service.revision
            )
        except CommitRefused as exc:
            return MergeOutcome(
                False, "\n".join(exc.messages) + f"\n{NO_CHANGE}", step="pre-flight"
            )
        except CommitFailed as exc:
            return MergeOutcome(False, exc.message, step="commit")
        # RecoveryRefusedError propagates to execute().

        # 7. Adopt.
        self._adopt(new_data)
        recovery_message = ""
        if result.recovered:
            recovery_message = getattr(result.recovery_outcome, "message", "") or ""
        return MergeOutcome(
            True, "Sammanslagningen är klar.", history_entry_id=entry.id,
            step="done", recovery_message=recovery_message,
        )

    # ------------------------------------------------------------------
    # Steps

    @staticmethod
    def _read_translation(project_file: Path) -> TranslationData:
        try:
            return translation_io.read_all(Path(project_file).parent / "translation")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Översättningsfilerna kunde inte läsas.")
            raise _StepError(
                "läsa översättningsfiler",
                f"Översättningsfilerna kunde inte läsas. {NO_CHANGE}",
            ) from exc

    def _validate_plan(
        self, plan: MergePlan, data: ProjectData, translation: TranslationData
    ) -> Optional[MergeOutcome]:
        if not plan.can_execute:
            return MergeOutcome(False, PLAN_NOT_EXECUTABLE_MESSAGE, step="plan")
        missing = pri.missing_handlers_message()
        if missing is not None:
            return MergeOutcome(False, f"{missing}\n{NO_CHANGE}", step="plan")
        if plan.content_revision != self._service.content_revision:
            return MergeOutcome(False, PLAN_STALE_MESSAGE, step="plan", stale=True)
        try:
            index = pri.PersonReferenceIndex.build(
                data, plan.decisions.person_ids, translation
            )
            fingerprint = compute_fingerprint(
                data, plan.decisions.person_ids, index, translation
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Kontrollen av förhandsgranskningen misslyckades.")
            raise _StepError("kontrollera förhandsgranskningen") from exc
        if fingerprint != plan.fingerprint:
            return MergeOutcome(False, PLAN_STALE_MESSAGE, step="plan", stale=True)
        return None

    @staticmethod
    def _raised_marks(new_data: ProjectData, retired: str) -> dict[str, int]:
        """Copy of the high-water marks with ``person_`` at least the retired suffix."""
        marks = dict(new_data.id_high_water_marks)
        match = re.fullmatch(rf"{re.escape(_PERSON_PREFIX)}(\d+)", retired)
        if match:
            marks[_PERSON_PREFIX] = max(marks.get(_PERSON_PREFIX, 0), int(match.group(1)))
        return marks

    @staticmethod
    def _translation_changes(plan: MergePlan) -> bool:
        ops = plan.identity_ops
        return bool(
            ops.mappings_moved or ops.aliases_rewritten
            or ops.new_aliases or ops.rewritten_aliases
        )

    @staticmethod
    def _merged_translation(
        plan: MergePlan, translation: TranslationData, retired: str, survivor: str
    ) -> TranslationData:
        """Translation after the merge (a new object; the input is not modified)."""
        ops = plan.identity_ops
        rewritten = {(a.gedcom_id, a.merge_id): a for a in ops.rewritten_aliases}
        aliases: list[IdentityAlias] = []
        for alias in translation.person_aliases:
            if alias.person_id == retired:
                alias = rewritten.get(
                    (alias.gedcom_id, alias.merge_id),
                    IdentityAlias(alias.gedcom_id, alias.fingerprint, survivor, alias.merge_id),
                )
            aliases.append(alias)
        aliases.extend(ops.new_aliases)
        return TranslationData(
            sources=list(translation.sources),
            places=list(translation.places),
            persons=[m for m in translation.persons if m.app_id != retired],
            families=list(translation.families),
            person_aliases=aliases,
        )

    @staticmethod
    def _validate_result(
        plan: MergePlan, new_data: ProjectData, translation: TranslationData, retired: str
    ) -> None:
        step = "kontrollera resultatet"
        try:
            if any(p.id == retired for p in new_data.persons):
                raise _StepError(step)
            index = pri.PersonReferenceIndex.build(new_data, [retired], translation)
            stale = [
                loc.key
                for loc in pri.PERSON_REFERENCE_INVENTORY
                if loc.requires_handler and index.count(loc.key, retired)
            ]
            if stale:
                raise _StepError(
                    step,
                    "Sammanslagningen avbröts eftersom den borttagna personen fortfarande "
                    f"refereras på: {', '.join(stale)}. {NO_CHANGE}",
                )
            differences = compute_ledger(new_data).differences(plan.ledger_after_expected)
            if differences:
                names = ", ".join(sorted(differences))
                raise _StepError(
                    step,
                    f"Sammanslagningen avbröts eftersom information skulle försvinna ({names}). "
                    + NO_CHANGE,
                )
        except _StepError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Kontrollen av resultatet misslyckades.")
            raise _StepError(step) from exc

    def _adopt(self, new_data: ProjectData) -> None:
        """Copy *new_data* onto the live instance, then run the adopt step."""
        live = self._service.data
        names = [f.name for f in fields(ProjectData)]
        snapshot = {n: getattr(live, n) for n in names}
        try:
            for name in names:
                setattr(live, name, getattr(new_data, name))
        except Exception:  # noqa: BLE001 - never leave memory half adopted
            for name, value in snapshot.items():
                setattr(live, name, value)
            raise
        self._service.adopt_committed_state()
