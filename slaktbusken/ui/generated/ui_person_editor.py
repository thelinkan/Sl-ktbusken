# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'person_editor.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QSizePolicy,
    QSpacerItem, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget)

class Ui_PersonEditor(object):
    def setupUi(self, PersonEditor):
        if not PersonEditor.objectName():
            PersonEditor.setObjectName(u"PersonEditor")
        PersonEditor.resize(700, 550)
        self.main_layout = QVBoxLayout(PersonEditor)
        self.main_layout.setObjectName(u"main_layout")
        self.tab_widget = QTabWidget(PersonEditor)
        self.tab_widget.setObjectName(u"tab_widget")
        self.names_tab = QWidget()
        self.names_tab.setObjectName(u"names_tab")
        self.names_tab_layout = QVBoxLayout(self.names_tab)
        self.names_tab_layout.setObjectName(u"names_tab_layout")
        self.sex_layout = QHBoxLayout()
        self.sex_layout.setObjectName(u"sex_layout")
        self.sex_label = QLabel(self.names_tab)
        self.sex_label.setObjectName(u"sex_label")

        self.sex_layout.addWidget(self.sex_label)

        self.sex_combo = QComboBox(self.names_tab)
        self.sex_combo.addItem("")
        self.sex_combo.addItem("")
        self.sex_combo.addItem("")
        self.sex_combo.addItem("")
        self.sex_combo.setObjectName(u"sex_combo")

        self.sex_layout.addWidget(self.sex_combo)

        self.title_label = QLabel(self.names_tab)
        self.title_label.setObjectName(u"title_label")

        self.sex_layout.addWidget(self.title_label)

        self.title_input = QLineEdit(self.names_tab)
        self.title_input.setObjectName(u"title_input")
        self.title_input.setMaxLength(100)

        self.sex_layout.addWidget(self.title_input)

        self.occupation_label = QLabel(self.names_tab)
        self.occupation_label.setObjectName(u"occupation_label")

        self.sex_layout.addWidget(self.occupation_label)

        self.occupation_input = QLineEdit(self.names_tab)
        self.occupation_input.setObjectName(u"occupation_input")
        self.occupation_input.setMaxLength(100)

        self.sex_layout.addWidget(self.occupation_input)


        self.names_tab_layout.addLayout(self.sex_layout)

        self.names_table = QTableWidget(self.names_tab)
        if (self.names_table.columnCount() < 3):
            self.names_table.setColumnCount(3)
        __qtablewidgetitem = QTableWidgetItem()
        self.names_table.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.names_table.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.names_table.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        self.names_table.setObjectName(u"names_table")
        self.names_table.setColumnCount(3)
        self.names_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.names_table.setSelectionMode(QAbstractItemView.SingleSelection)

        self.names_tab_layout.addWidget(self.names_table)

        self.names_buttons_layout = QHBoxLayout()
        self.names_buttons_layout.setObjectName(u"names_buttons_layout")
        self.add_name_button = QPushButton(self.names_tab)
        self.add_name_button.setObjectName(u"add_name_button")

        self.names_buttons_layout.addWidget(self.add_name_button)

        self.edit_name_button = QPushButton(self.names_tab)
        self.edit_name_button.setObjectName(u"edit_name_button")

        self.names_buttons_layout.addWidget(self.edit_name_button)

        self.remove_name_button = QPushButton(self.names_tab)
        self.remove_name_button.setObjectName(u"remove_name_button")

        self.names_buttons_layout.addWidget(self.remove_name_button)

        self.names_buttons_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.names_buttons_layout.addItem(self.names_buttons_spacer)


        self.names_tab_layout.addLayout(self.names_buttons_layout)

        self.name_edit_layout = QHBoxLayout()
        self.name_edit_layout.setObjectName(u"name_edit_layout")
        self.name_type_label = QLabel(self.names_tab)
        self.name_type_label.setObjectName(u"name_type_label")

        self.name_edit_layout.addWidget(self.name_type_label)

        self.name_type_combo = QComboBox(self.names_tab)
        self.name_type_combo.addItem("")
        self.name_type_combo.addItem("")
        self.name_type_combo.addItem("")
        self.name_type_combo.addItem("")
        self.name_type_combo.setObjectName(u"name_type_combo")

        self.name_edit_layout.addWidget(self.name_type_combo)

        self.given_name_label = QLabel(self.names_tab)
        self.given_name_label.setObjectName(u"given_name_label")

        self.name_edit_layout.addWidget(self.given_name_label)

        self.given_name_input = QLineEdit(self.names_tab)
        self.given_name_input.setObjectName(u"given_name_input")
        self.given_name_input.setMaxLength(100)

        self.name_edit_layout.addWidget(self.given_name_input)

        self.surname_label = QLabel(self.names_tab)
        self.surname_label.setObjectName(u"surname_label")

        self.name_edit_layout.addWidget(self.surname_label)

        self.surname_input = QLineEdit(self.names_tab)
        self.surname_input.setObjectName(u"surname_input")
        self.surname_input.setMaxLength(100)

        self.name_edit_layout.addWidget(self.surname_input)


        self.names_tab_layout.addLayout(self.name_edit_layout)

        self.notes_label = QLabel(self.names_tab)
        self.notes_label.setObjectName(u"notes_label")

        self.names_tab_layout.addWidget(self.notes_label)

        self.notes_input = QPlainTextEdit(self.names_tab)
        self.notes_input.setObjectName(u"notes_input")
        self.notes_input.setMaximumSize(QSize(16777215, 80))

        self.names_tab_layout.addWidget(self.notes_input)

        self.tab_widget.addTab(self.names_tab, "")
        self.events_tab = QWidget()
        self.events_tab.setObjectName(u"events_tab")
        self.events_tab_layout = QVBoxLayout(self.events_tab)
        self.events_tab_layout.setObjectName(u"events_tab_layout")
        self.events_list = QListWidget(self.events_tab)
        self.events_list.setObjectName(u"events_list")

        self.events_tab_layout.addWidget(self.events_list)

        self.events_buttons_layout = QHBoxLayout()
        self.events_buttons_layout.setObjectName(u"events_buttons_layout")
        self.add_event_button = QPushButton(self.events_tab)
        self.add_event_button.setObjectName(u"add_event_button")

        self.events_buttons_layout.addWidget(self.add_event_button)

        self.remove_event_button = QPushButton(self.events_tab)
        self.remove_event_button.setObjectName(u"remove_event_button")

        self.events_buttons_layout.addWidget(self.remove_event_button)

        self.events_buttons_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.events_buttons_layout.addItem(self.events_buttons_spacer)


        self.events_tab_layout.addLayout(self.events_buttons_layout)

        self.tab_widget.addTab(self.events_tab, "")
        self.photos_tab = QWidget()
        self.photos_tab.setObjectName(u"photos_tab")
        self.photos_tab_layout = QVBoxLayout(self.photos_tab)
        self.photos_tab_layout.setObjectName(u"photos_tab_layout")
        self.profile_photo_layout = QHBoxLayout()
        self.profile_photo_layout.setObjectName(u"profile_photo_layout")
        self.profile_photo_label = QLabel(self.photos_tab)
        self.profile_photo_label.setObjectName(u"profile_photo_label")

        self.profile_photo_layout.addWidget(self.profile_photo_label)

        self.profile_photo_display = QLabel(self.photos_tab)
        self.profile_photo_display.setObjectName(u"profile_photo_display")
        self.profile_photo_display.setMinimumSize(QSize(100, 100))
        self.profile_photo_display.setMaximumSize(QSize(100, 100))
        self.profile_photo_display.setAlignment(Qt.AlignCenter)

        self.profile_photo_layout.addWidget(self.profile_photo_display)

        self.select_profile_button = QPushButton(self.photos_tab)
        self.select_profile_button.setObjectName(u"select_profile_button")

        self.profile_photo_layout.addWidget(self.select_profile_button)

        self.profile_photo_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.profile_photo_layout.addItem(self.profile_photo_spacer)


        self.photos_tab_layout.addLayout(self.profile_photo_layout)

        self.media_list_label = QLabel(self.photos_tab)
        self.media_list_label.setObjectName(u"media_list_label")

        self.photos_tab_layout.addWidget(self.media_list_label)

        self.media_list = QListWidget(self.photos_tab)
        self.media_list.setObjectName(u"media_list")

        self.photos_tab_layout.addWidget(self.media_list)

        self.tab_widget.addTab(self.photos_tab, "")
        self.dna_tab = QWidget()
        self.dna_tab.setObjectName(u"dna_tab")
        self.dna_tab_layout = QVBoxLayout(self.dna_tab)
        self.dna_tab_layout.setObjectName(u"dna_tab_layout")
        self.dna_profiles_label = QLabel(self.dna_tab)
        self.dna_profiles_label.setObjectName(u"dna_profiles_label")

        self.dna_tab_layout.addWidget(self.dna_profiles_label)

        self.dna_profiles_list = QListWidget(self.dna_tab)
        self.dna_profiles_list.setObjectName(u"dna_profiles_list")

        self.dna_tab_layout.addWidget(self.dna_profiles_list)

        self.dna_matches_label = QLabel(self.dna_tab)
        self.dna_matches_label.setObjectName(u"dna_matches_label")

        self.dna_tab_layout.addWidget(self.dna_matches_label)

        self.dna_matches_list = QListWidget(self.dna_tab)
        self.dna_matches_list.setObjectName(u"dna_matches_list")

        self.dna_tab_layout.addWidget(self.dna_matches_list)

        self.dna_clusters_label = QLabel(self.dna_tab)
        self.dna_clusters_label.setObjectName(u"dna_clusters_label")

        self.dna_tab_layout.addWidget(self.dna_clusters_label)

        self.dna_clusters_list = QListWidget(self.dna_tab)
        self.dna_clusters_list.setObjectName(u"dna_clusters_list")

        self.dna_tab_layout.addWidget(self.dna_clusters_list)

        self.tab_widget.addTab(self.dna_tab, "")

        self.main_layout.addWidget(self.tab_widget)

        self.status_label = QLabel(PersonEditor)
        self.status_label.setObjectName(u"status_label")

        self.main_layout.addWidget(self.status_label)

        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.setObjectName(u"buttons_layout")
        self.buttons_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.buttons_layout.addItem(self.buttons_spacer)

        self.save_button = QPushButton(PersonEditor)
        self.save_button.setObjectName(u"save_button")

        self.buttons_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton(PersonEditor)
        self.cancel_button.setObjectName(u"cancel_button")

        self.buttons_layout.addWidget(self.cancel_button)


        self.main_layout.addLayout(self.buttons_layout)


        self.retranslateUi(PersonEditor)

        self.tab_widget.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(PersonEditor)
    # setupUi

    def retranslateUi(self, PersonEditor):
        PersonEditor.setWindowTitle(QCoreApplication.translate("PersonEditor", u"Personredigerare", None))
        self.sex_label.setText(QCoreApplication.translate("PersonEditor", u"K\u00f6n:", None))
        self.sex_combo.setItemText(0, QCoreApplication.translate("PersonEditor", u"M", None))
        self.sex_combo.setItemText(1, QCoreApplication.translate("PersonEditor", u"F", None))
        self.sex_combo.setItemText(2, QCoreApplication.translate("PersonEditor", u"X", None))
        self.sex_combo.setItemText(3, QCoreApplication.translate("PersonEditor", u"U", None))

        self.title_label.setText(QCoreApplication.translate("PersonEditor", u"Titel:", None))
        self.title_input.setPlaceholderText(QCoreApplication.translate("PersonEditor", u"t.ex. Fil.Dr", None))
        self.occupation_label.setText(QCoreApplication.translate("PersonEditor", u"Yrke:", None))
        self.occupation_input.setPlaceholderText(QCoreApplication.translate("PersonEditor", u"t.ex. Lektor", None))
        ___qtablewidgetitem = self.names_table.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("PersonEditor", u"Typ", None))
        ___qtablewidgetitem1 = self.names_table.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("PersonEditor", u"F\u00f6rnamn", None))
        ___qtablewidgetitem2 = self.names_table.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("PersonEditor", u"Efternamn", None))
        self.add_name_button.setText(QCoreApplication.translate("PersonEditor", u"L\u00e4gg till namn", None))
        self.edit_name_button.setText(QCoreApplication.translate("PersonEditor", u"Redigera namn", None))
        self.remove_name_button.setText(QCoreApplication.translate("PersonEditor", u"Ta bort namn", None))
        self.name_type_label.setText(QCoreApplication.translate("PersonEditor", u"Namntyp:", None))
        self.name_type_combo.setItemText(0, QCoreApplication.translate("PersonEditor", u"birth", None))
        self.name_type_combo.setItemText(1, QCoreApplication.translate("PersonEditor", u"married", None))
        self.name_type_combo.setItemText(2, QCoreApplication.translate("PersonEditor", u"adopted", None))
        self.name_type_combo.setItemText(3, QCoreApplication.translate("PersonEditor", u"other", None))

        self.given_name_label.setText(QCoreApplication.translate("PersonEditor", u"F\u00f6rnamn:", None))
        self.surname_label.setText(QCoreApplication.translate("PersonEditor", u"Efternamn:", None))
        self.notes_label.setText(QCoreApplication.translate("PersonEditor", u"Anteckningar:", None))
        self.tab_widget.setTabText(self.tab_widget.indexOf(self.names_tab), QCoreApplication.translate("PersonEditor", u"Namn", None))
        self.add_event_button.setText(QCoreApplication.translate("PersonEditor", u"L\u00e4gg till h\u00e4ndelse", None))
        self.remove_event_button.setText(QCoreApplication.translate("PersonEditor", u"Ta bort h\u00e4ndelse", None))
        self.tab_widget.setTabText(self.tab_widget.indexOf(self.events_tab), QCoreApplication.translate("PersonEditor", u"H\u00e4ndelser", None))
        self.profile_photo_label.setText(QCoreApplication.translate("PersonEditor", u"Profilbild:", None))
        self.profile_photo_display.setText(QCoreApplication.translate("PersonEditor", u"Ingen bild", None))
        self.profile_photo_display.setStyleSheet(QCoreApplication.translate("PersonEditor", u"border: 1px solid gray;", None))
        self.select_profile_button.setText(QCoreApplication.translate("PersonEditor", u"V\u00e4lj profilbild", None))
        self.media_list_label.setText(QCoreApplication.translate("PersonEditor", u"L\u00e4nkade foton:", None))
        self.tab_widget.setTabText(self.tab_widget.indexOf(self.photos_tab), QCoreApplication.translate("PersonEditor", u"Foton", None))
        self.dna_profiles_label.setText(QCoreApplication.translate("PersonEditor", u"DNA-profiler:", None))
        self.dna_matches_label.setText(QCoreApplication.translate("PersonEditor", u"DNA-matchningar:", None))
        self.dna_clusters_label.setText(QCoreApplication.translate("PersonEditor", u"Klustermedlemskap:", None))
        self.tab_widget.setTabText(self.tab_widget.indexOf(self.dna_tab), QCoreApplication.translate("PersonEditor", u"DNA & Kluster", None))
        self.status_label.setText("")
        self.status_label.setStyleSheet(QCoreApplication.translate("PersonEditor", u"color: red;", None))
        self.save_button.setText(QCoreApplication.translate("PersonEditor", u"Spara", None))
        self.cancel_button.setText(QCoreApplication.translate("PersonEditor", u"Avbryt", None))
    # retranslateUi

