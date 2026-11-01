"""Dialog for editing one merge candidate: assessment, active flag, research
case and dated comments.

Every change goes through a ``ProjectService`` candidate method and is
followed by a refresh. The comment editor at the bottom can hold unsaved text;
closing the dialog then asks whether to save, discard or stay, and the dialog
takes part in the editor registry so a merge can see the unsaved text.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.merge_candidate import (
    CANDIDATE_ASSESSMENTS,
    MAX_COMMENT_TEXT,
    MergeCandidate,
    MergeCandidateComment,
)
from slaktbusken.services.editor_registry import EditorRegistry, ResolutionResult
from slaktbusken.services.person_summary import PersonSummaryIndex
from slaktbusken.services.project_service import ProjectService, ValidationError
from slaktbusken.ui.dialogs.research_case_picker_dialog import ResearchCasePickerDialog
from slaktbusken.ui.swedish_locale import (
    get_candidate_assessment_label,
    get_candidate_section_label,
)

SAVE = "save"
DISCARD = "discard"
STAY = "stay"

MSG_NO_DATE = "kommentaren saknar datum"


def today_text() -> str:
    """Today's local date as ÅÅÅÅ-MM-DD."""
    return date.today().isoformat()


def delete_prompt_text(comment: MergeCandidateComment) -> str:
    """Confirmation text for deleting a comment, naming its date."""
    if comment.date.strip():
        return f"Vill du ta bort kommentaren daterad {comment.date}?"
    return f"Vill du ta bort kommentaren? ({MSG_NO_DATE})"


