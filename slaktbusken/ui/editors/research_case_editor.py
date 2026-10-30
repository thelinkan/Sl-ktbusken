"""Research case editor.

Edits one research case together with all of its hypotheses, hypothesis
comments and actions in a single widget. While it is open the editor changes a
deep-copied working copy and nothing else; ``ProjectData`` is written only by a
successful, validated :meth:`ResearchCaseEditor.try_save`, which commits the
whole graph in one step. Cancelling, or a failed save, leaves the project
exactly as it was.

The rules (completion, ordering, primary entity, closing warning) live in
``slaktbusken.services.research_editing``; this widget is a thin layer over
them. The host (a dialog or window) connects ``save_requested`` and
``cancel_requested`` to close itself.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.event import SourceRef
from slaktbusken.model.research_case import (
    ResearchAction,
    ResearchEntityLink,
    ResearchHypothesis,
    case_entity_links,
    is_pending,
)
from slaktbusken.services.project_service import ProjectService, ValidationError
from slaktbusken.services.research_editing import (
    CLOSED_CASE_PENDING_INFO,
    WorkingCopyIdAllocator,
    add_action,
    add_comment,
    add_hypothesis,
    add_link,
    closing_warning_count,
    closing_warning_text,
    completed_actions,
    demote_primary,
    new_case_working_copy,
    pending_actions,
    remove_link,
    reorder_pending,
    set_action_completed,
    set_action_completed_date,
    set_primary,
)
from slaktbusken.services.research_entities import (
    LINKABLE_ENTITY_TYPES,
    MISSING_ENTITY_MARKER,
    entity_label,
)
from slaktbusken.services.research_service import (
    ResearchCaseWorkingCopy,
    open_working_copy,
)
from slaktbusken.ui.dialogs.delete_research_case_dialog import confirm_and_delete_case
from slaktbusken.ui.dialogs.entity_picker_dialog import EntityPickerDialog
from slaktbusken.ui.swedish_locale import (
    HYPOTHESIS_ASSESSMENT_LABELS,
    RESEARCH_PRIORITY_LABELS,
    RESEARCH_STATUS_LABELS,
    get_research_entity_type_label,
)

_NO_TITLE = "(utan rubrik)"
_ROLE_ID = Qt.ItemDataRole.UserRole
_ROLE_TYPE = Qt.ItemDataRole.UserRole + 1


class ResearchCaseEditor(QWidget):
    """Editor for one research case and everything that belongs to it.

    Signals:
        save_requested(str): Emitted with the case id after a successful commit.
        cancel_requested: Emitted when the user cancels; nothing was written.
        open_entity_requested(str, str): Emitted with ``(entity_type, entity_id)``
            when the user asks to go to a linked entity. The editor keeps its
            unsaved edits.

    Args:
        project_service: The open project.
        case_id: The case to edit, or None to start a new one.
        primary: For a new case, the entity to prepopulate as primary entity.
        parent: Optional parent widget.

    Raises:
        KeyError: If *case_id* names no case.
    """

    save_requested = Signal(str)
    cancel_requested = Signal()
    open_entity_requested = Signal(str, str)
    deleted = Signal(str)

    def __init__(
        self,
        project_service: ProjectService,
        case_id: Optional[str] = None,
        primary: Optional[ResearchEntityLink] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._service = project_service
        data = project_service.data
        if case_id is None:
            self._wc: ResearchCaseWorkingCopy = new_case_working_copy(data, primary)
        else:
            self._wc = open_working_copy(data, case_id)
        self._alloc = WorkingCopyIdAllocator(data, self._wc)
        self._status_before = self._wc.case.status
        self._loading = False
        self._current_action: Optional[ResearchAction] = None
        self._current_hypothesis: Optional[ResearchHypothesis] = None

        self._setup_ui()
        self._load_all()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def working_copy(self) -> ResearchCaseWorkingCopy:
        """The case, hypotheses and actions being edited (never the project's own)."""
        return self._wc

    def try_save(self) -> bool:
        """Validate and commit the working copy.

        Returns:
            True when committed (``save_requested`` is emitted). False when
            validation failed: the messages are shown, nothing was written and
            the editor keeps the user's edits.
        """
        self._finish_pending_edits()
        case = self._wc.case
        case.title = case.title.strip()
        for hypothesis in self._wc.hypotheses:
            for comment in hypothesis.comments:
                comment.date = comment.date.strip()
        try:
            self._service.commit_research_case_working_copy(self._wc)
        except ValidationError as error:
            self._show_errors(error.errors)
            return False
        self._show_errors([])
        self.save_requested.emit(case.id)
        return True

    def cancel(self) -> None:
        """Discard the working copy; the project was never touched."""
        self.cancel_requested.emit()

    def delete_case(self, ask=None) -> bool:
        """Delete the whole case after the shared confirmation.

        Unsaved edits are discarded with the case. Cancelling the confirmation
        leaves the case and the editor as they are.

        Returns:
            True if the case was deleted (``deleted`` is emitted).
        """
        case_id = self._wc.case.id
        if not confirm_and_delete_case(self, self._service, case_id, ask):
            return False
        self.deleted.emit(case_id)
        return True

    def select_action(self, action_id: str) -> bool:
        """Select an action in its list so the user lands on it; False if absent."""
        if self._find_action(action_id) is None:
            return False
        self._rebuild_actions(select_id=action_id)
        return True

    def set_status(self, status: str) -> bool:
        """Change the status as the combo would, asking first when closing.

        Returns:
            True if the status was applied, False if the user went back.
        """
        old = self._wc.case.status
        count = closing_warning_count(old, status, self._wc.actions)
        if count and not self._confirm_close_with_pending(count):
            self._set_combo_data(self._status_combo, old)
            return False
        self._wc.case.status = status
        self._status_before = status
        self._set_combo_data(self._status_combo, status)
        return True

    def add_pending_action(self, title: str = "") -> ResearchAction:
        """Add a pending action; informs the user when the case is closed."""
        action = add_action(self._wc, self._alloc, title)
        if self._wc.case.status == "closed":
            self._show_closed_case_info()
        self._rebuild_actions(select_id=action.id)
        return action

    # Overridable dialogs (tests replace these)

    def _confirm_close_with_pending(self, count: int) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Forskningsärendet har öppna åtgärder")
        box.setText(closing_warning_text(count))
        go_back = box.addButton("Gå tillbaka", QMessageBox.ButtonRole.RejectRole)
        close_anyway = box.addButton("Avsluta ändå", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(go_back)
        box.exec()
        return box.clickedButton() is close_anyway

    def _show_closed_case_info(self) -> None:
        QMessageBox.information(self, "Avslutat ärende", CLOSED_CASE_PENDING_INFO)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        # --- Frågeställning, status, priority -------------------------
        head = QGroupBox("Frågeställning")
        head_form = QFormLayout(head)
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Rubrik")
        self._title_edit.textChanged.connect(self._on_title_changed)
        head_form.addRow("Rubrik:", self._title_edit)
        self._description_edit = QPlainTextEdit()
        self._description_edit.setFixedHeight(80)
        self._description_edit.textChanged.connect(self._on_description_changed)
        head_form.addRow("Frågeställning:", self._description_edit)
        self._status_combo = QComboBox()
        for key, label in RESEARCH_STATUS_LABELS.items():
            self._status_combo.addItem(label, key)
        self._status_combo.activated.connect(self._on_status_activated)
        head_form.addRow("Status:", self._status_combo)
        self._priority_combo = QComboBox()
        for key, label in RESEARCH_PRIORITY_LABELS.items():
            self._priority_combo.addItem(label, key)
        self._priority_combo.activated.connect(self._on_priority_activated)
        head_form.addRow("Prioritet:", self._priority_combo)
        body_layout.addWidget(head)

        # --- Berörda objekt -------------------------------------------
        links_box = QGroupBox("Berörda objekt")
        links_layout = QVBoxLayout(links_box)
        self._links_list = QListWidget()
        self._links_list.itemSelectionChanged.connect(self._update_link_buttons)
        links_layout.addWidget(self._links_list)
        links_buttons = QHBoxLayout()
        self._add_link_button = QPushButton("Lägg till objekt...")
        self._remove_link_button = QPushButton("Ta bort kopplingen")
        self._primary_button = QPushButton("Gör till huvudobjekt")
        self._unprimary_button = QPushButton("Ta bort huvudobjekt")
        self._goto_button = QPushButton("Gå till objektet")
        for button in (
            self._add_link_button,
            self._remove_link_button,
            self._primary_button,
            self._unprimary_button,
            self._goto_button,
        ):
            links_buttons.addWidget(button)
        links_buttons.addStretch()
        links_layout.addLayout(links_buttons)
        self._add_link_button.clicked.connect(self._on_add_link)
        self._remove_link_button.clicked.connect(self._on_remove_link)
        self._primary_button.clicked.connect(self._on_make_primary)
        self._unprimary_button.clicked.connect(self._on_clear_primary)
        self._goto_button.clicked.connect(self._on_goto_entity)
        body_layout.addWidget(links_box)

        # --- Hypoteser ------------------------------------------------
        hyp_box = QGroupBox("Hypoteser")
        hyp_layout = QVBoxLayout(hyp_box)
        self._hyp_list = QListWidget()
        self._hyp_list.setFixedHeight(90)
        self._hyp_list.itemSelectionChanged.connect(self._on_hypothesis_selected)
        hyp_layout.addWidget(self._hyp_list)
        hyp_buttons = QHBoxLayout()
        self._add_hyp_button = QPushButton("Ny hypotes")
        self._remove_hyp_button = QPushButton("Ta bort hypotesen")
        hyp_buttons.addWidget(self._add_hyp_button)
        hyp_buttons.addWidget(self._remove_hyp_button)
        hyp_buttons.addStretch()
        hyp_layout.addLayout(hyp_buttons)
        self._add_hyp_button.clicked.connect(self._on_add_hypothesis)
        self._remove_hyp_button.clicked.connect(self._on_remove_hypothesis)

        self._hyp_detail = QWidget()
        hyp_form = QFormLayout(self._hyp_detail)
        self._hyp_statement = QLineEdit()
        self._hyp_statement.textChanged.connect(self._on_hyp_statement_changed)
        hyp_form.addRow("Hypotes:", self._hyp_statement)
        self._hyp_assessment = QComboBox()
        for key, label in HYPOTHESIS_ASSESSMENT_LABELS.items():
            self._hyp_assessment.addItem(label, key)
        self._hyp_assessment.activated.connect(self._on_hyp_assessment_activated)
        hyp_form.addRow("Bedömning:", self._hyp_assessment)
        self._hyp_reasoning = QPlainTextEdit()
        self._hyp_reasoning.setFixedHeight(70)
        self._hyp_reasoning.textChanged.connect(self._on_hyp_reasoning_changed)
        hyp_form.addRow("Resonemang:", self._hyp_reasoning)

        self._hyp_entities = QListWidget()
        self._hyp_entities.setFixedHeight(60)
        hyp_form.addRow("Nämnda objekt:", self._hyp_entities)
        hyp_ent_buttons = QHBoxLayout()
        self._hyp_add_entity = QPushButton("Lägg till objekt...")
        self._hyp_remove_entity = QPushButton("Ta bort kopplingen")
        hyp_ent_buttons.addWidget(self._hyp_add_entity)
        hyp_ent_buttons.addWidget(self._hyp_remove_entity)
        hyp_ent_buttons.addStretch()
        hyp_form.addRow("", hyp_ent_buttons)
        self._hyp_add_entity.clicked.connect(self._on_hyp_add_entity)
        self._hyp_remove_entity.clicked.connect(self._on_hyp_remove_entity)

        self._comments_list = QListWidget()
        self._comments_list.setFixedHeight(80)
        self._comments_list.itemSelectionChanged.connect(self._on_comment_selected)
        hyp_form.addRow("Kommentarer:", self._comments_list)
        self._comment_date = QLineEdit()
        self._comment_date.setPlaceholderText("ÅÅÅÅ-MM-DD")
        self._comment_date.textChanged.connect(self._on_comment_date_changed)
        hyp_form.addRow("Datum:", self._comment_date)
        self._comment_text = QPlainTextEdit()
        self._comment_text.setFixedHeight(60)
        self._comment_text.textChanged.connect(self._on_comment_text_changed)
        hyp_form.addRow("Text:", self._comment_text)
        comment_buttons = QHBoxLayout()
        self._add_comment_button = QPushButton("Ny kommentar")
        self._remove_comment_button = QPushButton("Ta bort kommentaren")
        comment_buttons.addWidget(self._add_comment_button)
        comment_buttons.addWidget(self._remove_comment_button)
        comment_buttons.addStretch()
        hyp_form.addRow("", comment_buttons)
        self._add_comment_button.clicked.connect(self._on_add_comment)
        self._remove_comment_button.clicked.connect(self._on_remove_comment)
        hyp_layout.addWidget(self._hyp_detail)
        body_layout.addWidget(hyp_box)

        # --- Actions ----------------------------------------------------
        pending_box = QGroupBox("Nästa åtgärder")
        pending_layout = QVBoxLayout(pending_box)
        self._pending_list = QListWidget()
        self._pending_list.setFixedHeight(100)
        self._pending_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._pending_list.itemSelectionChanged.connect(
            lambda: self._on_action_list_selected(self._pending_list, self._done_list)
        )
        self._pending_list.model().rowsMoved.connect(self._on_pending_reordered)
        pending_layout.addWidget(self._pending_list)
        pending_buttons = QHBoxLayout()
        self._add_action_button = QPushButton("Ny åtgärd")
        self._remove_action_button = QPushButton("Ta bort åtgärden")
        pending_buttons.addWidget(self._add_action_button)
        pending_buttons.addWidget(self._remove_action_button)
        pending_buttons.addStretch()
        pending_layout.addLayout(pending_buttons)
        self._add_action_button.clicked.connect(lambda: self.add_pending_action())
        self._remove_action_button.clicked.connect(self._on_remove_action)
        body_layout.addWidget(pending_box)

        done_box = QGroupBox("Genomförda åtgärder")
        done_layout = QVBoxLayout(done_box)
        self._done_list = QListWidget()
        self._done_list.setFixedHeight(100)
        self._done_list.itemSelectionChanged.connect(
            lambda: self._on_action_list_selected(self._done_list, self._pending_list)
        )
        done_layout.addWidget(self._done_list)
        body_layout.addWidget(done_box)

        self._action_detail = QGroupBox("Vald åtgärd")
        action_form = QFormLayout(self._action_detail)
        self._action_title = QLineEdit()
        self._action_title.textChanged.connect(self._on_action_title_changed)
        action_form.addRow("Rubrik:", self._action_title)
        self._action_text = QPlainTextEdit()
        self._action_text.setFixedHeight(70)
        self._action_text.textChanged.connect(self._on_action_text_changed)
        action_form.addRow("Text:", self._action_text)
        self._action_done = QCheckBox("Åtgärden genomförd")
        self._action_done.clicked.connect(self._on_action_done_clicked)
        action_form.addRow("", self._action_done)
        self._action_date = QLineEdit()
        self._action_date.setPlaceholderText("ÅÅÅÅ-MM-DD")
        self._action_date.editingFinished.connect(self._on_action_date_finished)
        action_form.addRow("Färdigdatum:", self._action_date)
        self._action_sources = QListWidget()
        self._action_sources.setFixedHeight(60)
        action_form.addRow("Granskade källor:", self._action_sources)
        source_buttons = QHBoxLayout()
        self._add_source_button = QPushButton("Lägg till granskad källa...")
        self._remove_source_button = QPushButton("Ta bort källan")
        source_buttons.addWidget(self._add_source_button)
        source_buttons.addWidget(self._remove_source_button)
        source_buttons.addStretch()
        action_form.addRow("", source_buttons)
        self._add_source_button.clicked.connect(self._on_add_source)
        self._remove_source_button.clicked.connect(self._on_remove_source)
        body_layout.addWidget(self._action_detail)

        # --- Slutsats ---------------------------------------------------
        conclusion_box = QGroupBox("Slutsats")
        conclusion_layout = QVBoxLayout(conclusion_box)
        self._conclusion_edit = QPlainTextEdit()
        self._conclusion_edit.setFixedHeight(80)
        self._conclusion_edit.textChanged.connect(self._on_conclusion_changed)
        conclusion_layout.addWidget(self._conclusion_edit)
        body_layout.addWidget(conclusion_box)
        body_layout.addStretch()

        # --- Errors and buttons ----------------------------------------
        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("color: #C0392B;")
        self._error_label.setVisible(False)
        outer.addWidget(self._error_label)

        buttons = QHBoxLayout()
        self._delete_button = QPushButton("Ta bort forskningsärendet...")
        # Only a case that exists in the project can be deleted.
        self._delete_button.setEnabled(
            any(c.id == self._wc.case.id for c in self._service.data.research_cases)
        )
        self._delete_button.clicked.connect(lambda _checked=False: self.delete_case())
        buttons.addWidget(self._delete_button)
        buttons.addStretch()
        self._save_button = QPushButton("Spara")
        self._cancel_button = QPushButton("Avbryt")
        buttons.addWidget(self._save_button)
        buttons.addWidget(self._cancel_button)
        outer.addLayout(buttons)
        self._save_button.clicked.connect(self.try_save)
        self._cancel_button.clicked.connect(self.cancel)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @staticmethod
    def _set_combo_data(combo: QComboBox, key: str) -> None:
        index = combo.findData(key)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _load_all(self) -> None:
        self._loading = True
        try:
            case = self._wc.case
            self._title_edit.setText(case.title)
            self._description_edit.setPlainText(case.description)
            self._set_combo_data(self._status_combo, case.status)
            self._set_combo_data(self._priority_combo, case.priority)
            self._conclusion_edit.setPlainText(case.conclusion)
        finally:
            self._loading = False
        self._rebuild_links()
        self._rebuild_hypotheses()
        self._rebuild_actions()

    # ------------------------------------------------------------------
    # Head fields
    # ------------------------------------------------------------------

    def _on_title_changed(self, text: str) -> None:
        if not self._loading:
            self._wc.case.title = text

    def _on_description_changed(self) -> None:
        if not self._loading:
            self._wc.case.description = self._description_edit.toPlainText()

    def _on_conclusion_changed(self) -> None:
        if not self._loading:
            self._wc.case.conclusion = self._conclusion_edit.toPlainText()

    def _on_status_activated(self, _index: int) -> None:
        self.set_status(self._status_combo.currentData())

    def _on_priority_activated(self, _index: int) -> None:
        self._wc.case.priority = self._priority_combo.currentData()

    # ------------------------------------------------------------------
    # Linked entities (case)
    # ------------------------------------------------------------------

    def _link_text(self, link: ResearchEntityLink, is_primary: bool) -> str:
        type_label = get_research_entity_type_label(link.entity_type)
        label = entity_label(self._service.data, link.entity_type, link.entity_id)
        name = label if label is not None else f"{MISSING_ENTITY_MARKER} {link.entity_id}"
        suffix = "  [huvudobjekt]" if is_primary else ""
        return f"{type_label}: {name}{suffix}"

    def _rebuild_links(self) -> None:
        self._links_list.clear()
        case = self._wc.case
        for index, link in enumerate(case_entity_links(case)):
            is_primary = case.primary_entity_ref is not None and index == 0
            item = QListWidgetItem(self._link_text(link, is_primary))
            item.setData(_ROLE_TYPE, link.entity_type)
            item.setData(_ROLE_ID, link.entity_id)
            item.setData(Qt.ItemDataRole.UserRole + 2, is_primary)
            self._links_list.addItem(item)
        self._update_link_buttons()

    def _selected_link(self) -> Optional[tuple[str, str, bool]]:
        items = self._links_list.selectedItems()
        if not items:
            return None
        item = items[0]
        return (item.data(_ROLE_TYPE), item.data(_ROLE_ID), bool(item.data(Qt.ItemDataRole.UserRole + 2)))

    def _update_link_buttons(self) -> None:
        selected = self._selected_link()
        exists = (
            selected is not None
            and entity_label(self._service.data, selected[0], selected[1]) is not None
        )
        self._remove_link_button.setEnabled(selected is not None)
        # A dangling link offers removal only.
        self._primary_button.setEnabled(exists and not selected[2])
        self._unprimary_button.setEnabled(selected is not None and selected[2])
        self._goto_button.setEnabled(exists)

    def _on_add_link(self) -> None:
        picked = EntityPickerDialog.pick(
            self._service.data, LINKABLE_ENTITY_TYPES, "Lägg till objekt", self
        )
        if picked is not None:
            self.add_case_link(*picked)

    def add_case_link(self, entity_type: str, entity_id: str) -> bool:
        """Link an entity to the case unless it is already linked."""
        added = add_link(self._wc.case, entity_type, entity_id)
        self._rebuild_links()
        return added

    def _on_remove_link(self) -> None:
        selected = self._selected_link()
        if selected is not None:
            remove_link(self._wc.case, selected[0], selected[1])
            self._rebuild_links()

    def _on_make_primary(self) -> None:
        selected = self._selected_link()
        if selected is not None:
            set_primary(self._wc.case, selected[0], selected[1])
            self._rebuild_links()

    def _on_clear_primary(self) -> None:
        demote_primary(self._wc.case)
        self._rebuild_links()

    def _on_goto_entity(self) -> None:
        selected = self._selected_link()
        if selected is not None:
            self.open_entity_requested.emit(selected[0], selected[1])

    # ------------------------------------------------------------------
    # Hypotheses
    # ------------------------------------------------------------------

    def _rebuild_hypotheses(self, select_id: Optional[str] = None) -> None:
        self._hyp_list.blockSignals(True)
        self._hyp_list.clear()
        for hypothesis in self._wc.hypotheses:
            item = QListWidgetItem(hypothesis.statement.strip() or "(utan formulering)")
            item.setData(_ROLE_ID, hypothesis.id)
            self._hyp_list.addItem(item)
            if hypothesis.id == select_id:
                self._hyp_list.setCurrentItem(item)
        self._hyp_list.blockSignals(False)
        self._on_hypothesis_selected()

    def _find_hypothesis(self, hypothesis_id: str) -> Optional[ResearchHypothesis]:
        return next((h for h in self._wc.hypotheses if h.id == hypothesis_id), None)

    def _on_hypothesis_selected(self) -> None:
        items = self._hyp_list.selectedItems()
        self._current_hypothesis = (
            self._find_hypothesis(items[0].data(_ROLE_ID)) if items else None
        )
        hypothesis = self._current_hypothesis
        self._hyp_detail.setEnabled(hypothesis is not None)
        self._remove_hyp_button.setEnabled(hypothesis is not None)
        self._loading = True
        try:
            self._hyp_statement.setText(hypothesis.statement if hypothesis else "")
            if hypothesis:
                self._set_combo_data(self._hyp_assessment, hypothesis.assessment)
            self._hyp_reasoning.setPlainText(hypothesis.reasoning if hypothesis else "")
        finally:
            self._loading = False
        self._rebuild_hyp_entities()
        self._rebuild_comments()

    def _on_add_hypothesis(self) -> None:
        hypothesis = add_hypothesis(self._wc, self._alloc)
        self._rebuild_hypotheses(select_id=hypothesis.id)

    def _on_remove_hypothesis(self) -> None:
        hypothesis = self._current_hypothesis
        if hypothesis is not None:
            self._wc.hypotheses = [h for h in self._wc.hypotheses if h.id != hypothesis.id]
            self._rebuild_hypotheses()

    def _on_hyp_statement_changed(self, text: str) -> None:
        if self._loading or self._current_hypothesis is None:
            return
        self._current_hypothesis.statement = text
        items = self._hyp_list.selectedItems()
        if items:
            items[0].setText(text.strip() or "(utan formulering)")

    def _on_hyp_assessment_activated(self, _index: int) -> None:
        if self._current_hypothesis is not None:
            self._current_hypothesis.assessment = self._hyp_assessment.currentData()

    def _on_hyp_reasoning_changed(self) -> None:
        if not self._loading and self._current_hypothesis is not None:
            self._current_hypothesis.reasoning = self._hyp_reasoning.toPlainText()

    def _rebuild_hyp_entities(self) -> None:
        self._hyp_entities.clear()
        hypothesis = self._current_hypothesis
        if hypothesis is None:
            return
        for link in hypothesis.linked_entities:
            item = QListWidgetItem(self._link_text(link, False))
            item.setData(_ROLE_TYPE, link.entity_type)
            item.setData(_ROLE_ID, link.entity_id)
            self._hyp_entities.addItem(item)

    def _on_hyp_add_entity(self) -> None:
        hypothesis = self._current_hypothesis
        if hypothesis is None:
            return
        picked = EntityPickerDialog.pick(
            self._service.data, LINKABLE_ENTITY_TYPES, "Lägg till objekt", self
        )
        if picked is None:
            return
        if not any(
            link.entity_type == picked[0] and link.entity_id == picked[1]
            for link in hypothesis.linked_entities
        ):
            hypothesis.linked_entities.append(ResearchEntityLink(picked[0], picked[1]))
        self._rebuild_hyp_entities()

    def _on_hyp_remove_entity(self) -> None:
        hypothesis = self._current_hypothesis
        items = self._hyp_entities.selectedItems()
        if hypothesis is None or not items:
            return
        entity_type, entity_id = items[0].data(_ROLE_TYPE), items[0].data(_ROLE_ID)
        hypothesis.linked_entities = [
            link
            for link in hypothesis.linked_entities
            if not (link.entity_type == entity_type and link.entity_id == entity_id)
        ]
        self._rebuild_hyp_entities()

    # --- comments ------------------------------------------------------

    def _current_comment(self):
        hypothesis = self._current_hypothesis
        items = self._comments_list.selectedItems()
        if hypothesis is None or not items:
            return None
        comment_id = items[0].data(_ROLE_ID)
        return next((c for c in hypothesis.comments if c.id == comment_id), None)

    def _rebuild_comments(self, select_id: Optional[str] = None) -> None:
        self._comments_list.blockSignals(True)
        self._comments_list.clear()
        hypothesis = self._current_hypothesis
        if hypothesis is not None:
            for comment in hypothesis.comments:
                first_line = comment.text.strip().splitlines()[0] if comment.text.strip() else ""
                item = QListWidgetItem(f"{comment.date or '(utan datum)'}: {first_line}")
                item.setData(_ROLE_ID, comment.id)
                self._comments_list.addItem(item)
                if comment.id == select_id:
                    self._comments_list.setCurrentItem(item)
        self._comments_list.blockSignals(False)
        self._on_comment_selected()

    def _on_comment_selected(self) -> None:
        comment = self._current_comment()
        self._comment_date.setEnabled(comment is not None)
        self._comment_text.setEnabled(comment is not None)
        self._remove_comment_button.setEnabled(comment is not None)
        self._add_comment_button.setEnabled(self._current_hypothesis is not None)
        self._loading = True
        try:
            self._comment_date.setText(comment.date if comment else "")
            self._comment_text.setPlainText(comment.text if comment else "")
        finally:
            self._loading = False

    def _on_add_comment(self) -> None:
        hypothesis = self._current_hypothesis
        if hypothesis is None:
            return
        comment = add_comment(hypothesis, self._alloc)
        self._rebuild_comments(select_id=comment.id)

    def _on_remove_comment(self) -> None:
        hypothesis = self._current_hypothesis
        comment = self._current_comment()
        if hypothesis is not None and comment is not None:
            hypothesis.comments = [c for c in hypothesis.comments if c.id != comment.id]
            self._rebuild_comments()

    def _refresh_comment_row(self, comment) -> None:
        items = self._comments_list.selectedItems()
        if items:
            first_line = comment.text.strip().splitlines()[0] if comment.text.strip() else ""
            items[0].setText(f"{comment.date or '(utan datum)'}: {first_line}")

    def _on_comment_date_changed(self, text: str) -> None:
        comment = self._current_comment()
        if self._loading or comment is None:
            return
        comment.date = text.strip()
        self._refresh_comment_row(comment)

    def _on_comment_text_changed(self) -> None:
        comment = self._current_comment()
        if self._loading or comment is None:
            return
        comment.text = self._comment_text.toPlainText()
        self._refresh_comment_row(comment)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @staticmethod
    def _action_row_text(action: ResearchAction) -> str:
        title = action.title.strip() or _NO_TITLE
        if is_pending(action):
            return title
        return f"{action.completed_date}  {title}"

    def _rebuild_actions(self, select_id: Optional[str] = None) -> None:
        if select_id is None and self._current_action is not None:
            select_id = self._current_action.id
        for widget in (self._pending_list, self._done_list):
            widget.blockSignals(True)
            widget.clear()
        selected_item: Optional[tuple[QListWidget, QListWidgetItem]] = None
        for action in pending_actions(self._wc.actions):
            item = QListWidgetItem(self._action_row_text(action))
            item.setData(_ROLE_ID, action.id)
            self._pending_list.addItem(item)
            if action.id == select_id:
                selected_item = (self._pending_list, item)
        for action in completed_actions(self._wc.actions):
            item = QListWidgetItem(self._action_row_text(action))
            item.setData(_ROLE_ID, action.id)
            self._done_list.addItem(item)
            if action.id == select_id:
                selected_item = (self._done_list, item)
        if selected_item is not None:
            selected_item[0].setCurrentItem(selected_item[1])
        for widget in (self._pending_list, self._done_list):
            widget.blockSignals(False)
        self._load_action_detail(select_id if selected_item else None)

    def _find_action(self, action_id: Optional[str]) -> Optional[ResearchAction]:
        if action_id is None:
            return None
        return next((a for a in self._wc.actions if a.id == action_id), None)

    def _on_action_list_selected(self, source: QListWidget, other: QListWidget) -> None:
        items = source.selectedItems()
        if not items:
            return
        other.blockSignals(True)
        other.clearSelection()
        other.blockSignals(False)
        self._finish_pending_edits()
        self._load_action_detail(items[0].data(_ROLE_ID))

    def _load_action_detail(self, action_id: Optional[str]) -> None:
        action = self._find_action(action_id)
        self._current_action = action
        self._action_detail.setEnabled(action is not None)
        self._remove_action_button.setEnabled(action is not None)
        self._loading = True
        try:
            self._action_title.setText(action.title if action else "")
            self._action_text.setPlainText(action.text if action else "")
            done = action is not None and not is_pending(action)
            self._action_done.setChecked(done)
            self._action_date.setText(action.completed_date or "" if action else "")
            self._action_date.setVisible(done)
        finally:
            self._loading = False
        self._rebuild_action_sources()

    def _finish_pending_edits(self) -> None:
        """Apply a date typed but not yet confirmed with Enter or focus loss."""
        action = self._current_action
        if action is not None and not is_pending(action) and not self._loading:
            if self._action_date.text() != (action.completed_date or ""):
                self._apply_action_date(self._action_date.text())

    def _on_action_title_changed(self, text: str) -> None:
        action = self._current_action
        if self._loading or action is None:
            return
        action.title = text
        for widget in (self._pending_list, self._done_list):
            for row in range(widget.count()):
                item = widget.item(row)
                if item.data(_ROLE_ID) == action.id:
                    item.setText(self._action_row_text(action))

    def _on_action_text_changed(self) -> None:
        action = self._current_action
        if not self._loading and action is not None:
            action.text = self._action_text.toPlainText()

    def _on_action_done_clicked(self, checked: bool) -> None:
        action = self._current_action
        if action is None:
            return
        set_action_completed(action, checked)
        self._rebuild_actions(select_id=action.id)

    def _on_action_date_finished(self) -> None:
        if self._loading:
            return
        self._apply_action_date(self._action_date.text())

    def _apply_action_date(self, text: str) -> None:
        action = self._current_action
        if action is None:
            return
        set_action_completed_date(action, text)
        self._rebuild_actions(select_id=action.id)

    def _on_pending_reordered(self, *_args) -> None:
        ids = [
            self._pending_list.item(row).data(_ROLE_ID)
            for row in range(self._pending_list.count())
        ]
        reorder_pending(self._wc, ids)

    def _on_remove_action(self) -> None:
        action = self._current_action
        if action is not None:
            self._wc.actions = [a for a in self._wc.actions if a.id != action.id]
            self._current_action = None
            self._rebuild_actions()

    # --- examined sources ----------------------------------------------

    def _rebuild_action_sources(self) -> None:
        self._action_sources.clear()
        action = self._current_action
        if action is None:
            return
        for source_ref in action.source_refs:
            label = entity_label(self._service.data, "source", source_ref.source_id)
            item = QListWidgetItem(
                label if label is not None else f"{MISSING_ENTITY_MARKER} {source_ref.source_id}"
            )
            item.setData(_ROLE_ID, source_ref.source_id)
            self._action_sources.addItem(item)

    def add_action_source(self, source_id: str) -> bool:
        """Attach an examined source to the selected action unless already attached."""
        action = self._current_action
        if action is None or any(r.source_id == source_id for r in action.source_refs):
            return False
        action.source_refs.append(SourceRef(source_id=source_id, quality="primary"))
        self._rebuild_action_sources()
        return True

    def _on_add_source(self) -> None:
        picked = EntityPickerDialog.pick(
            self._service.data, ("source",), "Lägg till granskad källa", self
        )
        if picked is not None:
            self.add_action_source(picked[1])

    def _on_remove_source(self) -> None:
        action = self._current_action
        items = self._action_sources.selectedItems()
        if action is None or not items:
            return
        source_id = items[0].data(_ROLE_ID)
        action.source_refs = [r for r in action.source_refs if r.source_id != source_id]
        self._rebuild_action_sources()

    # ------------------------------------------------------------------
    # Errors
    # ------------------------------------------------------------------

    def _show_errors(self, errors: list[str]) -> None:
        # Repeated messages (one per bad item) are listed once each.
        unique = list(dict.fromkeys(errors))
        self._error_label.setText("\n".join(unique))
        self._error_label.setVisible(bool(unique))
