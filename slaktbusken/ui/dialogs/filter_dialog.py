"""Filter dialog for the person list in Släktbusken.

A non-modal dialog that allows the user to set filter criteria for the
person list. Emits a signal when the filter is applied.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QCompleter,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    pass

from slaktbusken.ui.person_list_panel import FilterCriteria

# All event types used in the project
INDIVIDUAL_EVENT_TYPES = [
    ("adoption", "Adoption"),
    ("baptism", "Dop"),
    ("birth", "Födelse"),
    ("blessing", "Välsignelse"),
    ("burial", "Begravning"),
    ("census", "Folkräkning"),
    ("confirmation", "Konfirmation"),
    ("cremation", "Kremering"),
    ("death", "Död"),
    ("emigration", "Emigration"),
    ("first_communion", "Första nattvarden"),
    ("gender_correction", "Könskorrigering"),
    ("graduation", "Examen"),
    ("immigration", "Immigration"),
    ("name_change", "Namnbyte"),
    ("retirement", "Pension"),
    ("will", "Testamente"),
    ("custom_individual_event", "Anpassad individuell händelse"),
]

FAMILY_EVENT_TYPES = [
    ("divorce", "Skilsmässa"),
    ("divorce_filed", "Skilsmässoansökan"),
    ("engagement", "Förlovning"),
    ("marriage", "Vigsel"),
    ("custom_family_event", "Anpassad familjehändelse"),
]


class FilterDialog(QDialog):
    """Non-modal filter dialog for the person list.

    Provides fields for filtering by name, title, event types, year ranges,
    and parish. Emits filter_applied when the user clicks 'Filtrera'.

    Signals:
        filter_applied: Emitted with FilterCriteria when the filter is applied.
    """

    filter_applied = Signal(FilterCriteria)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the FilterDialog.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Filtrera personlistan")
        self.setMinimumWidth(400)
        self._event_checkboxes: dict[str, QCheckBox] = {}

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Build the dialog UI."""
        main_layout = QVBoxLayout(self)

        # --- Name filters ---
        name_group = QGroupBox("Namnfilter")
        name_layout = QFormLayout()

        self._title_field = QLineEdit()
        self._title_field.setPlaceholderText("T.ex. Fil.Dr")
        name_layout.addRow("Titel:", self._title_field)

        self._given_field = QLineEdit()
        self._given_field.setPlaceholderText("Förnamn...")
        name_layout.addRow("Förnamn:", self._given_field)

        self._surname_field = QLineEdit()
        self._surname_field.setPlaceholderText("Efternamn...")
        name_layout.addRow("Efternamn:", self._surname_field)

        name_group.setLayout(name_layout)
        main_layout.addWidget(name_group)

        # --- Event type filters ---
        event_group = QGroupBox("Händelsetyper")
        event_layout = QVBoxLayout()

        # Scroll area for many checkboxes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(200)
        scroll_widget = QWidget()
        scroll_inner = QVBoxLayout(scroll_widget)

        # Individual event types
        ind_label = QLabel("Individuella händelser:")
        ind_label.setStyleSheet("font-weight: bold;")
        scroll_inner.addWidget(ind_label)
        for event_key, event_label in INDIVIDUAL_EVENT_TYPES:
            cb = QCheckBox(event_label)
            self._event_checkboxes[event_key] = cb
            scroll_inner.addWidget(cb)

        # Family event types
        fam_label = QLabel("Familjehändelser:")
        fam_label.setStyleSheet("font-weight: bold;")
        scroll_inner.addWidget(fam_label)
        for event_key, event_label in FAMILY_EVENT_TYPES:
            cb = QCheckBox(event_label)
            self._event_checkboxes[event_key] = cb
            scroll_inner.addWidget(cb)

        scroll_inner.addStretch()
        scroll.setWidget(scroll_widget)
        event_layout.addWidget(scroll)
        event_group.setLayout(event_layout)
        main_layout.addWidget(event_group)

        # --- Date range filters ---
        date_group = QGroupBox("Datumintervall")
        date_layout = QFormLayout()

        # Birth year range
        birth_row = QHBoxLayout()
        self._birth_year_from = QLineEdit()
        self._birth_year_from.setPlaceholderText("Från")
        self._birth_year_from.setMaximumWidth(80)
        birth_row.addWidget(self._birth_year_from)
        birth_row.addWidget(QLabel("–"))
        self._birth_year_to = QLineEdit()
        self._birth_year_to.setPlaceholderText("Till")
        self._birth_year_to.setMaximumWidth(80)
        birth_row.addWidget(self._birth_year_to)
        birth_row.addStretch()
        date_layout.addRow("Födelseår:", birth_row)

        # Death year range
        death_row = QHBoxLayout()
        self._death_year_from = QLineEdit()
        self._death_year_from.setPlaceholderText("Från")
        self._death_year_from.setMaximumWidth(80)
        death_row.addWidget(self._death_year_from)
        death_row.addWidget(QLabel("–"))
        self._death_year_to = QLineEdit()
        self._death_year_to.setPlaceholderText("Till")
        self._death_year_to.setMaximumWidth(80)
        death_row.addWidget(self._death_year_to)
        death_row.addStretch()
        date_layout.addRow("Dödsår:", death_row)

        # Marriage year range
        marriage_row = QHBoxLayout()
        self._marriage_year_from = QLineEdit()
        self._marriage_year_from.setPlaceholderText("Från")
        self._marriage_year_from.setMaximumWidth(80)
        marriage_row.addWidget(self._marriage_year_from)
        marriage_row.addWidget(QLabel("–"))
        self._marriage_year_to = QLineEdit()
        self._marriage_year_to.setPlaceholderText("Till")
        self._marriage_year_to.setMaximumWidth(80)
        marriage_row.addWidget(self._marriage_year_to)
        marriage_row.addStretch()
        date_layout.addRow("Vigselår:", marriage_row)

        date_group.setLayout(date_layout)
        main_layout.addWidget(date_group)

        # --- Parish filter ---
        parish_group = QGroupBox("Församling")
        parish_layout = QFormLayout()
        self._parish_field = QLineEdit()
        self._parish_field.setPlaceholderText("Församlingsnamn...")
        parish_layout.addRow("Församling:", self._parish_field)
        parish_group.setLayout(parish_layout)
        main_layout.addWidget(parish_group)

        # --- DNA Cluster filter ---
        cluster_group = QGroupBox("DNA-kluster")
        cluster_layout = QFormLayout()
        self._cluster_field = QLineEdit()
        self._cluster_field.setPlaceholderText("Klusternamn...")
        self._cluster_completer = QCompleter([], self)
        self._cluster_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._cluster_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._cluster_field.setCompleter(self._cluster_completer)
        cluster_layout.addRow("Kluster:", self._cluster_field)
        cluster_group.setLayout(cluster_layout)
        main_layout.addWidget(cluster_group)

        # --- Buttons ---
        button_row = QHBoxLayout()
        self._apply_button = QPushButton("Filtrera")
        self._clear_button = QPushButton("Rensa")
        button_row.addStretch()
        button_row.addWidget(self._apply_button)
        button_row.addWidget(self._clear_button)
        main_layout.addLayout(button_row)

    def _connect_signals(self) -> None:
        """Connect button signals."""
        self._apply_button.clicked.connect(self._on_apply)
        self._clear_button.clicked.connect(self._on_clear)

    def _on_apply(self) -> None:
        """Gather criteria from fields and emit filter_applied signal."""
        event_types: set[str] = set()
        for event_key, cb in self._event_checkboxes.items():
            if cb.isChecked():
                event_types.add(event_key)

        criteria = FilterCriteria(
            title=self._title_field.text(),
            given=self._given_field.text(),
            surname=self._surname_field.text(),
            event_types=event_types,
            birth_year_from=self._birth_year_from.text(),
            birth_year_to=self._birth_year_to.text(),
            death_year_from=self._death_year_from.text(),
            death_year_to=self._death_year_to.text(),
            marriage_year_from=self._marriage_year_from.text(),
            marriage_year_to=self._marriage_year_to.text(),
            parish=self._parish_field.text(),
            cluster=self._cluster_field.text(),
        )
        self.filter_applied.emit(criteria)

    def _on_clear(self) -> None:
        """Clear all filter fields."""
        self._title_field.clear()
        self._given_field.clear()
        self._surname_field.clear()
        self._birth_year_from.clear()
        self._birth_year_to.clear()
        self._death_year_from.clear()
        self._death_year_to.clear()
        self._marriage_year_from.clear()
        self._marriage_year_to.clear()
        self._parish_field.clear()
        self._cluster_field.clear()
        for cb in self._event_checkboxes.values():
            cb.setChecked(False)

    def set_available_clusters(self, cluster_names: list[str]) -> None:
        """Update the autocomplete suggestions for the cluster field.

        Args:
            cluster_names: List of available cluster names from the project.
        """
        from PySide6.QtCore import QStringListModel

        model = QStringListModel(cluster_names, self._cluster_completer)
        self._cluster_completer.setModel(model)