class CandidateEditorDialog(QDialog):
    """Edit a merge candidate.

    Args:
        service: The project service owning the data.
        candidate_id: Id of the candidate to edit.
        parent: Optional parent widget.
        registry: Optional editor registry; the dialog registers itself.
    """

    def __init__(
        self,
        service: ProjectService,
        candidate_id: str,
        parent: Optional[QWidget] = None,
        registry: Optional[EditorRegistry] = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._candidate_id = candidate_id
        self._editing_comment_id: Optional[str] = None
        self._baseline: tuple[str, str] = ("", "")
        self._loading = False
        self.editor_title = f"Kandidatredigerare: {candidate_id}"
        self.setWindowTitle("Sammanslagningskandidat")
        self.resize(560, 640)
        self._build_ui()
        self._start_new_comment()
        self.refresh()
        if registry is not None:
            registry.register(self)

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._persons_label = QLabel()
        self._persons_label.setWordWrap(True)
        layout.addWidget(self._persons_label)

        row = QHBoxLayout()
        row.addWidget(QLabel("Bedömning:"))
        self._assessment = QComboBox()
        for key in CANDIDATE_ASSESSMENTS:
            self._assessment.addItem(get_candidate_assessment_label(key), key)
        row.addWidget(self._assessment, 1)
        self._enabled = QCheckBox("Aktiv")
        row.addWidget(self._enabled)
        layout.addLayout(row)

        case_row = QHBoxLayout()
        self._case_label = QLabel()
        self._case_label.setWordWrap(True)
        case_row.addWidget(QLabel(get_candidate_section_label("research_case") + ":"))
        case_row.addWidget(self._case_label, 1)
        self._pick_case = QPushButton("Välj ärende…")
        self._create_case = QPushButton("Skapa forskningsärende")
        self._remove_case = QPushButton("Ta bort koppling")
        for button in (self._pick_case, self._create_case, self._remove_case):
            case_row.addWidget(button)
        layout.addLayout(case_row)

        layout.addWidget(QLabel(get_candidate_section_label("comments") + ":"))
        self._comments = QListWidget()
        layout.addWidget(self._comments, 1)
        comment_buttons = QHBoxLayout()
        self._new_button = QPushButton("Ny kommentar…")
        self._edit_button = QPushButton("Redigera")
        self._delete_button = QPushButton("Ta bort")
        for button in (self._new_button, self._edit_button, self._delete_button):
            comment_buttons.addWidget(button)
        comment_buttons.addStretch(1)
        layout.addLayout(comment_buttons)

        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("Datum (ÅÅÅÅ-MM-DD):"))
        self._date_edit = QLineEdit()
        date_row.addWidget(self._date_edit, 1)
        layout.addLayout(date_row)
        self._text_edit = QPlainTextEdit()
        self._text_edit.setFixedHeight(90)
        layout.addWidget(self._text_edit)
        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: #b00020;")
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)
        bottom = QHBoxLayout()
        self._save_button = QPushButton("Spara kommentar")
        bottom.addWidget(self._save_button)
        bottom.addStretch(1)
        self._close_button = QPushButton("Stäng")
        bottom.addWidget(self._close_button)
        layout.addLayout(bottom)

        self._assessment.currentIndexChanged.connect(self._on_assessment_changed)
        self._enabled.toggled.connect(self._on_enabled_toggled)
        self._pick_case.clicked.connect(self._on_pick_case)
        self._create_case.clicked.connect(self._on_create_case)
        self._remove_case.clicked.connect(self._on_remove_case)
        self._new_button.clicked.connect(self._on_new_comment)
        self._edit_button.clicked.connect(self._on_edit_comment)
        self._delete_button.clicked.connect(self._on_delete_comment)
        self._save_button.clicked.connect(self.save_comment)
        self._close_button.clicked.connect(self.close)
        self._comments.itemSelectionChanged.connect(self._update_buttons)

    # -- data access -----------------------------------------------------

    def candidate(self) -> Optional[MergeCandidate]:
        """The stored candidate, or None if it no longer exists."""
        return next(
            (c for c in self._service.data.merge_candidates if c.id == self._candidate_id),
            None,
        )

    def refresh(self) -> None:
        """Re-read the candidate and rebuild everything except the comment editor."""
        cand = self.candidate()
        self._loading = True
        try:
            if cand is None:
                self._persons_label.setText("Kandidaten finns inte längre.")
                self.setEnabled(False)
                return
            data = self._service.data
            summaries = PersonSummaryIndex.build(data)
            self._persons_label.setText(
                "\n".join(self._person_line(summaries, pid) for pid in (cand.person_1_id, cand.person_2_id))
            )
            self._assessment.setCurrentIndex(self._assessment.findData(cand.assessment))
            self._enabled.setChecked(cand.enabled)
            case = next((c for c in data.research_cases if c.id == cand.research_case_id), None)
            if case is not None:
                self._case_label.setText(case.title.strip() or "(utan rubrik)")
            else:
                self._case_label.setText("Inget")
            self._remove_case.setEnabled(bool(cand.research_case_id))
            self._comments.clear()
            for comment in cand.comments:
                shown = comment.date.strip() or "(utan datum)"
                first_line = comment.text.splitlines()[0] if comment.text else ""
                item = QListWidgetItem(f"{shown}  {first_line}")
                item.setData(Qt.ItemDataRole.UserRole, comment.id)
                item.setToolTip(comment.text)
                self._comments.addItem(item)
        finally:
            self._loading = False
        self._update_buttons()

    @staticmethod
    def _person_line(summaries: PersonSummaryIndex, person_id: str) -> str:
        if person_id not in summaries:
            return f"Okänd person ({person_id})"
        life = summaries.lifespan_text(person_id)
        return f"{summaries.name(person_id)} {life} ({person_id})".replace("  ", " ")

    def _update_buttons(self) -> None:
        has_selection = bool(self._comments.selectedItems())
        self._edit_button.setEnabled(has_selection)
        self._delete_button.setEnabled(has_selection)

    def _selected_comment(self) -> Optional[MergeCandidateComment]:
        items = self._comments.selectedItems()
        cand = self.candidate()
        if not items or cand is None:
            return None
        comment_id = items[0].data(Qt.ItemDataRole.UserRole)
        return next((c for c in cand.comments if c.id == comment_id), None)

    def _show_error(self, exc: Exception) -> None:
        text = "\n".join(exc.errors) if isinstance(exc, ValidationError) else str(exc)
        self._error_label.setText(text)

    # -- candidate field changes -----------------------------------------

    def _on_assessment_changed(self) -> None:
        if self._loading:
            return
        try:
            self._service.set_candidate_assessment(
                self._candidate_id, self._assessment.currentData()
            )
            self._error_label.clear()
        except (ValidationError, KeyError) as exc:
            self._show_error(exc)
        self.refresh()

    def _on_enabled_toggled(self, checked: bool) -> None:
        if self._loading:
            return
        try:
            self._service.set_candidate_enabled(self._candidate_id, checked)
            self._error_label.clear()
        except (ValidationError, KeyError) as exc:
            self._show_error(exc)
        self.refresh()

    def _on_pick_case(self) -> None:
        case_id = ResearchCasePickerDialog.pick(
            self._service.data, "merge_candidate", self._candidate_id, self
        )
        if case_id is None:
            return
        try:
            self._service.set_candidate_research_case(self._candidate_id, case_id)
            self._error_label.clear()
        except (ValidationError, KeyError) as exc:
            self._show_error(exc)
        self.refresh()

    def _on_create_case(self) -> None:
        try:
            self._service.create_research_case_for_candidate(self._candidate_id)
            self._error_label.clear()
        except (ValidationError, KeyError) as exc:
            self._show_error(exc)
        self.refresh()

    def _on_remove_case(self) -> None:
        try:
            self._service.set_candidate_research_case(self._candidate_id, None)
            self._error_label.clear()
        except (ValidationError, KeyError) as exc:
            self._show_error(exc)
        self.refresh()

    # -- comments --------------------------------------------------------

    def _set_editor(self, comment_id: Optional[str], date_text: str, text: str) -> None:
        self._editing_comment_id = comment_id
        self._date_edit.setText(date_text)
        self._text_edit.setPlainText(text)
        self._baseline = (date_text, text)

    def _start_new_comment(self) -> None:
        self._set_editor(None, today_text(), "")

    def has_unsaved_text(self) -> bool:
        """True when the comment editor differs from what is stored."""
        if self._editing_comment_id is None:
            return bool(self._text_edit.toPlainText().strip())
        return (self._date_edit.text(), self._text_edit.toPlainText()) != self._baseline

    def has_unsaved_changes(self) -> bool:
        return self.has_unsaved_text()

    def _on_new_comment(self) -> None:
        if not self._resolve_unsaved():
            return
        self._comments.clearSelection()
        self._start_new_comment()
        self._text_edit.setFocus()

    def _on_edit_comment(self) -> None:
        comment = self._selected_comment()
        if comment is None:
            return
        if not self._resolve_unsaved():
            return
        self._set_editor(comment.id, comment.date, comment.text)
        self._text_edit.setFocus()

    def save_comment(self) -> bool:
        """Save the comment editor's content; True on success."""
        date_text = self._date_edit.text().strip()
        text = self._text_edit.toPlainText()
        if not text.strip():
            self._error_label.setText("Kommentaren måste ha en text.")
            return False
        if len(text) > MAX_COMMENT_TEXT:
            self._error_label.setText(
                f"Kommentaren får högst vara {MAX_COMMENT_TEXT} tecken."
            )
            return False
        try:
            if self._editing_comment_id is None:
                self._service.add_candidate_comment(self._candidate_id, date_text, text)
            else:
                self._service.update_candidate_comment(
                    self._candidate_id, self._editing_comment_id, date_text, text
                )
        except (ValidationError, KeyError) as exc:
            # Keep the text so nothing is lost.
            self._show_error(exc)
            return False
        self._error_label.clear()
        self._start_new_comment()
        self.refresh()
        return True

    def _confirm_delete(self, comment: MergeCandidateComment) -> bool:
        answer = QMessageBox.question(
            self,
            "Ta bort kommentar",
            delete_prompt_text(comment),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _on_delete_comment(self) -> None:
        comment = self._selected_comment()
        if comment is None or not self._confirm_delete(comment):
            return
        try:
            self._service.delete_candidate_comment(self._candidate_id, comment.id)
            self._error_label.clear()
        except (ValidationError, KeyError) as exc:
            self._show_error(exc)
        if self._editing_comment_id == comment.id:
            self._start_new_comment()
        self.refresh()

    # -- unsaved text ----------------------------------------------------

    def _ask_unsaved(self) -> str:
        """Ask save, discard or stay; returns SAVE, DISCARD or STAY."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Osparad kommentar")
        box.setText("Kommentaren har osparade ändringar. Vill du spara dem?")
        save = box.addButton("Spara", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Kasta", QMessageBox.ButtonRole.DestructiveRole)
        stay = box.addButton("Stanna", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(stay)
        box.setEscapeButton(stay)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save:
            return SAVE
        if clicked is discard:
            return DISCARD
        return STAY

    def _resolve_unsaved(self) -> bool:
        """Handle unsaved text; True when it is safe to continue."""
        if not self.has_unsaved_text():
            return True
        choice = self._ask_unsaved()
        if choice == SAVE:
            return self.save_comment()
        if choice == DISCARD:
            self._start_new_comment()
            return True
        return False

    def request_resolution(self) -> ResolutionResult:
        """Bring the dialog forward and let the user resolve unsaved text."""
        self.show()
        self.raise_()
        self.activateWindow()
        if not self.has_unsaved_text():
            return ResolutionResult.SAVED
        choice = self._ask_unsaved()
        if choice == SAVE and self.save_comment():
            return ResolutionResult.SAVED
        if choice == DISCARD:
            self._start_new_comment()
            return ResolutionResult.DISCARDED
        return ResolutionResult.STILL_UNSAVED

    def done(self, result: int) -> None:
        """Close only when unsaved comment text has been resolved."""
        if not self._resolve_unsaved():
            return
        super().done(result)
