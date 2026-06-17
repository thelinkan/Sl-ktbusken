# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'dna_editor.ui'
##
## Created by: Qt User Interface Compiler version 6.11.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QSizePolicy,
    QSpinBox, QTabWidget, QTextEdit, QVBoxLayout,
    QWidget)

class Ui_DnaEditor(object):
    def setupUi(self, DnaEditor):
        if not DnaEditor.objectName():
            DnaEditor.setObjectName(u"DnaEditor")
        DnaEditor.resize(1200, 800)
        self.main_layout = QVBoxLayout(DnaEditor)
        self.main_layout.setObjectName(u"main_layout")
        self.tab_widget = QTabWidget(DnaEditor)
        self.tab_widget.setObjectName(u"tab_widget")
        self.companies_tab = QWidget()
        self.companies_tab.setObjectName(u"companies_tab")
        self.companies_layout = QHBoxLayout(self.companies_tab)
        self.companies_layout.setObjectName(u"companies_layout")
        self.companies_left = QWidget(self.companies_tab)
        self.companies_left.setObjectName(u"companies_left")
        self.companies_left_layout = QVBoxLayout(self.companies_left)
        self.companies_left_layout.setObjectName(u"companies_left_layout")
        self.companies_left_layout.setContentsMargins(0, 0, 0, 0)
        self.companies_list = QListWidget(self.companies_left)
        self.companies_list.setObjectName(u"companies_list")

        self.companies_left_layout.addWidget(self.companies_list)

        self.companies_buttons_layout = QHBoxLayout()
        self.companies_buttons_layout.setObjectName(u"companies_buttons_layout")
        self.add_company_button = QPushButton(self.companies_left)
        self.add_company_button.setObjectName(u"add_company_button")

        self.companies_buttons_layout.addWidget(self.add_company_button)

        self.remove_company_button = QPushButton(self.companies_left)
        self.remove_company_button.setObjectName(u"remove_company_button")

        self.companies_buttons_layout.addWidget(self.remove_company_button)


        self.companies_left_layout.addLayout(self.companies_buttons_layout)


        self.companies_layout.addWidget(self.companies_left)

        self.company_form_group = QGroupBox(self.companies_tab)
        self.company_form_group.setObjectName(u"company_form_group")
        self.company_form_layout = QFormLayout(self.company_form_group)
        self.company_form_layout.setObjectName(u"company_form_layout")
        self.company_name_label = QLabel(self.company_form_group)
        self.company_name_label.setObjectName(u"company_name_label")

        self.company_form_layout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.company_name_label)

        self.company_name_input = QLineEdit(self.company_form_group)
        self.company_name_input.setObjectName(u"company_name_input")
        self.company_name_input.setMaxLength(200)

        self.company_form_layout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.company_name_input)

        self.company_notes_label = QLabel(self.company_form_group)
        self.company_notes_label.setObjectName(u"company_notes_label")

        self.company_form_layout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.company_notes_label)

        self.company_notes_input = QTextEdit(self.company_form_group)
        self.company_notes_input.setObjectName(u"company_notes_input")
        self.company_notes_input.setMaximumSize(QSize(16777215, 100))

        self.company_form_layout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.company_notes_input)

        self.company_logo_label = QLabel(self.company_form_group)
        self.company_logo_label.setObjectName(u"company_logo_label")

        self.company_form_layout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.company_logo_label)

        self.company_logo_input = QLineEdit(self.company_form_group)
        self.company_logo_input.setObjectName(u"company_logo_input")

        self.company_form_layout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.company_logo_input)

        self.save_company_button = QPushButton(self.company_form_group)
        self.save_company_button.setObjectName(u"save_company_button")

        self.company_form_layout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.save_company_button)


        self.companies_layout.addWidget(self.company_form_group)

        self.tab_widget.addTab(self.companies_tab, "")
        self.profiles_tab = QWidget()
        self.profiles_tab.setObjectName(u"profiles_tab")
        self.profiles_layout = QHBoxLayout(self.profiles_tab)
        self.profiles_layout.setObjectName(u"profiles_layout")
        self.profiles_left = QWidget(self.profiles_tab)
        self.profiles_left.setObjectName(u"profiles_left")
        self.profiles_left_layout = QVBoxLayout(self.profiles_left)
        self.profiles_left_layout.setObjectName(u"profiles_left_layout")
        self.profiles_left_layout.setContentsMargins(0, 0, 0, 0)
        self.profiles_list = QListWidget(self.profiles_left)
        self.profiles_list.setObjectName(u"profiles_list")

        self.profiles_left_layout.addWidget(self.profiles_list)

        self.profiles_buttons_layout = QHBoxLayout()
        self.profiles_buttons_layout.setObjectName(u"profiles_buttons_layout")
        self.add_profile_button = QPushButton(self.profiles_left)
        self.add_profile_button.setObjectName(u"add_profile_button")

        self.profiles_buttons_layout.addWidget(self.add_profile_button)

        self.remove_profile_button = QPushButton(self.profiles_left)
        self.remove_profile_button.setObjectName(u"remove_profile_button")

        self.profiles_buttons_layout.addWidget(self.remove_profile_button)


        self.profiles_left_layout.addLayout(self.profiles_buttons_layout)


        self.profiles_layout.addWidget(self.profiles_left)

        self.profile_form_group = QGroupBox(self.profiles_tab)
        self.profile_form_group.setObjectName(u"profile_form_group")
        self.profile_form_layout = QFormLayout(self.profile_form_group)
        self.profile_form_layout.setObjectName(u"profile_form_layout")
        self.profile_person_label = QLabel(self.profile_form_group)
        self.profile_person_label.setObjectName(u"profile_person_label")

        self.profile_form_layout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.profile_person_label)

        self.profile_person_input = QLineEdit(self.profile_form_group)
        self.profile_person_input.setObjectName(u"profile_person_input")

        self.profile_form_layout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.profile_person_input)

        self.profile_company_label = QLabel(self.profile_form_group)
        self.profile_company_label.setObjectName(u"profile_company_label")

        self.profile_form_layout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.profile_company_label)

        self.profile_company_combo = QComboBox(self.profile_form_group)
        self.profile_company_combo.setObjectName(u"profile_company_combo")

        self.profile_form_layout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.profile_company_combo)

        self.profile_test_type_label = QLabel(self.profile_form_group)
        self.profile_test_type_label.setObjectName(u"profile_test_type_label")

        self.profile_form_layout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.profile_test_type_label)

        self.profile_test_type_combo = QComboBox(self.profile_form_group)
        self.profile_test_type_combo.setObjectName(u"profile_test_type_combo")

        self.profile_form_layout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.profile_test_type_combo)

        self.profile_kit_name_label = QLabel(self.profile_form_group)
        self.profile_kit_name_label.setObjectName(u"profile_kit_name_label")

        self.profile_form_layout.setWidget(3, QFormLayout.ItemRole.LabelRole, self.profile_kit_name_label)

        self.profile_kit_name_input = QLineEdit(self.profile_form_group)
        self.profile_kit_name_input.setObjectName(u"profile_kit_name_input")
        self.profile_kit_name_input.setMaxLength(200)

        self.profile_form_layout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.profile_kit_name_input)

        self.profile_kit_id_label = QLabel(self.profile_form_group)
        self.profile_kit_id_label.setObjectName(u"profile_kit_id_label")

        self.profile_form_layout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.profile_kit_id_label)

        self.profile_kit_id_input = QLineEdit(self.profile_form_group)
        self.profile_kit_id_input.setObjectName(u"profile_kit_id_input")
        self.profile_kit_id_input.setMaxLength(100)

        self.profile_form_layout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.profile_kit_id_input)

        self.profile_admin_person_label = QLabel(self.profile_form_group)
        self.profile_admin_person_label.setObjectName(u"profile_admin_person_label")

        self.profile_form_layout.setWidget(5, QFormLayout.ItemRole.LabelRole, self.profile_admin_person_label)

        self.profile_admin_person_input = QLineEdit(self.profile_form_group)
        self.profile_admin_person_input.setObjectName(u"profile_admin_person_input")

        self.profile_form_layout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.profile_admin_person_input)

        self.profile_admin_status_label = QLabel(self.profile_form_group)
        self.profile_admin_status_label.setObjectName(u"profile_admin_status_label")

        self.profile_form_layout.setWidget(6, QFormLayout.ItemRole.LabelRole, self.profile_admin_status_label)

        self.profile_admin_status_combo = QComboBox(self.profile_form_group)
        self.profile_admin_status_combo.setObjectName(u"profile_admin_status_combo")

        self.profile_form_layout.setWidget(6, QFormLayout.ItemRole.FieldRole, self.profile_admin_status_combo)

        self.profile_notes_label = QLabel(self.profile_form_group)
        self.profile_notes_label.setObjectName(u"profile_notes_label")

        self.profile_form_layout.setWidget(7, QFormLayout.ItemRole.LabelRole, self.profile_notes_label)

        self.profile_notes_input = QTextEdit(self.profile_form_group)
        self.profile_notes_input.setObjectName(u"profile_notes_input")
        self.profile_notes_input.setMaximumSize(QSize(16777215, 80))

        self.profile_form_layout.setWidget(7, QFormLayout.ItemRole.FieldRole, self.profile_notes_input)

        self.save_profile_button = QPushButton(self.profile_form_group)
        self.save_profile_button.setObjectName(u"save_profile_button")

        self.profile_form_layout.setWidget(8, QFormLayout.ItemRole.FieldRole, self.save_profile_button)


        self.profiles_layout.addWidget(self.profile_form_group)

        self.tab_widget.addTab(self.profiles_tab, "")
        self.matches_tab = QWidget()
        self.matches_tab.setObjectName(u"matches_tab")
        self.matches_layout = QHBoxLayout(self.matches_tab)
        self.matches_layout.setObjectName(u"matches_layout")
        self.matches_left = QWidget(self.matches_tab)
        self.matches_left.setObjectName(u"matches_left")
        self.matches_left_layout = QVBoxLayout(self.matches_left)
        self.matches_left_layout.setObjectName(u"matches_left_layout")
        self.matches_left_layout.setContentsMargins(0, 0, 0, 0)
        self.matches_list = QListWidget(self.matches_left)
        self.matches_list.setObjectName(u"matches_list")

        self.matches_left_layout.addWidget(self.matches_list)

        self.matches_buttons_layout = QHBoxLayout()
        self.matches_buttons_layout.setObjectName(u"matches_buttons_layout")
        self.add_match_button = QPushButton(self.matches_left)
        self.add_match_button.setObjectName(u"add_match_button")

        self.matches_buttons_layout.addWidget(self.add_match_button)

        self.remove_match_button = QPushButton(self.matches_left)
        self.remove_match_button.setObjectName(u"remove_match_button")

        self.matches_buttons_layout.addWidget(self.remove_match_button)


        self.matches_left_layout.addLayout(self.matches_buttons_layout)


        self.matches_layout.addWidget(self.matches_left)

        self.match_form_group = QGroupBox(self.matches_tab)
        self.match_form_group.setObjectName(u"match_form_group")
        self.match_form_layout = QFormLayout(self.match_form_group)
        self.match_form_layout.setObjectName(u"match_form_layout")
        self.match_profile1_label = QLabel(self.match_form_group)
        self.match_profile1_label.setObjectName(u"match_profile1_label")

        self.match_form_layout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.match_profile1_label)

        self.match_profile1_combo = QComboBox(self.match_form_group)
        self.match_profile1_combo.setObjectName(u"match_profile1_combo")

        self.match_form_layout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.match_profile1_combo)

        self.match_profile2_label = QLabel(self.match_form_group)
        self.match_profile2_label.setObjectName(u"match_profile2_label")

        self.match_form_layout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.match_profile2_label)

        self.match_profile2_combo = QComboBox(self.match_form_group)
        self.match_profile2_combo.setObjectName(u"match_profile2_combo")

        self.match_form_layout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.match_profile2_combo)

        self.match_shared_cm_label = QLabel(self.match_form_group)
        self.match_shared_cm_label.setObjectName(u"match_shared_cm_label")

        self.match_form_layout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.match_shared_cm_label)

        self.match_shared_cm_input = QDoubleSpinBox(self.match_form_group)
        self.match_shared_cm_input.setObjectName(u"match_shared_cm_input")
        self.match_shared_cm_input.setMaximum(7400.000000000000000)
        self.match_shared_cm_input.setDecimals(1)

        self.match_form_layout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.match_shared_cm_input)

        self.match_percentage_label = QLabel(self.match_form_group)
        self.match_percentage_label.setObjectName(u"match_percentage_label")

        self.match_form_layout.setWidget(3, QFormLayout.ItemRole.LabelRole, self.match_percentage_label)

        self.match_percentage_input = QDoubleSpinBox(self.match_form_group)
        self.match_percentage_input.setObjectName(u"match_percentage_input")
        self.match_percentage_input.setMaximum(100.000000000000000)
        self.match_percentage_input.setDecimals(2)

        self.match_form_layout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.match_percentage_input)

        self.match_segment_count_label = QLabel(self.match_form_group)
        self.match_segment_count_label.setObjectName(u"match_segment_count_label")

        self.match_form_layout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.match_segment_count_label)

        self.match_segment_count_input = QSpinBox(self.match_form_group)
        self.match_segment_count_input.setObjectName(u"match_segment_count_input")
        self.match_segment_count_input.setMaximum(10000)

        self.match_form_layout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.match_segment_count_input)

        self.match_largest_segment_label = QLabel(self.match_form_group)
        self.match_largest_segment_label.setObjectName(u"match_largest_segment_label")

        self.match_form_layout.setWidget(5, QFormLayout.ItemRole.LabelRole, self.match_largest_segment_label)

        self.match_largest_segment_input = QDoubleSpinBox(self.match_form_group)
        self.match_largest_segment_input.setObjectName(u"match_largest_segment_input")
        self.match_largest_segment_input.setMaximum(300.000000000000000)
        self.match_largest_segment_input.setDecimals(1)

        self.match_form_layout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.match_largest_segment_input)

        self.match_source_label = QLabel(self.match_form_group)
        self.match_source_label.setObjectName(u"match_source_label")

        self.match_form_layout.setWidget(6, QFormLayout.ItemRole.LabelRole, self.match_source_label)

        self.match_source_combo = QComboBox(self.match_form_group)
        self.match_source_combo.setObjectName(u"match_source_combo")

        self.match_form_layout.setWidget(6, QFormLayout.ItemRole.FieldRole, self.match_source_combo)

        self.match_notes_label = QLabel(self.match_form_group)
        self.match_notes_label.setObjectName(u"match_notes_label")

        self.match_form_layout.setWidget(7, QFormLayout.ItemRole.LabelRole, self.match_notes_label)

        self.match_notes_input = QTextEdit(self.match_form_group)
        self.match_notes_input.setObjectName(u"match_notes_input")
        self.match_notes_input.setMaximumSize(QSize(16777215, 80))

        self.match_form_layout.setWidget(7, QFormLayout.ItemRole.FieldRole, self.match_notes_input)

        self.save_match_button = QPushButton(self.match_form_group)
        self.save_match_button.setObjectName(u"save_match_button")

        self.match_form_layout.setWidget(8, QFormLayout.ItemRole.FieldRole, self.save_match_button)


        self.matches_layout.addWidget(self.match_form_group)

        self.tab_widget.addTab(self.matches_tab, "")
        self.segments_tab = QWidget()
        self.segments_tab.setObjectName(u"segments_tab")
        self.segments_layout = QHBoxLayout(self.segments_tab)
        self.segments_layout.setObjectName(u"segments_layout")
        self.segments_left = QWidget(self.segments_tab)
        self.segments_left.setObjectName(u"segments_left")
        self.segments_left_layout = QVBoxLayout(self.segments_left)
        self.segments_left_layout.setObjectName(u"segments_left_layout")
        self.segments_left_layout.setContentsMargins(0, 0, 0, 0)
        self.segments_list = QListWidget(self.segments_left)
        self.segments_list.setObjectName(u"segments_list")

        self.segments_left_layout.addWidget(self.segments_list)

        self.segments_buttons_layout = QHBoxLayout()
        self.segments_buttons_layout.setObjectName(u"segments_buttons_layout")
        self.add_segment_button = QPushButton(self.segments_left)
        self.add_segment_button.setObjectName(u"add_segment_button")

        self.segments_buttons_layout.addWidget(self.add_segment_button)

        self.remove_segment_button = QPushButton(self.segments_left)
        self.remove_segment_button.setObjectName(u"remove_segment_button")

        self.segments_buttons_layout.addWidget(self.remove_segment_button)


        self.segments_left_layout.addLayout(self.segments_buttons_layout)


        self.segments_layout.addWidget(self.segments_left)

        self.segment_form_group = QGroupBox(self.segments_tab)
        self.segment_form_group.setObjectName(u"segment_form_group")
        self.segment_form_layout = QFormLayout(self.segment_form_group)
        self.segment_form_layout.setObjectName(u"segment_form_layout")
        self.segment_match_label = QLabel(self.segment_form_group)
        self.segment_match_label.setObjectName(u"segment_match_label")

        self.segment_form_layout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.segment_match_label)

        self.segment_match_combo = QComboBox(self.segment_form_group)
        self.segment_match_combo.setObjectName(u"segment_match_combo")

        self.segment_form_layout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.segment_match_combo)

        self.segment_chromosome_label = QLabel(self.segment_form_group)
        self.segment_chromosome_label.setObjectName(u"segment_chromosome_label")

        self.segment_form_layout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.segment_chromosome_label)

        self.segment_chromosome_combo = QComboBox(self.segment_form_group)
        self.segment_chromosome_combo.setObjectName(u"segment_chromosome_combo")

        self.segment_form_layout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.segment_chromosome_combo)

        self.segment_start_label = QLabel(self.segment_form_group)
        self.segment_start_label.setObjectName(u"segment_start_label")

        self.segment_form_layout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.segment_start_label)

        self.segment_start_input = QSpinBox(self.segment_form_group)
        self.segment_start_input.setObjectName(u"segment_start_input")
        self.segment_start_input.setMaximum(999999999)

        self.segment_form_layout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.segment_start_input)

        self.segment_end_label = QLabel(self.segment_form_group)
        self.segment_end_label.setObjectName(u"segment_end_label")

        self.segment_form_layout.setWidget(3, QFormLayout.ItemRole.LabelRole, self.segment_end_label)

        self.segment_end_input = QSpinBox(self.segment_form_group)
        self.segment_end_input.setObjectName(u"segment_end_input")
        self.segment_end_input.setMaximum(999999999)

        self.segment_form_layout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.segment_end_input)

        self.segment_cm_label = QLabel(self.segment_form_group)
        self.segment_cm_label.setObjectName(u"segment_cm_label")

        self.segment_form_layout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.segment_cm_label)

        self.segment_cm_input = QDoubleSpinBox(self.segment_form_group)
        self.segment_cm_input.setObjectName(u"segment_cm_input")
        self.segment_cm_input.setMaximum(7400.000000000000000)
        self.segment_cm_input.setDecimals(2)

        self.segment_form_layout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.segment_cm_input)

        self.segment_snp_label = QLabel(self.segment_form_group)
        self.segment_snp_label.setObjectName(u"segment_snp_label")

        self.segment_form_layout.setWidget(5, QFormLayout.ItemRole.LabelRole, self.segment_snp_label)

        self.segment_snp_input = QSpinBox(self.segment_form_group)
        self.segment_snp_input.setObjectName(u"segment_snp_input")
        self.segment_snp_input.setMaximum(999999)

        self.segment_form_layout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.segment_snp_input)

        self.save_segment_button = QPushButton(self.segment_form_group)
        self.save_segment_button.setObjectName(u"save_segment_button")

        self.segment_form_layout.setWidget(6, QFormLayout.ItemRole.FieldRole, self.save_segment_button)


        self.segments_layout.addWidget(self.segment_form_group)

        self.tab_widget.addTab(self.segments_tab, "")
        self.clusters_tab = QWidget()
        self.clusters_tab.setObjectName(u"clusters_tab")
        self.clusters_layout = QHBoxLayout(self.clusters_tab)
        self.clusters_layout.setObjectName(u"clusters_layout")
        self.clusters_left = QWidget(self.clusters_tab)
        self.clusters_left.setObjectName(u"clusters_left")
        self.clusters_left_layout = QVBoxLayout(self.clusters_left)
        self.clusters_left_layout.setObjectName(u"clusters_left_layout")
        self.clusters_left_layout.setContentsMargins(0, 0, 0, 0)
        self.clusters_list = QListWidget(self.clusters_left)
        self.clusters_list.setObjectName(u"clusters_list")

        self.clusters_left_layout.addWidget(self.clusters_list)

        self.clusters_buttons_layout = QHBoxLayout()
        self.clusters_buttons_layout.setObjectName(u"clusters_buttons_layout")
        self.add_cluster_button = QPushButton(self.clusters_left)
        self.add_cluster_button.setObjectName(u"add_cluster_button")

        self.clusters_buttons_layout.addWidget(self.add_cluster_button)

        self.remove_cluster_button = QPushButton(self.clusters_left)
        self.remove_cluster_button.setObjectName(u"remove_cluster_button")

        self.clusters_buttons_layout.addWidget(self.remove_cluster_button)


        self.clusters_left_layout.addLayout(self.clusters_buttons_layout)


        self.clusters_layout.addWidget(self.clusters_left)

        self.cluster_form_group = QGroupBox(self.clusters_tab)
        self.cluster_form_group.setObjectName(u"cluster_form_group")
        self.cluster_form_layout = QVBoxLayout(self.cluster_form_group)
        self.cluster_form_layout.setObjectName(u"cluster_form_layout")
        self.cluster_fields_layout = QFormLayout()
        self.cluster_fields_layout.setObjectName(u"cluster_fields_layout")
        self.cluster_name_label = QLabel(self.cluster_form_group)
        self.cluster_name_label.setObjectName(u"cluster_name_label")

        self.cluster_fields_layout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.cluster_name_label)

        self.cluster_name_input = QLineEdit(self.cluster_form_group)
        self.cluster_name_input.setObjectName(u"cluster_name_input")
        self.cluster_name_input.setMaxLength(200)

        self.cluster_fields_layout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.cluster_name_input)

        self.cluster_notes_label = QLabel(self.cluster_form_group)
        self.cluster_notes_label.setObjectName(u"cluster_notes_label")

        self.cluster_fields_layout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.cluster_notes_label)

        self.cluster_notes_input = QTextEdit(self.cluster_form_group)
        self.cluster_notes_input.setObjectName(u"cluster_notes_input")
        self.cluster_notes_input.setMaximumSize(QSize(16777215, 60))

        self.cluster_fields_layout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.cluster_notes_input)

        self.cluster_color_label = QLabel(self.cluster_form_group)
        self.cluster_color_label.setObjectName(u"cluster_color_label")

        self.cluster_fields_layout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.cluster_color_label)

        self.cluster_color_input = QLineEdit(self.cluster_form_group)
        self.cluster_color_input.setObjectName(u"cluster_color_input")

        self.cluster_fields_layout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.cluster_color_input)


        self.cluster_form_layout.addLayout(self.cluster_fields_layout)

        self.cluster_members_label = QLabel(self.cluster_form_group)
        self.cluster_members_label.setObjectName(u"cluster_members_label")

        self.cluster_form_layout.addWidget(self.cluster_members_label)

        self.cluster_members_list = QListWidget(self.cluster_form_group)
        self.cluster_members_list.setObjectName(u"cluster_members_list")
        self.cluster_members_list.setMaximumSize(QSize(16777215, 80))

        self.cluster_form_layout.addWidget(self.cluster_members_list)

        self.cluster_members_buttons_layout = QHBoxLayout()
        self.cluster_members_buttons_layout.setObjectName(u"cluster_members_buttons_layout")
        self.cluster_member_input = QLineEdit(self.cluster_form_group)
        self.cluster_member_input.setObjectName(u"cluster_member_input")

        self.cluster_members_buttons_layout.addWidget(self.cluster_member_input)

        self.add_cluster_member_button = QPushButton(self.cluster_form_group)
        self.add_cluster_member_button.setObjectName(u"add_cluster_member_button")

        self.cluster_members_buttons_layout.addWidget(self.add_cluster_member_button)

        self.remove_cluster_member_button = QPushButton(self.cluster_form_group)
        self.remove_cluster_member_button.setObjectName(u"remove_cluster_member_button")

        self.cluster_members_buttons_layout.addWidget(self.remove_cluster_member_button)


        self.cluster_form_layout.addLayout(self.cluster_members_buttons_layout)

        self.cluster_matches_label = QLabel(self.cluster_form_group)
        self.cluster_matches_label.setObjectName(u"cluster_matches_label")

        self.cluster_form_layout.addWidget(self.cluster_matches_label)

        self.cluster_matches_list = QListWidget(self.cluster_form_group)
        self.cluster_matches_list.setObjectName(u"cluster_matches_list")
        self.cluster_matches_list.setMaximumSize(QSize(16777215, 80))

        self.cluster_form_layout.addWidget(self.cluster_matches_list)

        self.cluster_matches_buttons_layout = QHBoxLayout()
        self.cluster_matches_buttons_layout.setObjectName(u"cluster_matches_buttons_layout")
        self.cluster_match_combo = QComboBox(self.cluster_form_group)
        self.cluster_match_combo.setObjectName(u"cluster_match_combo")

        self.cluster_matches_buttons_layout.addWidget(self.cluster_match_combo)

        self.add_cluster_match_button = QPushButton(self.cluster_form_group)
        self.add_cluster_match_button.setObjectName(u"add_cluster_match_button")

        self.cluster_matches_buttons_layout.addWidget(self.add_cluster_match_button)

        self.remove_cluster_match_button = QPushButton(self.cluster_form_group)
        self.remove_cluster_match_button.setObjectName(u"remove_cluster_match_button")

        self.cluster_matches_buttons_layout.addWidget(self.remove_cluster_match_button)


        self.cluster_form_layout.addLayout(self.cluster_matches_buttons_layout)

        self.save_cluster_button = QPushButton(self.cluster_form_group)
        self.save_cluster_button.setObjectName(u"save_cluster_button")

        self.cluster_form_layout.addWidget(self.save_cluster_button)


        self.clusters_layout.addWidget(self.cluster_form_group)

        self.tab_widget.addTab(self.clusters_tab, "")
        self.triangulations_tab = QWidget()
        self.triangulations_tab.setObjectName(u"triangulations_tab")
        self.triangulations_layout = QHBoxLayout(self.triangulations_tab)
        self.triangulations_layout.setObjectName(u"triangulations_layout")
        self.triangulations_left = QWidget(self.triangulations_tab)
        self.triangulations_left.setObjectName(u"triangulations_left")
        self.triangulations_left_layout = QVBoxLayout(self.triangulations_left)
        self.triangulations_left_layout.setObjectName(u"triangulations_left_layout")
        self.triangulations_left_layout.setContentsMargins(0, 0, 0, 0)
        self.triangulations_list = QListWidget(self.triangulations_left)
        self.triangulations_list.setObjectName(u"triangulations_list")

        self.triangulations_left_layout.addWidget(self.triangulations_list)

        self.triangulations_buttons_layout = QHBoxLayout()
        self.triangulations_buttons_layout.setObjectName(u"triangulations_buttons_layout")
        self.add_triangulation_button = QPushButton(self.triangulations_left)
        self.add_triangulation_button.setObjectName(u"add_triangulation_button")

        self.triangulations_buttons_layout.addWidget(self.add_triangulation_button)

        self.remove_triangulation_button = QPushButton(self.triangulations_left)
        self.remove_triangulation_button.setObjectName(u"remove_triangulation_button")

        self.triangulations_buttons_layout.addWidget(self.remove_triangulation_button)


        self.triangulations_left_layout.addLayout(self.triangulations_buttons_layout)


        self.triangulations_layout.addWidget(self.triangulations_left)

        self.triangulation_form_group = QGroupBox(self.triangulations_tab)
        self.triangulation_form_group.setObjectName(u"triangulation_form_group")
        self.triangulation_form_layout = QVBoxLayout(self.triangulation_form_group)
        self.triangulation_form_layout.setObjectName(u"triangulation_form_layout")
        self.triangulation_fields_layout = QFormLayout()
        self.triangulation_fields_layout.setObjectName(u"triangulation_fields_layout")
        self.triangulation_company_label = QLabel(self.triangulation_form_group)
        self.triangulation_company_label.setObjectName(u"triangulation_company_label")

        self.triangulation_fields_layout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.triangulation_company_label)

        self.triangulation_company_combo = QComboBox(self.triangulation_form_group)
        self.triangulation_company_combo.setObjectName(u"triangulation_company_combo")

        self.triangulation_fields_layout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.triangulation_company_combo)

        self.triangulation_chromosome_label = QLabel(self.triangulation_form_group)
        self.triangulation_chromosome_label.setObjectName(u"triangulation_chromosome_label")

        self.triangulation_fields_layout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.triangulation_chromosome_label)

        self.triangulation_chromosome_combo = QComboBox(self.triangulation_form_group)
        self.triangulation_chromosome_combo.setObjectName(u"triangulation_chromosome_combo")

        self.triangulation_fields_layout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.triangulation_chromosome_combo)

        self.triangulation_start_label = QLabel(self.triangulation_form_group)
        self.triangulation_start_label.setObjectName(u"triangulation_start_label")

        self.triangulation_fields_layout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.triangulation_start_label)

        self.triangulation_start_input = QSpinBox(self.triangulation_form_group)
        self.triangulation_start_input.setObjectName(u"triangulation_start_input")
        self.triangulation_start_input.setMaximum(999999999)

        self.triangulation_fields_layout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.triangulation_start_input)

        self.triangulation_end_label = QLabel(self.triangulation_form_group)
        self.triangulation_end_label.setObjectName(u"triangulation_end_label")

        self.triangulation_fields_layout.setWidget(3, QFormLayout.ItemRole.LabelRole, self.triangulation_end_label)

        self.triangulation_end_input = QSpinBox(self.triangulation_form_group)
        self.triangulation_end_input.setObjectName(u"triangulation_end_input")
        self.triangulation_end_input.setMaximum(999999999)

        self.triangulation_fields_layout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.triangulation_end_input)

        self.triangulation_cluster_label = QLabel(self.triangulation_form_group)
        self.triangulation_cluster_label.setObjectName(u"triangulation_cluster_label")

        self.triangulation_fields_layout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.triangulation_cluster_label)

        self.triangulation_cluster_combo = QComboBox(self.triangulation_form_group)
        self.triangulation_cluster_combo.setObjectName(u"triangulation_cluster_combo")

        self.triangulation_fields_layout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.triangulation_cluster_combo)

        self.triangulation_notes_label = QLabel(self.triangulation_form_group)
        self.triangulation_notes_label.setObjectName(u"triangulation_notes_label")

        self.triangulation_fields_layout.setWidget(5, QFormLayout.ItemRole.LabelRole, self.triangulation_notes_label)

        self.triangulation_notes_input = QTextEdit(self.triangulation_form_group)
        self.triangulation_notes_input.setObjectName(u"triangulation_notes_input")
        self.triangulation_notes_input.setMaximumSize(QSize(16777215, 60))

        self.triangulation_fields_layout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.triangulation_notes_input)


        self.triangulation_form_layout.addLayout(self.triangulation_fields_layout)

        self.triangulation_segments_label = QLabel(self.triangulation_form_group)
        self.triangulation_segments_label.setObjectName(u"triangulation_segments_label")

        self.triangulation_form_layout.addWidget(self.triangulation_segments_label)

        self.triangulation_segments_list = QListWidget(self.triangulation_form_group)
        self.triangulation_segments_list.setObjectName(u"triangulation_segments_list")
        self.triangulation_segments_list.setMaximumSize(QSize(16777215, 70))

        self.triangulation_form_layout.addWidget(self.triangulation_segments_list)

        self.triangulation_segments_buttons_layout = QHBoxLayout()
        self.triangulation_segments_buttons_layout.setObjectName(u"triangulation_segments_buttons_layout")
        self.triangulation_segment_input = QLineEdit(self.triangulation_form_group)
        self.triangulation_segment_input.setObjectName(u"triangulation_segment_input")

        self.triangulation_segments_buttons_layout.addWidget(self.triangulation_segment_input)

        self.add_triangulation_segment_button = QPushButton(self.triangulation_form_group)
        self.add_triangulation_segment_button.setObjectName(u"add_triangulation_segment_button")

        self.triangulation_segments_buttons_layout.addWidget(self.add_triangulation_segment_button)

        self.remove_triangulation_segment_button = QPushButton(self.triangulation_form_group)
        self.remove_triangulation_segment_button.setObjectName(u"remove_triangulation_segment_button")

        self.triangulation_segments_buttons_layout.addWidget(self.remove_triangulation_segment_button)


        self.triangulation_form_layout.addLayout(self.triangulation_segments_buttons_layout)

        self.triangulation_profiles_label = QLabel(self.triangulation_form_group)
        self.triangulation_profiles_label.setObjectName(u"triangulation_profiles_label")

        self.triangulation_form_layout.addWidget(self.triangulation_profiles_label)

        self.triangulation_profiles_list = QListWidget(self.triangulation_form_group)
        self.triangulation_profiles_list.setObjectName(u"triangulation_profiles_list")
        self.triangulation_profiles_list.setMaximumSize(QSize(16777215, 70))

        self.triangulation_form_layout.addWidget(self.triangulation_profiles_list)

        self.triangulation_profiles_buttons_layout = QHBoxLayout()
        self.triangulation_profiles_buttons_layout.setObjectName(u"triangulation_profiles_buttons_layout")
        self.triangulation_profile_input = QLineEdit(self.triangulation_form_group)
        self.triangulation_profile_input.setObjectName(u"triangulation_profile_input")

        self.triangulation_profiles_buttons_layout.addWidget(self.triangulation_profile_input)

        self.add_triangulation_profile_button = QPushButton(self.triangulation_form_group)
        self.add_triangulation_profile_button.setObjectName(u"add_triangulation_profile_button")

        self.triangulation_profiles_buttons_layout.addWidget(self.add_triangulation_profile_button)

        self.remove_triangulation_profile_button = QPushButton(self.triangulation_form_group)
        self.remove_triangulation_profile_button.setObjectName(u"remove_triangulation_profile_button")

        self.triangulation_profiles_buttons_layout.addWidget(self.remove_triangulation_profile_button)


        self.triangulation_form_layout.addLayout(self.triangulation_profiles_buttons_layout)

        self.save_triangulation_button = QPushButton(self.triangulation_form_group)
        self.save_triangulation_button.setObjectName(u"save_triangulation_button")

        self.triangulation_form_layout.addWidget(self.save_triangulation_button)


        self.triangulations_layout.addWidget(self.triangulation_form_group)

        self.tab_widget.addTab(self.triangulations_tab, "")

        self.main_layout.addWidget(self.tab_widget)

        self.status_label = QLabel(DnaEditor)
        self.status_label.setObjectName(u"status_label")

        self.main_layout.addWidget(self.status_label)


        self.retranslateUi(DnaEditor)

        self.tab_widget.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(DnaEditor)
    # setupUi

    def retranslateUi(self, DnaEditor):
        DnaEditor.setWindowTitle(QCoreApplication.translate("DnaEditor", u"DNA-redigerare", None))
        self.add_company_button.setText(QCoreApplication.translate("DnaEditor", u"L\u00e4gg till", None))
        self.remove_company_button.setText(QCoreApplication.translate("DnaEditor", u"Ta bort", None))
        self.company_form_group.setTitle(QCoreApplication.translate("DnaEditor", u"F\u00f6retagsuppgifter", None))
        self.company_name_label.setText(QCoreApplication.translate("DnaEditor", u"Namn:", None))
        self.company_notes_label.setText(QCoreApplication.translate("DnaEditor", u"Anteckningar:", None))
        self.company_logo_label.setText(QCoreApplication.translate("DnaEditor", u"Logo media-ID:", None))
        self.company_logo_input.setPlaceholderText(QCoreApplication.translate("DnaEditor", u"Media-ID f\u00f6r logotyp", None))
        self.save_company_button.setText(QCoreApplication.translate("DnaEditor", u"Spara f\u00f6retag", None))
        self.tab_widget.setTabText(self.tab_widget.indexOf(self.companies_tab), QCoreApplication.translate("DnaEditor", u"F\u00f6retag", None))
        self.add_profile_button.setText(QCoreApplication.translate("DnaEditor", u"L\u00e4gg till", None))
        self.remove_profile_button.setText(QCoreApplication.translate("DnaEditor", u"Ta bort", None))
        self.profile_form_group.setTitle(QCoreApplication.translate("DnaEditor", u"Profiluppgifter", None))
        self.profile_person_label.setText(QCoreApplication.translate("DnaEditor", u"Person-ID:", None))
        self.profile_person_input.setPlaceholderText(QCoreApplication.translate("DnaEditor", u"ID f\u00f6r person", None))
        self.profile_company_label.setText(QCoreApplication.translate("DnaEditor", u"F\u00f6retag:", None))
        self.profile_test_type_label.setText(QCoreApplication.translate("DnaEditor", u"Testtyp:", None))
        self.profile_kit_name_label.setText(QCoreApplication.translate("DnaEditor", u"Kit-namn:", None))
        self.profile_kit_id_label.setText(QCoreApplication.translate("DnaEditor", u"Kit-ID:", None))
        self.profile_admin_person_label.setText(QCoreApplication.translate("DnaEditor", u"Admin person-ID:", None))
        self.profile_admin_person_input.setPlaceholderText(QCoreApplication.translate("DnaEditor", u"ID f\u00f6r administrat\u00f6r", None))
        self.profile_admin_status_label.setText(QCoreApplication.translate("DnaEditor", u"Adminstatus:", None))
        self.profile_notes_label.setText(QCoreApplication.translate("DnaEditor", u"Anteckningar:", None))
        self.save_profile_button.setText(QCoreApplication.translate("DnaEditor", u"Spara profil", None))
        self.tab_widget.setTabText(self.tab_widget.indexOf(self.profiles_tab), QCoreApplication.translate("DnaEditor", u"Profiler", None))
        self.add_match_button.setText(QCoreApplication.translate("DnaEditor", u"L\u00e4gg till", None))
        self.remove_match_button.setText(QCoreApplication.translate("DnaEditor", u"Ta bort", None))
        self.match_form_group.setTitle(QCoreApplication.translate("DnaEditor", u"Matchningsuppgifter", None))
        self.match_profile1_label.setText(QCoreApplication.translate("DnaEditor", u"Profil 1:", None))
        self.match_profile2_label.setText(QCoreApplication.translate("DnaEditor", u"Profil 2:", None))
        self.match_shared_cm_label.setText(QCoreApplication.translate("DnaEditor", u"Delad cM:", None))
        self.match_percentage_label.setText(QCoreApplication.translate("DnaEditor", u"Procent:", None))
        self.match_segment_count_label.setText(QCoreApplication.translate("DnaEditor", u"Antal segment:", None))
        self.match_largest_segment_label.setText(QCoreApplication.translate("DnaEditor", u"St\u00f6rsta segment (cM):", None))
        self.match_source_label.setText(QCoreApplication.translate("DnaEditor", u"K\u00e4lla:", None))
        self.match_notes_label.setText(QCoreApplication.translate("DnaEditor", u"Anteckningar:", None))
        self.save_match_button.setText(QCoreApplication.translate("DnaEditor", u"Spara matchning", None))
        self.tab_widget.setTabText(self.tab_widget.indexOf(self.matches_tab), QCoreApplication.translate("DnaEditor", u"Matchningar", None))
        self.add_segment_button.setText(QCoreApplication.translate("DnaEditor", u"L\u00e4gg till", None))
        self.remove_segment_button.setText(QCoreApplication.translate("DnaEditor", u"Ta bort", None))
        self.segment_form_group.setTitle(QCoreApplication.translate("DnaEditor", u"Segmentuppgifter", None))
        self.segment_match_label.setText(QCoreApplication.translate("DnaEditor", u"Matchning:", None))
        self.segment_chromosome_label.setText(QCoreApplication.translate("DnaEditor", u"Kromosom:", None))
        self.segment_start_label.setText(QCoreApplication.translate("DnaEditor", u"Startposition:", None))
        self.segment_end_label.setText(QCoreApplication.translate("DnaEditor", u"Slutposition:", None))
        self.segment_cm_label.setText(QCoreApplication.translate("DnaEditor", u"cM:", None))
        self.segment_snp_label.setText(QCoreApplication.translate("DnaEditor", u"SNP-antal:", None))
        self.save_segment_button.setText(QCoreApplication.translate("DnaEditor", u"Spara segment", None))
        self.tab_widget.setTabText(self.tab_widget.indexOf(self.segments_tab), QCoreApplication.translate("DnaEditor", u"Segment", None))
        self.add_cluster_button.setText(QCoreApplication.translate("DnaEditor", u"L\u00e4gg till", None))
        self.remove_cluster_button.setText(QCoreApplication.translate("DnaEditor", u"Ta bort", None))
        self.cluster_form_group.setTitle(QCoreApplication.translate("DnaEditor", u"Klusteruppgifter", None))
        self.cluster_name_label.setText(QCoreApplication.translate("DnaEditor", u"Namn:", None))
        self.cluster_notes_label.setText(QCoreApplication.translate("DnaEditor", u"Anteckningar:", None))
        self.cluster_color_label.setText(QCoreApplication.translate("DnaEditor", u"F\u00e4rg:", None))
        self.cluster_color_input.setPlaceholderText(QCoreApplication.translate("DnaEditor", u"#RRGGBB", None))
        self.cluster_members_label.setText(QCoreApplication.translate("DnaEditor", u"Medlemmar (person-ID):", None))
        self.cluster_member_input.setPlaceholderText(QCoreApplication.translate("DnaEditor", u"Person-ID", None))
        self.add_cluster_member_button.setText(QCoreApplication.translate("DnaEditor", u"L\u00e4gg till", None))
        self.remove_cluster_member_button.setText(QCoreApplication.translate("DnaEditor", u"Ta bort", None))
        self.cluster_matches_label.setText(QCoreApplication.translate("DnaEditor", u"Associerade matchningar:", None))
        self.add_cluster_match_button.setText(QCoreApplication.translate("DnaEditor", u"L\u00e4gg till", None))
        self.remove_cluster_match_button.setText(QCoreApplication.translate("DnaEditor", u"Ta bort", None))
        self.save_cluster_button.setText(QCoreApplication.translate("DnaEditor", u"Spara kluster", None))
        self.tab_widget.setTabText(self.tab_widget.indexOf(self.clusters_tab), QCoreApplication.translate("DnaEditor", u"Kluster", None))
        self.add_triangulation_button.setText(QCoreApplication.translate("DnaEditor", u"L\u00e4gg till", None))
        self.remove_triangulation_button.setText(QCoreApplication.translate("DnaEditor", u"Ta bort", None))
        self.triangulation_form_group.setTitle(QCoreApplication.translate("DnaEditor", u"Trianguleringsuppgifter", None))
        self.triangulation_company_label.setText(QCoreApplication.translate("DnaEditor", u"F\u00f6retag:", None))
        self.triangulation_chromosome_label.setText(QCoreApplication.translate("DnaEditor", u"Kromosom:", None))
        self.triangulation_start_label.setText(QCoreApplication.translate("DnaEditor", u"\u00d6verlappning start:", None))
        self.triangulation_end_label.setText(QCoreApplication.translate("DnaEditor", u"\u00d6verlappning slut:", None))
        self.triangulation_cluster_label.setText(QCoreApplication.translate("DnaEditor", u"Kluster (valfritt):", None))
        self.triangulation_notes_label.setText(QCoreApplication.translate("DnaEditor", u"Anteckningar:", None))
        self.triangulation_segments_label.setText(QCoreApplication.translate("DnaEditor", u"Segment-ID:", None))
        self.triangulation_segment_input.setPlaceholderText(QCoreApplication.translate("DnaEditor", u"Segment-ID", None))
        self.add_triangulation_segment_button.setText(QCoreApplication.translate("DnaEditor", u"L\u00e4gg till", None))
        self.remove_triangulation_segment_button.setText(QCoreApplication.translate("DnaEditor", u"Ta bort", None))
        self.triangulation_profiles_label.setText(QCoreApplication.translate("DnaEditor", u"Profil-ID:", None))
        self.triangulation_profile_input.setPlaceholderText(QCoreApplication.translate("DnaEditor", u"Profil-ID", None))
        self.add_triangulation_profile_button.setText(QCoreApplication.translate("DnaEditor", u"L\u00e4gg till", None))
        self.remove_triangulation_profile_button.setText(QCoreApplication.translate("DnaEditor", u"Ta bort", None))
        self.save_triangulation_button.setText(QCoreApplication.translate("DnaEditor", u"Spara triangulering", None))
        self.tab_widget.setTabText(self.tab_widget.indexOf(self.triangulations_tab), QCoreApplication.translate("DnaEditor", u"Triangulering", None))
        self.status_label.setText("")
        self.status_label.setStyleSheet(QCoreApplication.translate("DnaEditor", u"color: red;", None))
    # retranslateUi

