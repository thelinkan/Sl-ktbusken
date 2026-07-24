"""Settings dialog with tabbed layout: Program and Diagram tabs.

Provides a modal dialog with two tabs:
- Program: Default project management
- Diagram: Person box field toggles, diagram depth, background color

All UI text is in Swedish.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.persistence.settings_io import (
    DiagramSettings,
    PersonBoxConfig,
    PersonListConfig,
)

if TYPE_CHECKING:
    from slaktbusken.persistence.app_settings_io import AppSettingsService


class SettingsDialog(QDialog):
    """Settings dialog with Program and Diagram tabs."""

    def __init__(
        self,
        person_box_config: PersonBoxConfig,
        diagram_settings: DiagramSettings,
        person_list_config: Optional[PersonListConfig] = None,
        app_settings_service: Optional["AppSettingsService"] = None,
        current_project_path: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Inställningar")
        self.setMinimumSize(480, 560)

        self._app_settings_service = app_settings_service
        self._current_project_path = current_project_path
        self._bg_color = diagram_settings.background_color

        if person_list_config is None:
            person_list_config = PersonListConfig()

        main_layout = QVBoxLayout(self)

        # Tab widget
        self._tabs = QTabWidget(self)
        main_layout.addWidget(self._tabs)

        # Tab 1: Program
        self._build_program_tab()

        # Tab 2: Personlista
        self._build_person_list_tab(person_list_config)

        # Tab 3: Diagram
        self._build_diagram_tab(person_box_config, diagram_settings)

        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def person_box_config(self) -> PersonBoxConfig:
        """Build a PersonBoxConfig from the current checkbox states."""
        return PersonBoxConfig(
            name=self._check_name.isChecked(),
            birth_date=self._check_birth_date.isChecked(),
            birth_place=self._check_birth_place.isChecked(),
            death_date=self._check_death_date.isChecked(),
            death_place=self._check_death_place.isChecked(),
            marriage_date=self._check_marriage_date.isChecked(),
            marriage_place=self._check_marriage_place.isChecked(),
            occupation=self._check_occupation.isChecked(),
            photo=self._check_photo.isChecked(),
            dna_info=self._check_dna_info.isChecked(),
            notes=self._check_notes.isChecked(),
            cause_of_death=self._check_cause_of_death.isChecked(),
            clusters=self._check_clusters.isChecked(),
            age=self._check_age.isChecked(),
        )

    @property
    def diagram_settings(self) -> DiagramSettings:
        """Build a DiagramSettings from the current control values."""
        return DiagramSettings(
            ancestry_depth=self._spin_ancestry.value(),
            descendants_depth=self._spin_descendants.value(),
            ancestry_compact=self._check_compact.isChecked(),
            background_color=self._bg_color,
        )

    @property
    def person_list_config(self) -> PersonListConfig:
        """Build a PersonListConfig from the current checkbox states."""
        return PersonListConfig(
            sex=self._pl_check_sex.isChecked(),
            relation=self._pl_check_relation.isChecked(),
            multiple_names=self._pl_check_multiple_names.isChecked(),
            birth_date=self._pl_check_birth_date.isChecked(),
            birth_place=self._pl_check_birth_place.isChecked(),
            death_date=self._pl_check_death_date.isChecked(),
            death_place=self._pl_check_death_place.isChecked(),
            title=self._pl_check_title.isChecked(),
            occupation=self._pl_check_occupation.isChecked(),
            clusters=self._pl_check_clusters.isChecked(),
            dna=self._pl_check_dna.isChecked(),
        )

    @property
    def startup_mode(self) -> str:
        """Return the selected startup mode from radio buttons."""
        if self._radio_recent.isChecked():
            return "recent"
        elif self._radio_default.isChecked():
            return "default_project"
        return "none"

    # ------------------------------------------------------------------
    # Tab 1: Program
    # ------------------------------------------------------------------

    def _build_program_tab(self) -> None:
        """Build the Program tab with startup mode and default folder settings."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Programstart group (replaces old Standardprojekt)
        group = QGroupBox("Programstart", tab)
        vbox = QVBoxLayout(group)

        # Determine current startup mode
        startup_mode = "none"
        if self._app_settings_service:
            startup_mode = self._app_settings_service.get_startup_mode()

        # Radio buttons
        self._radio_none = QRadioButton("Öppna inget projekt")
        self._radio_recent = QRadioButton("Öppna senaste projekt")
        self._radio_default = QRadioButton("Öppna standardprojekt")

        vbox.addWidget(self._radio_none)
        vbox.addWidget(self._radio_recent)
        vbox.addWidget(self._radio_default)

        # Set current selection
        if startup_mode == "recent":
            self._radio_recent.setChecked(True)
        elif startup_mode == "default_project":
            self._radio_default.setChecked(True)
        else:
            self._radio_none.setChecked(True)

        # Standard project selection (shown below the radio button)
        default_path = None
        if self._app_settings_service:
            default_path = self._app_settings_service.get_default_project()

        if default_path:
            self._default_label = QLabel(f"  Projekt: {default_path}")
        else:
            self._default_label = QLabel("  Inget standardprojekt angivet")
        vbox.addWidget(self._default_label)

        btn_layout = QHBoxLayout()
        btn_layout.addSpacing(20)
        self._btn_set_default = QPushButton("Ange som standard")
        self._btn_set_default.setToolTip(
            "Ange det öppna projektet som standardprojekt vid uppstart"
        )
        self._btn_set_default.clicked.connect(self._on_set_default)
        if self._current_project_path is None:
            self._btn_set_default.setEnabled(False)
        btn_layout.addWidget(self._btn_set_default)

        self._btn_clear_default = QPushButton("Rensa standard")
        self._btn_clear_default.setToolTip("Ta bort standardprojektinställningen")
        self._btn_clear_default.clicked.connect(self._on_clear_default)
        if default_path is None:
            self._btn_clear_default.setEnabled(False)
        btn_layout.addWidget(self._btn_clear_default)

        vbox.addLayout(btn_layout)

        # Enable/disable the standard project controls based on radio selection
        self._radio_default.toggled.connect(self._on_startup_radio_changed)
        self._on_startup_radio_changed(self._radio_default.isChecked())

        layout.addWidget(group)

        # Standardmapp group
        folder_group = QGroupBox("Standardmapp", tab)
        folder_vbox = QVBoxLayout(folder_group)

        default_folder = None
        if self._app_settings_service:
            default_folder = self._app_settings_service.get_default_folder()

        if default_folder:
            self._folder_label = QLabel(f"Nuvarande: {default_folder}")
        else:
            self._folder_label = QLabel("Ingen standardmapp angiven")
        folder_vbox.addWidget(self._folder_label)

        folder_btn_layout = QHBoxLayout()
        self._btn_set_folder = QPushButton("Välj mapp...")
        self._btn_set_folder.setToolTip(
            "Välj standardmapp för nya projekt"
        )
        self._btn_set_folder.clicked.connect(self._on_set_folder)
        folder_btn_layout.addWidget(self._btn_set_folder)

        self._btn_clear_folder = QPushButton("Rensa mapp")
        self._btn_clear_folder.setToolTip("Ta bort standardmappsinställningen")
        self._btn_clear_folder.clicked.connect(self._on_clear_folder)
        if default_folder is None:
            self._btn_clear_folder.setEnabled(False)
        folder_btn_layout.addWidget(self._btn_clear_folder)

        folder_vbox.addLayout(folder_btn_layout)
        layout.addWidget(folder_group)

        layout.addStretch()

        self._tabs.addTab(tab, "Program")

    # ------------------------------------------------------------------
    # Tab 2: Personlista
    # ------------------------------------------------------------------

    def _build_person_list_tab(self, config: PersonListConfig) -> None:
        """Build the Personlista tab with column/icon visibility toggles."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("Synliga kolumner och ikoner", tab)
        group_layout = QVBoxLayout(group)

        self._pl_check_sex = QCheckBox("Kön")
        self._pl_check_relation = QCheckBox("Relation")
        self._pl_check_multiple_names = QCheckBox("Multipla namn")
        self._pl_check_birth_date = QCheckBox("Födelsedatum")
        self._pl_check_birth_place = QCheckBox("Födelseort")
        self._pl_check_death_date = QCheckBox("Dödsdatum")
        self._pl_check_death_place = QCheckBox("Dödsort")
        self._pl_check_title = QCheckBox("Titel")
        self._pl_check_occupation = QCheckBox("Yrke")
        self._pl_check_clusters = QCheckBox("Kluster")
        self._pl_check_dna = QCheckBox("DNA")

        for cb in [
            self._pl_check_sex, self._pl_check_relation,
            self._pl_check_multiple_names,
            self._pl_check_birth_date, self._pl_check_birth_place,
            self._pl_check_death_date, self._pl_check_death_place,
            self._pl_check_title, self._pl_check_occupation,
            self._pl_check_clusters, self._pl_check_dna,
        ]:
            group_layout.addWidget(cb)

        # Load config values
        self._pl_check_sex.setChecked(config.sex)
        self._pl_check_relation.setChecked(config.relation)
        self._pl_check_multiple_names.setChecked(config.multiple_names)
        self._pl_check_birth_date.setChecked(config.birth_date)
        self._pl_check_birth_place.setChecked(config.birth_place)
        self._pl_check_death_date.setChecked(config.death_date)
        self._pl_check_death_place.setChecked(config.death_place)
        self._pl_check_title.setChecked(config.title)
        self._pl_check_occupation.setChecked(config.occupation)
        self._pl_check_clusters.setChecked(config.clusters)
        self._pl_check_dna.setChecked(config.dna)

        layout.addWidget(group)
        layout.addStretch()

        self._tabs.addTab(tab, "Personlista")

    # ------------------------------------------------------------------
    # Tab 2: Diagram
    # ------------------------------------------------------------------

    def _build_diagram_tab(
        self, config: PersonBoxConfig, settings: DiagramSettings
    ) -> None:
        """Build the Diagram tab with person box fields, depth, and background color."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # --- Personruta group ---
        person_group = QGroupBox("Personruta – synliga fält", tab)
        person_layout = QVBoxLayout(person_group)

        self._check_name = QCheckBox("Namn")
        self._check_birth_date = QCheckBox("Födelsedatum")
        self._check_birth_place = QCheckBox("Födelseort")
        self._check_death_date = QCheckBox("Dödsdatum")
        self._check_death_place = QCheckBox("Dödsort")
        self._check_marriage_date = QCheckBox("Vigselsdatum")
        self._check_marriage_place = QCheckBox("Vigselort")
        self._check_occupation = QCheckBox("Yrke")
        self._check_photo = QCheckBox("Profilfoto")
        self._check_dna_info = QCheckBox("DNA-information")
        self._check_notes = QCheckBox("Anteckningar")
        self._check_cause_of_death = QCheckBox("Dödsorsak")
        self._check_clusters = QCheckBox("DNA-kluster")
        self._check_age = QCheckBox("Ålder")

        for cb in [
            self._check_name, self._check_birth_date, self._check_birth_place,
            self._check_death_date, self._check_death_place,
            self._check_marriage_date, self._check_marriage_place,
            self._check_occupation, self._check_photo, self._check_dna_info,
            self._check_notes, self._check_cause_of_death,
            self._check_clusters, self._check_age,
        ]:
            person_layout.addWidget(cb)

        # Load config values
        self._check_name.setChecked(config.name)
        self._check_birth_date.setChecked(config.birth_date)
        self._check_birth_place.setChecked(config.birth_place)
        self._check_death_date.setChecked(config.death_date)
        self._check_death_place.setChecked(config.death_place)
        self._check_marriage_date.setChecked(config.marriage_date)
        self._check_marriage_place.setChecked(config.marriage_place)
        self._check_occupation.setChecked(config.occupation)
        self._check_photo.setChecked(config.photo)
        self._check_dna_info.setChecked(config.dna_info)
        self._check_notes.setChecked(config.notes)
        self._check_cause_of_death.setChecked(config.cause_of_death)
        self._check_clusters.setChecked(config.clusters)
        self._check_age.setChecked(config.age)

        layout.addWidget(person_group)

        # --- Diagramdjup group ---
        depth_group = QGroupBox("Diagramdjup", tab)
        depth_layout = QFormLayout(depth_group)

        self._spin_ancestry = QSpinBox()
        self._spin_ancestry.setMinimum(1)
        self._spin_ancestry.setMaximum(30)
        self._spin_ancestry.setValue(settings.ancestry_depth)
        depth_layout.addRow("Antal generationer uppåt (anor):", self._spin_ancestry)

        self._check_compact = QCheckBox("Kompakt vy")
        self._check_compact.setToolTip(
            "Minskar vertikalt utrymme för grenar med färre generationer"
        )
        self._check_compact.setChecked(settings.ancestry_compact)
        depth_layout.addRow("", self._check_compact)

        self._spin_descendants = QSpinBox()
        self._spin_descendants.setMinimum(1)
        self._spin_descendants.setMaximum(30)
        self._spin_descendants.setValue(settings.descendants_depth)
        depth_layout.addRow("Antal generationer nedåt (ättlingar):", self._spin_descendants)

        layout.addWidget(depth_group)

        # --- Bakgrundsfärg group ---
        bg_group = QGroupBox("Bakgrundsfärg", tab)
        bg_layout = QHBoxLayout(bg_group)

        self._bg_color_preview = QLabel()
        self._bg_color_preview.setFixedSize(40, 24)
        self._update_color_preview()
        bg_layout.addWidget(self._bg_color_preview)

        self._bg_color_label = QLabel(self._bg_color)
        bg_layout.addWidget(self._bg_color_label)

        btn_pick = QPushButton("Välj färg...")
        btn_pick.clicked.connect(self._on_pick_bg_color)
        bg_layout.addWidget(btn_pick)
        bg_layout.addStretch()

        layout.addWidget(bg_group)

        self._tabs.addTab(tab, "Diagram")

    # ------------------------------------------------------------------
    # Color picker
    # ------------------------------------------------------------------

    def _on_pick_bg_color(self) -> None:
        """Open a color dialog to pick the background color."""
        current = QColor(self._bg_color)
        color = QColorDialog.getColor(current, self, "Välj bakgrundsfärg")
        if color.isValid():
            self._bg_color = color.name()
            self._bg_color_label.setText(self._bg_color)
            self._update_color_preview()

    def _update_color_preview(self) -> None:
        """Update the color preview label background."""
        self._bg_color_preview.setStyleSheet(
            f"background-color: {self._bg_color}; border: 1px solid #888;"
        )

    # ------------------------------------------------------------------
    # Default project actions
    # ------------------------------------------------------------------

    def _on_set_default(self) -> None:
        """Set the current project as the default project."""
        if self._app_settings_service is None or self._current_project_path is None:
            return
        path_str = str(self._current_project_path)
        self._app_settings_service.set_default_project(path_str)
        self._default_label.setText(f"  Projekt: {path_str}")
        self._btn_clear_default.setEnabled(True)

    def _on_clear_default(self) -> None:
        """Clear the default project setting."""
        if self._app_settings_service is None:
            return
        self._app_settings_service.set_default_project(None)
        self._default_label.setText("  Inget standardprojekt angivet")
        self._btn_clear_default.setEnabled(False)

    def _on_startup_radio_changed(self, default_checked: bool) -> None:
        """Enable/disable standard project controls based on radio selection."""
        self._default_label.setEnabled(default_checked)
        self._btn_set_default.setEnabled(
            default_checked and self._current_project_path is not None
        )
        self._btn_clear_default.setEnabled(
            default_checked
            and self._app_settings_service is not None
            and self._app_settings_service.get_default_project() is not None
        )

    def _on_set_folder(self) -> None:
        """Open a directory picker to set the default folder for new projects."""
        if self._app_settings_service is None:
            return
        directory = QFileDialog.getExistingDirectory(
            self,
            "Välj standardmapp för nya projekt",
        )
        if directory:
            self._app_settings_service.set_default_folder(directory)
            self._folder_label.setText(f"Nuvarande: {directory}")
            self._btn_clear_folder.setEnabled(True)

    def _on_clear_folder(self) -> None:
        """Clear the default folder setting."""
        if self._app_settings_service is None:
            return
        self._app_settings_service.set_default_folder(None)
        self._folder_label.setText("Ingen standardmapp angiven")
        self._btn_clear_folder.setEnabled(False)
