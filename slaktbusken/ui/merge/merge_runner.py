"""Engine adapter for the UI: disk phase on a worker, adoption on the UI thread.

``MergeEngine.execute`` does all disk I/O and then adopts the committed data
into the live ``ProjectData`` (which notifies Qt listeners). Adoption must run
on the UI thread, so this adapter defers the engine's adopt step: the worker
runs everything up to and including the commit, and :meth:`finish` adopts on
the UI thread (design "Threading and responsiveness", Requirement 27.11).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from slaktbusken.model.project import ProjectData
from slaktbusken.services.editor_registry import EditorRegistry
from slaktbusken.services.merge_engine import MergeEngine, MergeOutcome
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge.merge_gateway import MergeExecutionResult
from slaktbusken.ui.merge.recovery_dialogs import log_recovery_refusal

logger = logging.getLogger(__name__)

SUCCESS_TEXT = "Sammanslagningen är klar."
ADOPT_FAILED_TEXT = (
    "Sammanslagningen sparades, men vyerna kunde inte uppdateras. Starta om Släktbusken."
)


class _DeferredAdoptEngine(MergeEngine):
    """Engine whose adopt step is held back until :meth:`adopt_pending`."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._pending: Optional[ProjectData] = None

    def _adopt(self, new_data: ProjectData) -> None:
        self._pending = new_data

    def adopt_pending(self) -> None:
        pending, self._pending = self._pending, None
        if pending is not None:
            MergeEngine._adopt(self, pending)

    def discard_pending(self) -> None:
        self._pending = None


class ThreadedMergeExecutor:
    """``MergeExecutor`` around :class:`MergeEngine` with a two-phase API."""

    def __init__(
        self,
        project_service: ProjectService,
        editor_registry: Optional[EditorRegistry] = None,
        engine: Optional[_DeferredAdoptEngine] = None,
    ) -> None:
        self._engine = engine or _DeferredAdoptEngine(project_service, editor_registry)

    # Two-phase API -----------------------------------------------------

    def run_disk_phase(self, plan: Any) -> tuple[Any, MergeOutcome]:
        """Worker thread: validate, encode and commit. Adopts nothing."""
        self._engine.discard_pending()
        return plan, self._engine.execute(plan)

    def finish(self, token: tuple[Any, MergeOutcome]) -> MergeExecutionResult:
        """UI thread: adopt the committed data and build the result."""
        plan, outcome = token
        if not outcome.success:
            self._engine.discard_pending()
            return self._failure(outcome)
        try:
            self._engine.adopt_pending()
        except Exception:  # noqa: BLE001 - the commit is on disk, memory is not
            logger.exception("Sammanslagningen kunde inte tas upp i minnet efter commit.")
            return MergeExecutionResult(False, ADOPT_FAILED_TEXT)
        return MergeExecutionResult(
            True,
            outcome.message or SUCCESS_TEXT,
            recovery_message=outcome.recovery_message,
            survivor_id=getattr(plan, "survivor_id", "") or "",
        )

    # Synchronous API (headless use) --------------------------------------

    def execute(self, plan: Any) -> MergeExecutionResult:
        return self.finish(self.run_disk_phase(plan))

    # -------------------------------------------------------------------

    @staticmethod
    def _failure(outcome: MergeOutcome) -> MergeExecutionResult:
        if outcome.refusal is not None:
            refusal = outcome.refusal
            log_recovery_refusal(refusal)
            return MergeExecutionResult(
                False, outcome.message, refusal_message=refusal.message
            )
        return MergeExecutionResult(
            False, outcome.message, recovery_message=outcome.recovery_message
        )
