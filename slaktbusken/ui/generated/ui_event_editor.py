# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'event_editor.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QSizePolicy,
    QSpacerItem, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget)

class Ui_EventEditor(object):
    def setupUi(self, EventEditor):
        if not EventEditor.objectName():
            EventEditor.setObjectName(u"EventEditor")
        EventEditor.resize(750, 650)
        self.main_layout = QVBoxLayout(EventEditor)
        self.main_layout.setObjectName(u"main_layout")
        self.type_group = QGroupBox(EventEditor)
        self.type_group.setObjectName(u"type_group")
        self.type_group_layout = QVBoxLayout(self.type_group)
        self.type_group_layout.setObjectName(u"type_group_layout")
        self.type_layout = QHBoxLayout()
        self.type_layout.setObjectName(u"type_layout")
        self.type_label = QLabel(self.type_group)
        self.type_label.setObjectName(u"type_label")

        self.type_layout.addWidget(self.type_label)

        self.type_combo = QComboBox(self.type_group)
        self.type_combo.setObjectName(u"type_combo")

        self.type_layout.addWidget(self.type_combo)


        self.type_group_layout.addLayout(self.type_layout)

        self.custom_type_layout = QHBoxLayout()
        self.custom_type_layout.setObjectName(u"custom_type_layout")
        self.custom_type_label = QLabel(self.type_group)
        self.custom_type_label.setObjectName(u"custom_type_label")

        self.custom_type_layout.addWidget(self.custom_type_label)

        self.custom_type_input = QLineEdit(self.type_group)
        self.custom_type_input.setObjectName(u"custom_type_input")
        self.custom_type_input.setMaxLength(200)

        self.custom_type_layout.addWidget(self.custom_type_input)


        self.type_group_layout.addLayout(self.custom_type_layout)

        self.cause_of_death_layout = QHBoxLayout()
        self.cause_of_death_layout.setObjectName(u"cause_of_death_layout")
        self.cause_of_death_label = QLabel(self.type_group)
        self.cause_of_death_label.setObjectName(u"cause_of_death_label")

        self.cause_of_death_layout.addWidget(self.cause_of_death_label)

        self.cause_of_death_input = QLineEdit(self.type_group)
        self.cause_of_death_input.setObjectName(u"cause_of_death_input")
        self.cause_of_death_input.setMaxLength(500)

        self.cause_of_death_layout.addWidget(self.cause_of_death_input)


        self.type_group_layout.addLayout(self.cause_of_death_layout)


        self.main_layout.addWidget(self.type_group)

        self.participants_group = QGroupBox(EventEditor)
        self.participants_group.setObjectName(u"participants_group")
        self.participants_group_layout = QVBoxLayout(self.participants_group)
        self.participants_group_layout.setObjectName(u"participants_group_layout")
        self.participants_table = QTableWidget(self.participants_group)
        if (self.participants_table.columnCount() < 2):
            self.participants_table.setColumnCount(2)
        __qtablewidgetitem = QTableWidgetItem()
        self.participants_table.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.participants_table.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        self.participants_table.setObjectName(u"participants_table")
        self.participants_table.setColumnCount(2)
        self.participants_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.participants_table.setSelectionMode(QAbstractItemView.SingleSelection)

        self.participants_group_layout.addWidget(self.participants_table)

        self.participant_edit_layout = QHBoxLayout()
        self.participant_edit_layout.setObjectName(u"participant_edit_layout")
        self.participant_person_label = QLabel(self.participants_group)
        self.participant_person_label.setObjectName(u"participant_person_label")

        self.participant_edit_layout.addWidget(self.participant_person_label)

        self.participant_person_combo = QComboBox(self.participants_group)
        self.participant_person_combo.setObjectName(u"participant_person_combo")

        self.participant_edit_layout.addWidget(self.participant_person_combo)

        self.participant_role_label = QLabel(self.participants_group)
        self.participant_role_label.setObjectName(u"participant_role_label")

        self.participant_edit_layout.addWidget(self.participant_role_label)

        self.participant_role_input = QLineEdit(self.participants_group)
        self.participant_role_input.setObjectName(u"participant_role_input")
        self.participant_role_input.setMaxLength(100)

        self.participant_edit_layout.addWidget(self.participant_role_input)


        self.participants_group_layout.addLayout(self.participant_edit_layout)

        self.participants_buttons_layout = QHBoxLayout()
        self.participants_buttons_layout.setObjectName(u"participants_buttons_layout")
        self.add_participant_button = QPushButton(self.participants_group)
        self.add_participant_button.setObjectName(u"add_participant_button")

        self.participants_buttons_layout.addWidget(self.add_participant_button)

        self.remove_participant_button = QPushButton(self.participants_group)
        self.remove_participant_button.setObjectName(u"remove_participant_button")

        self.participants_buttons_layout.addWidget(self.remove_participant_button)

        self.participants_buttons_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.participants_buttons_layout.addItem(self.participants_buttons_spacer)


        self.participants_group_layout.addLayout(self.participants_buttons_layout)


        self.main_layout.addWidget(self.participants_group)

        self.date_group = QGroupBox(EventEditor)
        self.date_group.setObjectName(u"date_group")
        self.date_group_layout = QHBoxLayout(self.date_group)
        self.date_group_layout.setObjectName(u"date_group_layout")
        self.date_value_label = QLabel(self.date_group)
        self.date_value_label.setObjectName(u"date_value_label")

        self.date_group_layout.addWidget(self.date_value_label)

        self.date_value_input = QLineEdit(self.date_group)
        self.date_value_input.setObjectName(u"date_value_input")
        self.date_value_input.setMaxLength(10)

        self.date_group_layout.addWidget(self.date_value_input)

        self.date_precision_label = QLabel(self.date_group)
        self.date_precision_label.setObjectName(u"date_precision_label")

        self.date_group_layout.addWidget(self.date_precision_label)

        self.date_precision_combo = QComboBox(self.date_group)
        self.date_precision_combo.addItem("")
        self.date_precision_combo.addItem("")
        self.date_precision_combo.addItem("")
        self.date_precision_combo.addItem("")
        self.date_precision_combo.setObjectName(u"date_precision_combo")

        self.date_group_layout.addWidget(self.date_precision_combo)


        self.main_layout.addWidget(self.date_group)

        self.place_group = QGroupBox(EventEditor)
        self.place_group.setObjectName(u"place_group")
        self.place_group_layout = QHBoxLayout(self.place_group)
        self.place_group_layout.setObjectName(u"place_group_layout")
        self.place_label = QLabel(self.place_group)
        self.place_label.setObjectName(u"place_label")

        self.place_group_layout.addWidget(self.place_label)

        self.place_combo = QComboBox(self.place_group)
        self.place_combo.setObjectName(u"place_combo")

        self.place_group_layout.addWidget(self.place_combo)


        self.main_layout.addWidget(self.place_group)

        self.sources_group = QGroupBox(EventEditor)
        self.sources_group.setObjectName(u"sources_group")
        self.sources_group_layout = QVBoxLayout(self.sources_group)
        self.sources_group_layout.setObjectName(u"sources_group_layout")
        self.sources_table = QTableWidget(self.sources_group)
        if (self.sources_table.columnCount() < 3):
            self.sources_table.setColumnCount(3)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.sources_table.setHorizontalHeaderItem(0, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.sources_table.setHorizontalHeaderItem(1, __qtablewidgetitem3)
        __qtablewidgetitem4 = QTableWidgetItem()
        self.sources_table.setHorizontalHeaderItem(2, __qtablewidgetitem4)
        self.sources_table.setObjectName(u"sources_table")
        self.sources_table.setColumnCount(3)
        self.sources_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.sources_table.setSelectionMode(QAbstractItemView.SingleSelection)

        self.sources_group_layout.addWidget(self.sources_table)

        self.source_edit_layout = QHBoxLayout()
        self.source_edit_layout.setObjectName(u"source_edit_layout")
        self.source_select_label = QLabel(self.sources_group)
        self.source_select_label.setObjectName(u"source_select_label")

        self.source_edit_layout.addWidget(self.source_select_label)

        self.source_combo = QComboBox(self.sources_group)
        self.source_combo.setObjectName(u"source_combo")

        self.source_edit_layout.addWidget(self.source_combo)

        self.source_quality_label = QLabel(self.sources_group)
        self.source_quality_label.setObjectName(u"source_quality_label")

        self.source_edit_layout.addWidget(self.source_quality_label)

        self.source_quality_combo = QComboBox(self.sources_group)
        self.source_quality_combo.addItem("")
        self.source_quality_combo.addItem("")
        self.source_quality_combo.addItem("")
        self.source_quality_combo.setObjectName(u"source_quality_combo")

        self.source_edit_layout.addWidget(self.source_quality_combo)


        self.sources_group_layout.addLayout(self.source_edit_layout)

        self.source_note_layout = QHBoxLayout()
        self.source_note_layout.setObjectName(u"source_note_layout")
        self.source_note_label = QLabel(self.sources_group)
        self.source_note_label.setObjectName(u"source_note_label")

        self.source_note_layout.addWidget(self.source_note_label)

        self.source_note_input = QLineEdit(self.sources_group)
        self.source_note_input.setObjectName(u"source_note_input")
        self.source_note_input.setMaxLength(500)

        self.source_note_layout.addWidget(self.source_note_input)


        self.sources_group_layout.addLayout(self.source_note_layout)

        self.sources_buttons_layout = QHBoxLayout()
        self.sources_buttons_layout.setObjectName(u"sources_buttons_layout")
        self.add_source_button = QPushButton(self.sources_group)
        self.add_source_button.setObjectName(u"add_source_button")

        self.sources_buttons_layout.addWidget(self.add_source_button)

        self.remove_source_button = QPushButton(self.sources_group)
        self.remove_source_button.setObjectName(u"remove_source_button")

        self.sources_buttons_layout.addWidget(self.remove_source_button)

        self.sources_buttons_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.sources_buttons_layout.addItem(self.sources_buttons_spacer)


        self.sources_group_layout.addLayout(self.sources_buttons_layout)


        self.main_layout.addWidget(self.sources_group)

        self.media_group = QGroupBox(EventEditor)
        self.media_group.setObjectName(u"media_group")
        self.media_group_layout = QVBoxLayout(self.media_group)
        self.media_group_layout.setObjectName(u"media_group_layout")
        self.media_list = QListWidget(self.media_group)
        self.media_list.setObjectName(u"media_list")

        self.media_group_layout.addWidget(self.media_list)

        self.media_edit_layout = QHBoxLayout()
        self.media_edit_layout.setObjectName(u"media_edit_layout")
        self.media_select_label = QLabel(self.media_group)
        self.media_select_label.setObjectName(u"media_select_label")

        self.media_edit_layout.addWidget(self.media_select_label)

        self.media_combo = QComboBox(self.media_group)
        self.media_combo.setObjectName(u"media_combo")

        self.media_edit_layout.addWidget(self.media_combo)


        self.media_group_layout.addLayout(self.media_edit_layout)

        self.media_buttons_layout = QHBoxLayout()
        self.media_buttons_layout.setObjectName(u"media_buttons_layout")
        self.add_media_button = QPushButton(self.media_group)
        self.add_media_button.setObjectName(u"add_media_button")

        self.media_buttons_layout.addWidget(self.add_media_button)

        self.remove_media_button = QPushButton(self.media_group)
        self.remove_media_button.setObjectName(u"remove_media_button")

        self.media_buttons_layout.addWidget(self.remove_media_button)

        self.media_buttons_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.media_buttons_layout.addItem(self.media_buttons_spacer)


        self.media_group_layout.addLayout(self.media_buttons_layout)


        self.main_layout.addWidget(self.media_group)

        self.status_label = QLabel(EventEditor)
        self.status_label.setObjectName(u"status_label")

        self.main_layout.addWidget(self.status_label)

        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.setObjectName(u"buttons_layout")
        self.buttons_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.buttons_layout.addItem(self.buttons_spacer)

        self.save_button = QPushButton(EventEditor)
        self.save_button.setObjectName(u"save_button")

        self.buttons_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton(EventEditor)
        self.cancel_button.setObjectName(u"cancel_button")

        self.buttons_layout.addWidget(self.cancel_button)


        self.main_layout.addLayout(self.buttons_layout)


        self.retranslateUi(EventEditor)

        QMetaObject.connectSlotsByName(EventEditor)
    # setupUi

    def retranslateUi(self, EventEditor):
        EventEditor.setWindowTitle(QCoreApplication.translate("EventEditor", u"H\u00e4ndelseredigerare", None))
        self.type_group.setTitle(QCoreApplication.translate("EventEditor", u"H\u00e4ndelsetyp", None))
        self.type_label.setText(QCoreApplication.translate("EventEditor", u"Typ:", None))
        self.custom_type_label.setText(QCoreApplication.translate("EventEditor", u"Eget typnamn:", None))
        self.custom_type_input.setPlaceholderText(QCoreApplication.translate("EventEditor", u"Ange namn f\u00f6r egen h\u00e4ndelsetyp", None))
        self.cause_of_death_label.setText(QCoreApplication.translate("EventEditor", u"D\u00f6dsorsak:", None))
        self.cause_of_death_input.setPlaceholderText(QCoreApplication.translate("EventEditor", u"Ange d\u00f6dsorsak", None))
        self.participants_group.setTitle(QCoreApplication.translate("EventEditor", u"Deltagare", None))
        ___qtablewidgetitem = self.participants_table.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("EventEditor", u"Person", None))
        ___qtablewidgetitem1 = self.participants_table.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("EventEditor", u"Roll", None))
        self.participant_person_label.setText(QCoreApplication.translate("EventEditor", u"Person:", None))
        self.participant_role_label.setText(QCoreApplication.translate("EventEditor", u"Roll:", None))
        self.participant_role_input.setPlaceholderText(QCoreApplication.translate("EventEditor", u"t.ex. huvudperson, vittne", None))
        self.add_participant_button.setText(QCoreApplication.translate("EventEditor", u"L\u00e4gg till deltagare", None))
        self.remove_participant_button.setText(QCoreApplication.translate("EventEditor", u"Ta bort deltagare", None))
        self.date_group.setTitle(QCoreApplication.translate("EventEditor", u"Datum", None))
        self.date_value_label.setText(QCoreApplication.translate("EventEditor", u"Datum:", None))
        self.date_value_input.setPlaceholderText(QCoreApplication.translate("EventEditor", u"\u00c5\u00c5\u00c5\u00c5-MM-DD, \u00c5\u00c5\u00c5\u00c5-MM, eller \u00c5\u00c5\u00c5\u00c5", None))
        self.date_precision_label.setText(QCoreApplication.translate("EventEditor", u"Precision:", None))
        self.date_precision_combo.setItemText(0, QCoreApplication.translate("EventEditor", u"day", None))
        self.date_precision_combo.setItemText(1, QCoreApplication.translate("EventEditor", u"month", None))
        self.date_precision_combo.setItemText(2, QCoreApplication.translate("EventEditor", u"year", None))
        self.date_precision_combo.setItemText(3, QCoreApplication.translate("EventEditor", u"approximate", None))

        self.place_group.setTitle(QCoreApplication.translate("EventEditor", u"Plats", None))
        self.place_label.setText(QCoreApplication.translate("EventEditor", u"Plats:", None))
        self.sources_group.setTitle(QCoreApplication.translate("EventEditor", u"K\u00e4llh\u00e4nvisningar", None))
        ___qtablewidgetitem2 = self.sources_table.horizontalHeaderItem(0)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("EventEditor", u"K\u00e4lla", None))
        ___qtablewidgetitem3 = self.sources_table.horizontalHeaderItem(1)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("EventEditor", u"Kvalitet", None))
        ___qtablewidgetitem4 = self.sources_table.horizontalHeaderItem(2)
        ___qtablewidgetitem4.setText(QCoreApplication.translate("EventEditor", u"Anteckning", None))
        self.source_select_label.setText(QCoreApplication.translate("EventEditor", u"K\u00e4lla:", None))
        self.source_quality_label.setText(QCoreApplication.translate("EventEditor", u"Kvalitet:", None))
        self.source_quality_combo.setItemText(0, QCoreApplication.translate("EventEditor", u"primary", None))
        self.source_quality_combo.setItemText(1, QCoreApplication.translate("EventEditor", u"secondary", None))
        self.source_quality_combo.setItemText(2, QCoreApplication.translate("EventEditor", u"tertiary", None))

        self.source_note_label.setText(QCoreApplication.translate("EventEditor", u"Anteckning:", None))
        self.source_note_input.setPlaceholderText(QCoreApplication.translate("EventEditor", u"Valfri anteckning om k\u00e4llan", None))
        self.add_source_button.setText(QCoreApplication.translate("EventEditor", u"L\u00e4gg till k\u00e4lla", None))
        self.remove_source_button.setText(QCoreApplication.translate("EventEditor", u"Ta bort k\u00e4lla", None))
        self.media_group.setTitle(QCoreApplication.translate("EventEditor", u"Media", None))
        self.media_select_label.setText(QCoreApplication.translate("EventEditor", u"Media:", None))
        self.add_media_button.setText(QCoreApplication.translate("EventEditor", u"L\u00e4gg till media", None))
        self.remove_media_button.setText(QCoreApplication.translate("EventEditor", u"Ta bort media", None))
        self.status_label.setText("")
        self.status_label.setStyleSheet(QCoreApplication.translate("EventEditor", u"color: red;", None))
        self.save_button.setText(QCoreApplication.translate("EventEditor", u"Spara", None))
        self.cancel_button.setText(QCoreApplication.translate("EventEditor", u"Avbryt", None))
    # retranslateUi

