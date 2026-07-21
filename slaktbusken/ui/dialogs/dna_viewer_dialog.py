"""DNA Viewer dialog for displaying raw genotype data.

Provides a modal dialog with a virtual-scrolling table for viewing
up to 1,000,000 SNP records. Includes text search and chromosome
filter for narrowing results.

All UI text is in Swedish.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QTimer, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.services.dna_raw_parser import RawSnpRecord

_COLUMNS = ["rsID", "Kromosom", "Position", "Alleler"]

# Natural sort order for chromosomes
_CHROMOSOME_ORDER = [
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
    "21", "22", "X", "Y", "MT",
]


def _chromosome_sort_key(chrom: str) -> tuple[int, str]:
    """Return a sort key for natural chromosome ordering."""
    try:
        idx = _CHROMOSOME_ORDER.index(chrom)
    except ValueError:
        idx = len(_CHROMOSOME_ORDER)
    return (idx, chrom)


class DnaSnpTableModel(QAbstractTableModel):
    """Table model for lazy display of SNP records with filtering.

    Supports up to 1,000,000 rows via Qt's virtual scrolling mechanism.
    Filtering is done in-memory on a pre-built filtered list.
    """

    def __init__(self, records: list[RawSnpRecord], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._all_records = records
        self._filtered_records: list[RawSnpRecord] = list(records)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Return number of rows in the filtered dataset."""
        if parent.isValid():
            return 0
        return len(self._filtered_records)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Return the fixed column count (4)."""
        if parent.isValid():
            return 0
        return len(_COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Optional[str]:
        """Return cell data for display."""
        if not index.isValid():
            return None
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        row = index.row()
        col = index.column()

        if row < 0 or row >= len(self._filtered_records):
            return None

        record = self._filtered_records[row]

        if col == 0:
            return record.rsid
        elif col == 1:
            return record.chromosome
        elif col == 2:
            return str(record.position)
        elif col == 3:
            return record.alleles
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Optional[str]:
        """Return column headers."""
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(_COLUMNS):
            return _COLUMNS[section]
        return None

    def set_filter(self, search_text: str, chromosome: str) -> None:
        """Apply combined text search and chromosome filter.

        Args:
            search_text: Case-insensitive substring to match against rsID,
                         chromosome, or position.
            chromosome: Chromosome value to filter on, or "Alla" for no filter.
        """
        self.beginResetModel()

        search_lower = search_text.strip().lower()

        if not search_lower and chromosome == "Alla":
            # No filtering needed
            self._filtered_records = list(self._all_records)
        else:
            filtered: list[RawSnpRecord] = []
            for record in self._all_records:
                # Chromosome filter
                if chromosome != "Alla" and record.chromosome != chromosome:
                    continue
                # Text search filter
                if search_lower:
                    if (
                        search_lower not in record.rsid.lower()
                        and search_lower not in record.chromosome.lower()
                        and search_lower not in str(record.position).lower()
                    ):
                        continue
                filtered.append(record)
            self._filtered_records = filtered

        self.endResetModel()


class DnaViewerDialog(QDialog):
    """Modal dialog for viewing raw DNA genotype data.

    Displays SNP records in a virtual-scrolling table with search
    and chromosome filtering. Handles up to 1,000,000 rows.

    Args:
        records: List of RawSnpRecord to display, or None if the
                 data file could not be read.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        records: Optional[list[RawSnpRecord]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("DNA-datavisare")
        self.setMinimumSize(700, 500)
        self.resize(900, 600)

        self._records = records
        self._model: Optional[DnaSnpTableModel] = None
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(200)
        self._debounce_timer.timeout.connect(self._apply_filter)

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the dialog layout."""
        layout = QVBoxLayout(self)

        if self._records is None:
            # File not found / unreadable — show error message
            error_label = QLabel("Datafilen saknas eller kan inte läsas.")
            error_label.setObjectName("error_label")
            error_label.setWordWrap(True)
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(error_label)

            # Close button
            close_btn = QPushButton("Stäng")
            close_btn.clicked.connect(self.close)
            layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
            return

        # --- Filter bar ---
        filter_layout = QHBoxLayout()

        self._search_field = QLineEdit()
        self._search_field.setObjectName("search_field")
        self._search_field.setMaxLength(100)
        self._search_field.setPlaceholderText("Sök...")
        self._search_field.setClearButtonEnabled(True)
        filter_layout.addWidget(self._search_field, stretch=1)

        self._chromosome_combo = QComboBox()
        self._chromosome_combo.setObjectName("chromosome_combo")
        self._populate_chromosome_filter()
        filter_layout.addWidget(self._chromosome_combo)

        layout.addLayout(filter_layout)

        # --- Table view ---
        self._model = DnaSnpTableModel(self._records, self)
        self._table_view = QTableView()
        self._table_view.setObjectName("table_view")
        self._table_view.setModel(self._model)
        self._table_view.setSelectionBehavior(
            QTableView.SelectionBehavior.SelectRows
        )
        self._table_view.setAlternatingRowColors(True)
        self._table_view.verticalHeader().setVisible(False)
        self._table_view.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(self._table_view)

        # --- Close button ---
        close_btn = QPushButton("Stäng")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

        # --- Connect signals ---
        self._search_field.textChanged.connect(self._on_filter_changed)
        self._chromosome_combo.currentTextChanged.connect(self._on_filter_changed)

    # ------------------------------------------------------------------
    # Chromosome filter population
    # ------------------------------------------------------------------

    def _populate_chromosome_filter(self) -> None:
        """Populate the chromosome dropdown with 'Alla' + unique chromosomes from data."""
        self._chromosome_combo.addItem("Alla")

        if not self._records:
            return

        # Collect unique chromosomes from the data
        chromosomes: set[str] = set()
        for record in self._records:
            chromosomes.add(record.chromosome)

        # Sort naturally
        sorted_chromosomes = sorted(chromosomes, key=_chromosome_sort_key)

        for chrom in sorted_chromosomes:
            self._chromosome_combo.addItem(chrom)

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def _on_filter_changed(self) -> None:
        """Debounce filter updates to keep UI responsive."""
        self._debounce_timer.start()

    def _apply_filter(self) -> None:
        """Apply the current search text and chromosome filter to the model."""
        if self._model is None:
            return

        search_text = self._search_field.text()
        chromosome = self._chromosome_combo.currentText()
        self._model.set_filter(search_text, chromosome)
