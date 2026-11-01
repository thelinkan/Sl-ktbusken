"""Merge_Review wizard: survivor choice, review sections and preview.

An application-modal dialog with a section list on the left and a stacked page
area on the right (design 15.8). It builds ``MergePlan`` objects with
``build_plan`` (on a worker thread) and hands a ready plan to a ``MergeExecutor``
(see ``merge_gateway``). It never imports the engine and writes nothing before
the second confirmation.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Sequence

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.services import merge_rules as rules
from slaktbusken.services import person_reference_index as pri
from slaktbusken.services.editor_registry import EditorRegistry
from slaktbusken.services.merge_planner import (
    MergeDecisions,
    MergePlan,
    MergePlanError,
    MergeRefusal,
    build_plan,
    compute_fingerprint,
)
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge.merge_gateway import (
    MergeExecutionResult,
    MergeExecutor,
    get_merge_executor,
)
from slaktbusken.ui.merge.merge_pages import (
    SECTION_DEFS,
    SectionPage,
    SurvivorPage,
    build_choice_specs,
)
from slaktbusken.ui.merge.merge_preview import PREVIEW_TITLE, MergePreviewWidget
from slaktbusken.ui.merge.recovery_dialogs import show_recovery_refusal
from slaktbusken.ui.widgets.progress_overlay import ProgressOverlay

logger = logging.getLogger(__name__)

WINDOW_TITLE = "Slå samman personer"
SURVIVOR_SECTION_TITLE = "Välj person som behålls"
SAVE_AND_CONTINUE_TEXT = "Spara och fortsätt"
CANCEL_TEXT = "Avbryt"
GO_TO_EDITOR_TEXT = "Gå till redigeraren"
CONFIRM_MERGE_TEXT = "Slå samman"
EDITOR_BLOCK_TEXT = (
    "Redigeraren {title} har osparade ändringar. Spara eller kasta ändringarna i "
    "redigeraren och försök igen."
)
SAVE_FAILED_TEXT = "Projektet kunde inte sparas. Ingenting har slagits samman."
SAVE_PROMPT_TEXT = "Projektet har osparade ändringar. Spara projektet innan sammanslagningen."
CONFIRM_QUESTION = "Slå samman {survivor} som behålls med {retired} som tas bort?"
MERGE_FAILED_TEXT = "Sammanslagningen kunde inte genomföras."
COMMIT_PROGRESS_TEXT = "Genomför sammanslagningen..."

SAVE = "save"
CANCEL = "cancel"


def person_name(service: ProjectService, person_id: str) -> str:
    """Display name of a person ("Förnamn Efternamn") or the id."""
    data = service.data
    for person in data.persons:
        if person.id == person_id and person.names:
            n = person.names[0]
            return f"{n.given} {n.surname}".strip() or person_id
    return person_id


def person_text(service: ProjectService, person_id: str) -> str:
    """Name with id, for example "Anna Svensson (person_12)"."""
    return f"{person_name(service, person_id)} ({person_id})"


class _PlanWorker(QThread):
    """Runs ``build_plan`` off the GUI thread."""

    built = Signal(int, object, object)  # generation, plan or None, error or None

    def __init__(self, generation: int, job: Callable[[], MergePlan], parent: Any = None) -> None:
        super().__init__(parent)
        self._generation = generation
        self._job = job

    def run(self) -> None:
        try:
            self.built.emit(self._generation, self._job(), None)
        except Exception as exc:  # noqa: BLE001 - reported as an unavailable preview
            self.built.emit(self._generation, None, exc)


class _ExecWorker(QThread):
    """Runs the disk phase of the merge off the GUI thread."""

    finished_with = Signal(object, object)  # token or None, error or None

    def __init__(self, job: Callable[[], Any], parent: Any = None) -> None:
        super().__init__(parent)
        self._job = job

    def run(self) -> None:
        try:
            self.finished_with.emit(self._job(), None)
        except Exception as exc:  # noqa: BLE001 - reported as a failed merge
            self.finished_with.emit(None, exc)


class UnsavedEditorsDialog(QDialog):
    """Blocking message naming each editor with unsaved changes (Requirement 26.14).

    Offers "Gå till redigeraren" per editor and nothing else that saves or
    discards: the editor asks the user itself.
    """

    def __init__(self, editors: Sequence[Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)
        layout = QVBoxLayout(self)
        self.buttons: list[QPushButton] = []
        self._rows: list[tuple[Any, QLabel, QPushButton]] = []
        for editor in editors:
            label = self._label(EDITOR_BLOCK_TEXT.format(title=editor.editor_title))
            layout.addWidget(label)
            button = QPushButton(GO_TO_EDITOR_TEXT)
            button.setAccessibleName(f"{GO_TO_EDITOR_TEXT}: {editor.editor_title}")
            button.clicked.connect(lambda _c=False, e=editor: self._resolve(e))
            layout.addWidget(button)
            self.buttons.append(button)
            self._rows.append((editor, label, button))
        close = QPushButton("Stäng")
        close.clicked.connect(self.accept)
        layout.addWidget(close)

    def _resolve(self, editor: Any) -> None:
        """Let the editor ask the user, then re-check every listed editor."""
        editor.request_resolution()
        self.refresh()

    def refresh(self) -> None:
        """Hide rows of editors that no longer hold unsaved changes; close when none remain."""
        remaining = 0
        for editor, label, button in self._rows:
            unsaved = bool(editor.has_unsaved_changes())
            label.setVisible(unsaved)
            button.setVisible(unsaved)
            remaining += unsaved
        if remaining == 0:
            self.accept()

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        return label


class MergeReviewWizard(QDialog):
    """Review two persons and start a merge through the executor.

    Args:
        project_service: Owner of the project data.
        person_ids: Exactly two person ids.
        editor_registry: Registry of open editors, or None.
        executor: Engine adapter; defaults to the registered executor.
        translation_provider: Returns the translation data for planning.
        use_worker: Build plans on a worker thread (tests may pass False).
    """

    def __init__(
        self,
        project_service: ProjectService,
        person_ids: Sequence[str],
        editor_registry: Optional[EditorRegistry] = None,
        executor: Optional[MergeExecutor] = None,
        translation_provider: Optional[Callable[[], Any]] = None,
        use_worker: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        ids = list(person_ids)
        if len(ids) != 2:
            raise MergeRefusal("Exakt två personer krävs för en sammanslagning.")
        self._service = project_service
        self._ids = (ids[0], ids[1])
        self._registry = editor_registry
        self._executor = executor
        self._translation_provider = translation_provider or (lambda: None)
        self._use_worker = use_worker

        self._survivor: Optional[str] = None
        self._survivor_confirmed = False
        self._choices: dict[str, str] = {}
        self._notes_mode = rules.NOTES_CONCATENATE
        self._section_confirmed: list[bool] = [False] * len(SECTION_DEFS)
        self._plan: Optional[MergePlan] = None
        self._generation = 0
        self._workers: list[_PlanWorker] = []
        self._needs_reconfirm = False
        self._name_keys: dict[str, tuple] = {}
        self._remove_listener: Optional[Callable[[], None]] = None
        self.executed = False
        self.last_result: Optional[MergeExecutionResult] = None
        self._busy = False
        self._finishing = False
        self._exec_worker: Optional[_ExecWorker] = None

        self.setWindowTitle(WINDOW_TITLE)
        self.setModal(True)
        self.resize(1000, 650)
        self._build_ui()
        self._remove_listener = self._service.add_merge_listener(self._on_project_changed)
        self._update_section_states()
        self._rebuild_plan()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        body = QHBoxLayout()
        self.section_list = QListWidget()
        self.section_list.setAccessibleName("Avsnitt i sammanslagningen")
        self.section_list.setFixedWidth(240)
        body.addWidget(self.section_list)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        outer.addLayout(body)

        describe = lambda pid: person_text(self._service, pid)  # noqa: E731
        self.survivor_page = SurvivorPage(self._ids, describe)
        self.survivor_page.selection_changed.connect(self._on_survivor_selected)
        self.survivor_page.confirmed.connect(self._on_survivor_confirmed)
        self._add_page(SURVIVOR_SECTION_TITLE, self.survivor_page)

        self.section_pages: list[SectionPage] = []
        for index, (sid, title, sections, categories) in enumerate(SECTION_DEFS):
            page = SectionPage(sid, title, sections, categories)
            page.choice_made.connect(self._on_choice_made)
            page.notes_mode_changed.connect(self._on_notes_mode)
            page.confirmed.connect(lambda i=index: self._on_section_confirmed(i))
            self.section_pages.append(page)
            self._add_page(title, page)

        self.preview = MergePreviewWidget(describe)
        self.preview.execute_requested.connect(self._on_execute)
        self.preview.reconfirm_requested.connect(self._on_reconfirm)
        self._add_page(PREVIEW_TITLE, self.preview)
        self.section_list.currentRowChanged.connect(self._on_section_row)
        self.section_list.setCurrentRow(0)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.cancel_button = QPushButton(CANCEL_TEXT)
        self.cancel_button.clicked.connect(self.reject)
        bottom.addWidget(self.cancel_button)
        outer.addLayout(bottom)
        self._overlay = ProgressOverlay(self)

    def _add_page(self, title: str, page: QWidget) -> None:
        self.section_list.addItem(QListWidgetItem(title))
        self.stack.addWidget(page)

    def _on_section_row(self, row: int) -> None:
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    def _update_section_states(self) -> None:
        """Sections open in order; a section needs the previous one confirmed (20.10)."""
        unlocked = self._survivor_confirmed
        for row in range(self.section_list.count()):
            item = self.section_list.item(row)
            if row == 0:
                enabled = True
            else:
                enabled = unlocked
                if row <= len(self._section_confirmed):
                    unlocked = unlocked and self._section_confirmed[row - 1]
            flags = item.flags()
            item.setFlags(flags | Qt.ItemFlag.ItemIsEnabled if enabled else flags & ~Qt.ItemFlag.ItemIsEnabled)
        self.survivor_page.set_confirm_enabled(self._survivor is not None)

    def is_section_enabled(self, row: int) -> bool:
        return bool(self.section_list.item(row).flags() & Qt.ItemFlag.ItemIsEnabled)

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    def _on_survivor_selected(self, person_id: str) -> None:
        if person_id == self._survivor:
            return
        had_work = self._survivor_confirmed or bool(self._choices)
        self._survivor = person_id
        self._survivor_confirmed = False
        self._choices.clear()
        self._notes_mode = rules.NOTES_CONCATENATE
        self._section_confirmed = [False] * len(SECTION_DEFS)
        self._needs_reconfirm = False
        for page in self.section_pages:
            page.reset()
        self.survivor_page.show_reset_message(had_work)
        self._update_section_states()
        self._rebuild_plan()

    def _on_survivor_confirmed(self) -> None:
        if self._survivor is None:
            return
        self._survivor_confirmed = True
        self.survivor_page.show_reset_message(False)
        self._update_section_states()
        self._rebuild_plan()
        self.section_list.setCurrentRow(1)

    def _on_choice_made(self, key: str, value: str) -> None:
        if self._choices.get(key) == value:
            return
        self._choices[key] = value
        self._rebuild_plan()

    def _on_notes_mode(self, mode: str) -> None:
        self._notes_mode = mode
        self._rebuild_plan()

    def _on_section_confirmed(self, index: int) -> None:
        self._section_confirmed[index] = True
        self._update_section_states()
        self.section_list.setCurrentRow(index + 2)

    def build_decisions(self) -> MergeDecisions:
        """The decisions for the current choices (survivor never defaulted)."""
        c = self._choices
        roles = {
            k.split(":", 1)[1]: v for k, v in c.items() if k.startswith("participant_role:")
        }
        primary = self._name_keys.get(c.get("primary_name", ""))
        return MergeDecisions(
            first_person_id=self._ids[0],
            second_person_id=self._ids[1],
            survivor_id=self._survivor,
            survivor_confirmed=self._survivor_confirmed,
            sex=c.get("sex"),
            title_from=c.get("title"),
            occupation_from=c.get("occupation"),
            profile_media_id=c.get("profile_media_id"),
            notes_mode=self._notes_mode,
            primary_name=primary,
            participant_roles=roles,
            connection_override=c.get("connection_override"),
        )

    # ------------------------------------------------------------------
    # Plan building
    # ------------------------------------------------------------------

    @property
    def plan(self) -> Optional[MergePlan]:
        return self._plan

    def _rebuild_plan(self) -> None:
        self._generation += 1
        generation = self._generation
        self.preview.set_building(True)
        data = self._service.data
        translation = self._translation_provider()
        revision = self._service.content_revision
        decisions = self.build_decisions()

        def job() -> MergePlan:
            return build_plan(data, translation, decisions, revision)

        if not self._use_worker:
            try:
                self._on_built(generation, job(), None)
            except Exception as exc:  # noqa: BLE001
                self._on_built(generation, None, exc)
            return
        worker = _PlanWorker(generation, job, self)
        worker.built.connect(self._on_built)
        worker.finished.connect(lambda w=worker: self._discard_worker(w))
        self._workers.append(worker)
        worker.start()

    def _discard_worker(self, worker: _PlanWorker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()

    def wait_for_plan(self, timeout_ms: int = 10000) -> None:
        """Block until running plan builds have finished (used by tests)."""
        for worker in list(self._workers):
            worker.wait(timeout_ms)

    def _on_built(self, generation: int, plan: Optional[MergePlan], error: Optional[Exception]) -> None:
        if generation != self._generation:
            return  # a newer build is on its way
        if error is not None or plan is None:
            if error is not None and not isinstance(error, (MergePlanError, MergeRefusal)):
                logger.exception("Förhandsgranskningen kunde inte byggas.", exc_info=error)
            self._plan = None
            self.preview.set_plan(None, unavailable=True)
            return
        self._plan = plan
        self.preview.set_plan(plan)
        if self._needs_reconfirm:
            self.preview.set_stale(True)
        self._refresh_pages(plan)

    def _refresh_pages(self, plan: MergePlan) -> None:
        specs = []
        if plan.survivor_id and plan.retired_id:
            data = self._service.data
            by_id = {p.id: p for p in data.persons}
            survivor, retired = by_id[plan.survivor_id], by_id[plan.retired_id]
            union = rules.union_names(survivor.names, retired.names)
            self._name_keys = {str(i): rules.name_identity(n) for i, n in enumerate(union)}
            name_options = [
                (str(i), f"{n.given} {n.surname}".strip() + f" ({n.type})")
                for i, n in enumerate(union)
            ]
            specs = build_choice_specs(
                plan.unresolved,
                lambda pid: person_text(self._service, pid),
                plan.survivor_id,
                plan.retired_id,
                {survivor.id: survivor.profile_media_id, retired.id: retired.profile_media_id},
                name_options,
            )
        for page in self.section_pages:
            page.show_plan(plan, specs, self._choices)

    # ------------------------------------------------------------------
    # Project changes while open (26.9)
    # ------------------------------------------------------------------

    def _plan_is_current(self) -> bool:
        return self._plan is not None and self._plan.content_revision == self._service.content_revision

    def _on_project_changed(self) -> None:
        """A save changes ``revision`` only, so it never lands here as stale."""
        if self._finishing or self._plan is None or self._plan_is_current():
            return
        self._needs_reconfirm = True
        self.preview.set_stale(True)
        self._rebuild_plan()

    def _on_reconfirm(self) -> None:
        self._needs_reconfirm = False
        if self._plan is not None:
            self.preview.set_plan(self._plan)

    def _fingerprint_unchanged(self) -> bool:
        plan = self._plan
        if plan is None:
            return False
        data = self._service.data
        translation = self._translation_provider()
        index = pri.PersonReferenceIndex.build(data, plan.decisions.person_ids, translation)
        return compute_fingerprint(data, plan.decisions.person_ids, index, translation) == plan.fingerprint

    # ------------------------------------------------------------------
    # Execution (Saved_State_Precondition, 26.6, 26.11 to 26.14, then 26.7)
    # ------------------------------------------------------------------

    def _show_editor_block(self, editors: Sequence[Any]) -> None:
        UnsavedEditorsDialog(editors, self).exec()

    def _ask_save_choice(self) -> str:
        box = QMessageBox(self)
        box.setWindowTitle(WINDOW_TITLE)
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(SAVE_PROMPT_TEXT)
        save = box.addButton(SAVE_AND_CONTINUE_TEXT, QMessageBox.ButtonRole.AcceptRole)
        box.addButton(CANCEL_TEXT, QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return SAVE if box.clickedButton() is save else CANCEL

    def _confirm_merge(self, text: str) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(WINDOW_TITLE)
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(text)
        yes = box.addButton(CONFIRM_MERGE_TEXT, QMessageBox.ButtonRole.AcceptRole)
        box.addButton(CANCEL_TEXT, QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is yes

    def _show_message(self, text: str) -> None:
        QMessageBox.warning(self, WINDOW_TITLE, text)

    def check_saved_state(self) -> bool:
        """Run the Saved_State_Precondition. True when the merge may proceed."""
        if self._registry is not None:
            editors = self._registry.unsaved_editors()
            if editors:
                self._show_editor_block(editors)
                if self._registry.unsaved_editors():
                    return False  # no "Spara och fortsätt", no second confirmation
        if not self._service.is_saved_state():
            if self._ask_save_choice() != SAVE:
                return False  # back to the preview, decisions intact
            try:
                self._service.save_project()
            except Exception:  # noqa: BLE001 - reported to the user, nothing merged
                logger.exception("Projektet kunde inte sparas före sammanslagning.")
                self._show_message(SAVE_FAILED_TEXT)
                return False
            if not self._plan_is_current() or not self._fingerprint_unchanged():
                self._needs_reconfirm = True
                self.preview.set_stale(True)
                self._rebuild_plan()
                return False
        return True

    def _on_execute(self) -> None:
        plan = self._plan
        if plan is None or not self.preview.can_execute():
            return
        if not self.check_saved_state():
            return
        plan = self._plan
        if plan is None or not self.preview.can_execute() or plan.survivor_id is None:
            return
        question = CONFIRM_QUESTION.format(
            survivor=person_text(self._service, plan.survivor_id),
            retired=person_text(self._service, plan.retired_id or ""),
        )
        if not self._confirm_merge(question):
            return
        executor = self._executor or get_merge_executor()
        if executor is None:
            self._show_message(MERGE_FAILED_TEXT)
            return
        if self._use_worker and hasattr(executor, "run_disk_phase") and hasattr(executor, "finish"):
            self._start_background_execution(executor, plan)
            return
        self._handle_result(executor.execute(plan))

    def _start_background_execution(self, executor: Any, plan: MergePlan) -> None:
        """Disk phase on a worker behind a progress overlay without cancel (27.11)."""
        self._set_busy(True)
        worker = _ExecWorker(lambda: executor.run_disk_phase(plan), self)

        def on_done(token: Any, error: Any) -> None:
            self._exec_worker = None
            try:
                if error is not None:
                    logger.error("Sammanslagningen misslyckades på arbetstråden.", exc_info=error)
                    result = MergeExecutionResult(False, MERGE_FAILED_TEXT)
                else:
                    self._finishing = True  # our own adoption is not a foreign change
                    result = executor.finish(token)  # adoption on the UI thread
            except Exception:  # noqa: BLE001
                logger.exception("Sammanslagningen kunde inte slutföras.")
                result = MergeExecutionResult(False, MERGE_FAILED_TEXT)
            self._finishing = False
            self._set_busy(False)
            self._handle_result(result)

        worker.finished_with.connect(on_done)
        worker.finished.connect(worker.deleteLater)
        self._exec_worker = worker
        worker.start()

    def wait_for_execution(self, timeout_ms: int = 10000) -> None:
        """Block until a running commit worker has finished (used by tests)."""
        worker = self._exec_worker
        if worker is not None:
            worker.wait(timeout_ms)

    @property
    def is_busy(self) -> bool:
        return self._busy

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for widget in (self.section_list, self.stack, self.preview, self.cancel_button):
            widget.setEnabled(not busy)
        if busy:
            self._overlay.show_with_message(COMMIT_PROGRESS_TEXT)
        else:
            self._overlay.hide()

    def _handle_result(self, result: MergeExecutionResult) -> None:
        self.last_result = result
        if result.refusal_message:
            show_recovery_refusal(self, result.refusal_message)
            self.reject()
            return
        if not result.success:
            text = result.message or MERGE_FAILED_TEXT
            if result.recovery_message and result.recovery_message not in text:
                text = f"{text}\n{result.recovery_message}"
            self._show_message(text)
            return
        self.executed = True
        self.accept()

    def reject(self) -> None:
        if self._busy:
            return  # no cancel while the commit runs
        super().reject()

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        if self._busy:
            event.ignore()
            return
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Closing
    # ------------------------------------------------------------------

    def done(self, result: int) -> None:
        self._generation += 1  # ignore results of builds still running
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
        for worker in list(self._workers):
            worker.wait(5000)
        super().done(result)
