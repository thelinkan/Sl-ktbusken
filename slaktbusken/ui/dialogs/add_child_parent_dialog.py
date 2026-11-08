"""Dialog för att välja andra förälder när ett nytt barn läggs till.

När användaren högerklickar på en person och väljer "Nytt barn" och
personen redan har en eller flera partnerfamiljer, låter denna dialog
användaren välja i vilken familj barnet ska placeras (dvs. vem den
andra föräldern är), eller att skapa en ny familj med endast den
klickade personen som förälder.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.family import Family
from slaktbusken.model.person import Person

# Sentinel returned as the chosen family id when the user wants a new
# single-parent family ("Annan/ingen andra förälder").
NEW_FAMILY_SENTINEL = "__new_single_parent_family__"

# Label shown for the "new family / unknown other parent" option.
OTHER_PARENT_LABEL = "Annan/ingen andra förälder"

# Label used when a partner family's only partner is the clicked person.
UNKNOWN_PARTNER_LABEL = "(okänd partner)"


def _format_person_name(person: Optional[Person], fallback: str) -> str:
    """Formatera en persons visningsnamn som 'förnamn efternamn'.

    Args:
        person: Personen vars namn ska formateras, eller None.
        fallback: Text att använda om personen saknas eller saknar namn.
    """
    if person is None or not person.names:
        return fallback
    name = person.names[0]
    parts = [p for p in (name.given, name.surname) if p]
    return " ".join(parts) if parts else fallback


def build_child_parent_options(
    partner_families: list[Family],
    persons_by_id: dict[str, Person],
    clicked_person_id: str,
) -> list[tuple[str, str]]:
    """Bygg valalternativ för dialogen.

    Varje partnerfamilj blir ett alternativ märkt med den *andra* partnerns
    namn (den som inte är den klickade personen). En familj vars enda
    partner är den klickade personen märks "(okänd partner)". Ett sista
    alternativ representerar en ny familj med endast den klickade personen.

    Args:
        partner_families: Familjer där den klickade personen är partner.
        persons_by_id: Uppslag från person-id till Person.
        clicked_person_id: Den klickade personens id.

    Returns:
        Lista av tupler (family_id_eller_sentinel, etikett).
    """
    options: list[tuple[str, str]] = []
    for family in partner_families:
        other_ids = [
            p.person_id
            for p in family.partners
            if p.person_id != clicked_person_id
        ]
        if other_ids:
            label = _format_person_name(
                persons_by_id.get(other_ids[0]), other_ids[0]
            )
        else:
            label = UNKNOWN_PARTNER_LABEL
        options.append((family.id, label))

    options.append((NEW_FAMILY_SENTINEL, OTHER_PARENT_LABEL))
    return options


class AddChildParentDialog(QDialog):
    """Dialog som låter användaren välja andra förälder för ett nytt barn.

    Visar en lista med den klickade personens partnerfamiljer (märkta med
    den andra partnern) samt ett alternativ för att skapa en ny familj med
    endast den klickade personen som förälder.

    Args:
        partner_families: Familjer där den klickade personen är partner.
        persons_by_id: Uppslag från person-id till Person.
        clicked_person_id: Den klickade personens id.
        parent: Valfri föräldrawidget.
    """

    def __init__(
        self,
        partner_families: list[Family],
        persons_by_id: dict[str, Person],
        clicked_person_id: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Lägg till barn")
        self.setMinimumWidth(380)

        self._options = build_child_parent_options(
            partner_families, persons_by_id, clicked_person_id
        )
        self._chosen_family_id: Optional[str] = None

        self._setup_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    @property
    def chosen_family_id(self) -> Optional[str]:
        """Vald familj-id, sentinel för ny familj, eller None om avbrutet."""
        return self._chosen_family_id

    @property
    def option_labels(self) -> list[str]:
        """Etiketterna som visas i listan, i ordning (för tester)."""
        return [label for _, label in self._options]

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        info_label = QLabel("Välj den andra föräldern till barnet:")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self._list_widget = QListWidget()
        for family_id, label in self._options:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, family_id)
            self._list_widget.addItem(item)
        if self._list_widget.count() > 0:
            self._list_widget.setCurrentRow(0)
        layout.addWidget(self._list_widget)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText("Välj")
        layout.addWidget(self._button_box)

    def _connect_signals(self) -> None:
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self.reject)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        if item is not None:
            self._chosen_family_id = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def _on_accept(self) -> None:
        current = self._list_widget.currentItem()
        if current is not None:
            self._chosen_family_id = current.data(Qt.ItemDataRole.UserRole)
            self.accept()
