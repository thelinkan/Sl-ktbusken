"""Background worker thread for running person checks."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.settings_io import PersonCheckConfig
from slaktbusken.services.person_check_engine import CheckFinding, PersonCheckEngine


class _InterruptedError(Exception):
    """Raised when the worker thread is interrupted."""

    pass


class CheckWorker(QThread):
    """Bakgrundstråd som kör PersonCheckEngine."""

    progress_updated = Signal(int)  # 0-100
    finished = Signal(list)  # list[CheckFinding]

    def __init__(
        self,
        data: ProjectData,
        config: PersonCheckConfig,
        project_folder: Path | None,
    ) -> None:
        super().__init__()
        self._data = data
        self._config = config
        self._project_folder = project_folder

    def run(self) -> None:
        """Run person checks in the background thread."""
        try:
            engine = PersonCheckEngine(
                data=self._data,
                config=self._config,
                project_folder=self._project_folder,
            )
            findings = engine.run_checks(progress_callback=self._progress_callback)
            self.finished.emit(findings)
        except _InterruptedError:
            # Worker was interrupted — emit finished with empty results
            self.finished.emit([])
        except Exception:
            # On unexpected error, emit finished with empty results
            self.finished.emit([])

    def _progress_callback(self, percent: int) -> None:
        """Callback passed to PersonCheckEngine.run_checks().

        Emits progress signal and checks for interruption request.
        """
        if self.isInterruptionRequested():
            raise _InterruptedError()
        self.progress_updated.emit(percent)
