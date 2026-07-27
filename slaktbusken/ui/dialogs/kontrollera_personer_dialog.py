"""Dialog for person validation checks (Kontrollera personer).

Provides a three-tab modal dialog for configuring and running person
validation checks against the active project data. Results are presented
in a table with person names and findings.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from PySide6.QtGui import QCloseEvent

    from slaktbusken.model.project import ProjectData

from slaktbusken.persistence.settings_io import AgeCheckThreshold, PersonCheckConfig
from slaktbusken.services.person_check_engine import CheckFinding
from slaktbusken.ui.icons.icon_registry import icon_registry
from slaktbusken.ui.workers.check_worker import CheckWorker


class KontrolleraPersonerDialog(QDialog):
    """Modal dialog for person validation checks.

    Displays three tabs: Resultat (results), Ålderskontroller (age checks
    configuration), and Fler kontroller (additional logic/structure checks).
    Runs checks in a background thread and presents findings in the result
    tab.

    Args:
        data: The project data to validate.
        config: Person check configuration (will be deep-copied).
        project_folder: Path to the project folder (for media file checks).
        parent: Optional parent widget.
    """

    def __init__(
        self,
        data: "ProjectData",
        config: PersonCheckConfig,
        project_folder: Path | None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._data = data
        self._config = deepcopy(config)
        self._project_folder = project_folder
        self._worker: CheckWorker | None = None
        self._findings: list[CheckFinding] = []
        self._selected_person_id: str | None = None

        self._setup_ui()

    @property
    def config(self) -> PersonCheckConfig:
        """Return the (potentially modified) check configuration."""
        return self._config

    @property
    def selected_person_id(self) -> str | None:
        """Return the person_id selected via double-click, or None."""
        return self._selected_person_id

    def _setup_ui(self) -> None:
        """Build the dialog UI structure."""
        self.setWindowTitle("Kontrollera personer")
        self.setModal(True)
        self.resize(700, 500)

        layout = QVBoxLayout(self)

        # Tab widget with three tabs
        self._tab_widget = QTabWidget()

        # Tab 0: Resultat
        self._result_tab = self._build_result_tab()
        self._tab_widget.addTab(self._result_tab, "Resultat")

        # Tab 1: Ålderskontroller
        self._age_tab = self._build_age_tab()
        self._tab_widget.addTab(self._age_tab, "Ålderskontroller")

        # Tab 2: Fler kontroller
        self._logic_tab = self._build_logic_tab()
        self._tab_widget.addTab(self._logic_tab, "Fler kontroller")

        # Set Resultat as active tab
        self._tab_widget.setCurrentIndex(0)

        layout.addWidget(self._tab_widget)

        # Progress bar (hidden by default)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        # Button row
        button_layout = QHBoxLayout()

        self._btn_close = QPushButton("Stäng")
        self._btn_close.clicked.connect(self.accept)

        self._btn_check = QPushButton("Kontrollera")
        self._btn_check.clicked.connect(self._start_check)

        self._btn_help = QPushButton("Hjälp")
        self._btn_help.clicked.connect(self._show_help)

        button_layout.addWidget(self._btn_close)
        button_layout.addStretch()
        button_layout.addWidget(self._btn_check)
        button_layout.addStretch()
        button_layout.addWidget(self._btn_help)

        layout.addLayout(button_layout)

    def _build_result_tab(self) -> QWidget:
        """Build and return the Resultat tab widget.

        Contains a QTableWidget with columns 'Person' and 'Påpekande',
        and a status label showing the number of findings.
        """
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)

        # Result table
        self._result_table = QTableWidget()
        self._result_table.setColumnCount(2)
        self._result_table.setHorizontalHeaderLabels(["Person", "Påpekande"])
        self._result_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._result_table.setAlternatingRowColors(True)
        self._result_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._result_table.verticalHeader().setVisible(False)

        # Stretch columns to fill available space
        header = self._result_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        self._result_table.setColumnWidth(0, 250)

        # Double-click signal
        self._result_table.cellDoubleClicked.connect(
            self._on_result_double_click
        )

        tab_layout.addWidget(self._result_table)

        # Status label
        self._result_status_label = QLabel("Antal påpekanden: 0")
        tab_layout.addWidget(self._result_status_label)

        return tab

    def _populate_results(self, findings: list[CheckFinding]) -> None:
        """Populate the result table with check findings.

        Args:
            findings: List of CheckFinding objects from the check engine.
        """
        self._result_table.setRowCount(0)
        self._result_table.setRowCount(len(findings))

        for row, finding in enumerate(findings):
            # Person column: icon + name
            person_item = QTableWidgetItem(finding.person_display)
            pixmap = icon_registry.get_gender_icon(finding.person_sex)
            if not pixmap.isNull():
                person_item.setIcon(QIcon(pixmap))
            # Store person_id for navigation
            person_item.setData(
                Qt.ItemDataRole.UserRole, finding.person_id
            )
            self._result_table.setItem(row, 0, person_item)

            # Påpekande column
            message_item = QTableWidgetItem(finding.message)
            self._result_table.setItem(row, 1, message_item)

        # Update status label
        self._result_status_label.setText(
            f"Antal påpekanden: {len(findings)}"
        )

    def _on_result_double_click(self, row: int, col: int) -> None:
        """Handle double-click on a result table row.

        Stores the selected person_id and closes the dialog with accept,
        so the caller can navigate to the person.
        """
        item = self._result_table.item(row, 0)
        if item is not None:
            self._selected_person_id = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def _build_age_tab(self) -> QWidget:
        """Build and return the age checks configuration tab.

        Contains a master checkbox controlling all child widgets, and
        individual checks each with their own checkbox and spinbox fields.
        """
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)

        # Master checkbox
        self._age_master_cb = QCheckBox("Utför kontroller")
        self._age_master_cb.setChecked(self._config.age_checks.master_enabled)
        tab_layout.addWidget(self._age_master_cb)

        # Scroll area for individual checks
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._age_content_widget = QWidget()
        grid = QGridLayout(self._age_content_widget)

        # Column headers
        grid.addWidget(QLabel(""), 0, 0)  # checkbox column
        grid.addWidget(QLabel(""), 0, 1)  # label column
        grid.addWidget(QLabel("Män"), 0, 2)
        grid.addWidget(QLabel("Kvinnor"), 0, 3)

        # Define checks: (label, config_attr, has_male_female, max_range)
        self._age_check_defs = [
            ("Högsta ålder", "max_age", True, 999),
            ("Högsta ålder vid dop", "max_age_at_baptism", True, 999),
            ("Lägsta ålder vid giftermål", "min_age_at_marriage", True, 999),
            ("Högsta ålder vid giftermål", "max_age_at_marriage", True, 999),
            ("Största åldersskillnad mellan makar/partner", "max_partner_age_diff", False, 999),
            ("Lägsta ålder vid barnafödande", "min_age_at_childbirth", True, 999),
            ("Högsta ålder vid barnafödande", "max_age_at_childbirth", True, 999),
            ("Kortast tid mellan barnafödslar", "min_days_between_births", False, 9999),
            ("Längsta tid mellan död och begravning", "max_days_death_to_burial", True, 9999),
        ]

        # Storage for UI widgets
        self._age_check_widgets: list[
            tuple[QCheckBox, QSpinBox | None, QSpinBox | None]
        ] = []

        row = 1
        cfg = self._config.age_checks
        for label_text, attr, has_mf, max_range in self._age_check_defs:
            cb = QCheckBox()
            label = QLabel(label_text)

            if has_mf:
                threshold: "AgeCheckThreshold" = getattr(cfg, attr)
                cb.setChecked(threshold.enabled)
                spin_male = QSpinBox()
                spin_male.setRange(0, max_range)
                spin_male.setValue(threshold.male)
                spin_female = QSpinBox()
                spin_female.setRange(0, max_range)
                spin_female.setValue(threshold.female)

                # Disable spinboxes when individual checkbox unchecked
                cb.toggled.connect(spin_male.setEnabled)
                cb.toggled.connect(spin_female.setEnabled)
                spin_male.setEnabled(threshold.enabled)
                spin_female.setEnabled(threshold.enabled)

                grid.addWidget(cb, row, 0)
                grid.addWidget(label, row, 1)
                grid.addWidget(spin_male, row, 2)
                grid.addWidget(spin_female, row, 3)
                self._age_check_widgets.append((cb, spin_male, spin_female))
            else:
                # Single value check (max_partner_age_diff or min_days_between_births)
                enabled_attr = attr + "_enabled"
                enabled_val = getattr(cfg, enabled_attr)
                value_val = getattr(cfg, attr)
                cb.setChecked(enabled_val)

                spin_single = QSpinBox()
                spin_single.setRange(0, max_range)
                spin_single.setValue(value_val)

                cb.toggled.connect(spin_single.setEnabled)
                spin_single.setEnabled(enabled_val)

                grid.addWidget(cb, row, 0)
                grid.addWidget(label, row, 1)
                grid.addWidget(spin_single, row, 2)
                self._age_check_widgets.append((cb, spin_single, None))

            row += 1

        grid.setColumnStretch(1, 1)
        scroll.setWidget(self._age_content_widget)
        tab_layout.addWidget(scroll)

        # Master checkbox controls enabled state of content
        self._age_master_cb.toggled.connect(
            self._age_content_widget.setEnabled
        )
        self._age_content_widget.setEnabled(
            self._config.age_checks.master_enabled
        )

        return tab

    def _sync_age_config_from_ui(self) -> None:
        """Read all age tab UI values back into self._config.age_checks."""
        cfg = self._config.age_checks
        cfg.master_enabled = self._age_master_cb.isChecked()

        for i, (label_text, attr, has_mf, _max_range) in enumerate(
            self._age_check_defs
        ):
            cb, spin1, spin2 = self._age_check_widgets[i]
            if has_mf:
                threshold = getattr(cfg, attr)
                threshold.enabled = cb.isChecked()
                threshold.male = spin1.value()  # type: ignore[union-attr]
                threshold.female = spin2.value()  # type: ignore[union-attr]
            else:
                enabled_attr = attr + "_enabled"
                setattr(cfg, enabled_attr, cb.isChecked())
                setattr(cfg, attr, spin1.value())  # type: ignore[union-attr]

    def _build_logic_tab(self) -> QWidget:
        """Build and return the Fler kontroller (logic checks) tab widget.

        Creates 13 checkboxes corresponding to the logic/structure checks,
        initialized from the current configuration.
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Define checkbox labels mapped to their config field names
        self._logic_checkbox_defs: list[tuple[str, str]] = [
            ("Rimliga datum", "reasonable_dates"),
            (
                "Ingen händelse får förekomma före Födelse",
                "no_event_before_birth",
            ),
            (
                "Begravning och Bouppteckning får inte förekomma före döden",
                "burial_not_before_death",
            ),
            (
                "Endast Begravning, Bouppteckning och Testamente får"
                " förekomma efter döden",
                "only_burial_after_death",
            ),
            (
                "Inga egna händelser får inträffa efter döden",
                "no_own_events_after_death",
            ),
            (
                "Födelse får inte inträffa efter föräldrars död",
                "birth_not_after_parent_death",
            ),
            (
                "Ingen händelse får inträffa före föräldrars födelse",
                "no_event_before_parent_birth",
            ),
            (
                "En person får inte vara gift med eller ha barn med ett"
                " syskon eller förälder (incest)",
                "no_incest",
            ),
            (
                "En person måste ha relationer till andra i arkivet",
                "must_have_relations",
            ),
            (
                "En person får inte vara anfader eller anmoder till sig själv",
                "no_ancestor_cycle",
            ),
            (
                "Bildfiler och länkade filer måste finnas",
                "media_files_exist",
            ),
            (
                "Datum måste vara giltiga enligt den svenska kalendern",
                "valid_swedish_calendar",
            ),
            (
                "En person måste ha en koppling till huvudpersonen",
                "connected_to_main_person",
            ),
        ]

        self._logic_checkboxes: dict[str, QCheckBox] = {}
        for label, field_name in self._logic_checkbox_defs:
            cb = QCheckBox(label)
            cb.setChecked(getattr(self._config.logic_checks, field_name))
            self._logic_checkboxes[field_name] = cb
            layout.addWidget(cb)

        layout.addStretch()
        return widget

    def _sync_logic_config_from_ui(self) -> None:
        """Read all logic checkbox states back into the config."""
        for field_name, cb in self._logic_checkboxes.items():
            setattr(self._config.logic_checks, field_name, cb.isChecked())

    def _start_check(self) -> None:
        """Start the person check worker thread."""
        self._sync_age_config_from_ui()
        self._sync_logic_config_from_ui()
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        self._btn_check.setEnabled(False)

        self._worker = CheckWorker(
            data=self._data,
            config=self._config,
            project_folder=self._project_folder,
        )
        self._worker.progress_updated.connect(self._progress_bar.setValue)
        self._worker.finished.connect(self._on_checks_finished)
        self._worker.start()

    def _on_checks_finished(self, findings: list[CheckFinding]) -> None:
        """Handle completed check run.

        Hides progress bar, re-enables the check button, stores findings,
        and switches to the Resultat tab.
        """
        self._progress_bar.setVisible(False)
        self._btn_check.setEnabled(True)
        self._findings = findings

        # Populate results table
        self._populate_results(findings)

        # Switch to Resultat tab
        self._tab_widget.setCurrentIndex(0)

    def _show_help(self) -> None:
        """Show help information about person checks."""
        QMessageBox.information(
            self,
            "Hjälp — Kontrollera personer",
            "Funktionen kontrollerar personuppgifter i projektet mot "
            "konfiguerbara regler.\n\n"
            "• Resultat — visar påpekanden efter en kontrollkörning.\n"
            "• Ålderskontroller — ställ in åldersgränser för varje kön.\n"
            "• Fler kontroller — aktivera/avaktivera logiska och "
            "strukturella kontroller.\n\n"
            "Klicka \"Kontrollera\" för att starta en ny körning. "
            "Dubbelklicka på en rad i resultatlistan för att navigera "
            "till personen i diagrammet.",
        )

    def accept(self) -> None:
        """Sync config from UI before closing via accept (Stäng button)."""
        self._sync_age_config_from_ui()
        self._sync_logic_config_from_ui()
        super().accept()

    def reject(self) -> None:
        """Sync config from UI before closing via reject (Escape key)."""
        self._sync_age_config_from_ui()
        self._sync_logic_config_from_ui()
        super().reject()

    def closeEvent(self, event: "QCloseEvent") -> None:
        """Handle dialog close — sync config and interrupt worker if running."""
        self._sync_age_config_from_ui()
        self._sync_logic_config_from_ui()
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait()
        super().closeEvent(event)
