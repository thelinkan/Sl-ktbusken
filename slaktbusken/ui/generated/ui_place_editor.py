# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'place_editor.ui'
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
    QSizePolicy, QSpacerItem, QSplitter, QVBoxLayout,
    QWidget)

class Ui_PlaceEditor(object):
    def setupUi(self, PlaceEditor):
        if not PlaceEditor.objectName():
            PlaceEditor.setObjectName(u"PlaceEditor")
        PlaceEditor.resize(900, 850)
        self.main_layout = QHBoxLayout(PlaceEditor)
        self.main_layout.setObjectName(u"main_layout")
        self.splitter = QSplitter(PlaceEditor)
        self.splitter.setObjectName(u"splitter")
        self.splitter.setOrientation(Qt.Horizontal)
        self.left_panel = QWidget(self.splitter)
        self.left_panel.setObjectName(u"left_panel")
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_layout.setObjectName(u"left_layout")
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.filter_label = QLabel(self.left_panel)
        self.filter_label.setObjectName(u"filter_label")

        self.left_layout.addWidget(self.filter_label)

        self.filter_input = QLineEdit(self.left_panel)
        self.filter_input.setObjectName(u"filter_input")

        self.left_layout.addWidget(self.filter_input)

        self.place_list = QListWidget(self.left_panel)
        self.place_list.setObjectName(u"place_list")

        self.left_layout.addWidget(self.place_list)

        self.list_buttons_layout = QHBoxLayout()
        self.list_buttons_layout.setObjectName(u"list_buttons_layout")
        self.add_button = QPushButton(self.left_panel)
        self.add_button.setObjectName(u"add_button")

        self.list_buttons_layout.addWidget(self.add_button)

        self.delete_button = QPushButton(self.left_panel)
        self.delete_button.setObjectName(u"delete_button")

        self.list_buttons_layout.addWidget(self.delete_button)

        self.list_buttons_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.list_buttons_layout.addItem(self.list_buttons_spacer)


        self.left_layout.addLayout(self.list_buttons_layout)

        self.splitter.addWidget(self.left_panel)
        self.right_panel = QWidget(self.splitter)
        self.right_panel.setObjectName(u"right_panel")
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setObjectName(u"right_layout")
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout = QFormLayout()
        self.form_layout.setObjectName(u"form_layout")
        self.type_label = QLabel(self.right_panel)
        self.type_label.setObjectName(u"type_label")

        self.form_layout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.type_label)

        self.type_combo = QComboBox(self.right_panel)
        self.type_combo.addItem("")
        self.type_combo.addItem("")
        self.type_combo.addItem("")
        self.type_combo.addItem("")
        self.type_combo.addItem("")
        self.type_combo.setObjectName(u"type_combo")

        self.form_layout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.type_combo)

        self.name_label = QLabel(self.right_panel)
        self.name_label.setObjectName(u"name_label")

        self.form_layout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.name_label)

        self.name_input = QLineEdit(self.right_panel)
        self.name_input.setObjectName(u"name_input")
        self.name_input.setMaxLength(200)

        self.form_layout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.name_input)

        self.parent_label = QLabel(self.right_panel)
        self.parent_label.setObjectName(u"parent_label")

        self.form_layout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.parent_label)

        self.parent_combo = QComboBox(self.right_panel)
        self.parent_combo.setObjectName(u"parent_combo")

        self.form_layout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.parent_combo)

        self.coordinates_check = QCheckBox(self.right_panel)
        self.coordinates_check.setObjectName(u"coordinates_check")

        self.form_layout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.coordinates_check)

        self.latitude_label = QLabel(self.right_panel)
        self.latitude_label.setObjectName(u"latitude_label")

        self.form_layout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.latitude_label)

        self.latitude_spin = QDoubleSpinBox(self.right_panel)
        self.latitude_spin.setObjectName(u"latitude_spin")
        self.latitude_spin.setEnabled(False)
        self.latitude_spin.setMinimum(-90.000000000000000)
        self.latitude_spin.setMaximum(90.000000000000000)
        self.latitude_spin.setDecimals(6)

        self.form_layout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.latitude_spin)

        self.longitude_label = QLabel(self.right_panel)
        self.longitude_label.setObjectName(u"longitude_label")

        self.form_layout.setWidget(5, QFormLayout.ItemRole.LabelRole, self.longitude_label)

        self.longitude_spin = QDoubleSpinBox(self.right_panel)
        self.longitude_spin.setObjectName(u"longitude_spin")
        self.longitude_spin.setEnabled(False)
        self.longitude_spin.setMinimum(-180.000000000000000)
        self.longitude_spin.setMaximum(180.000000000000000)
        self.longitude_spin.setDecimals(6)

        self.form_layout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.longitude_spin)

        self.notes_label = QLabel(self.right_panel)
        self.notes_label.setObjectName(u"notes_label")

        self.form_layout.setWidget(6, QFormLayout.ItemRole.LabelRole, self.notes_label)

        self.notes_input = QPlainTextEdit(self.right_panel)
        self.notes_input.setObjectName(u"notes_input")
        self.notes_input.setMaximumSize(QSize(16777215, 200))

        self.form_layout.setWidget(6, QFormLayout.ItemRole.FieldRole, self.notes_input)


        self.right_layout.addLayout(self.form_layout)

        self.status_label = QLabel(self.right_panel)
        self.status_label.setObjectName(u"status_label")

        self.right_layout.addWidget(self.status_label)

        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.setObjectName(u"buttons_layout")
        self.buttons_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.buttons_layout.addItem(self.buttons_spacer)

        self.save_button = QPushButton(self.right_panel)
        self.save_button.setObjectName(u"save_button")

        self.buttons_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton(self.right_panel)
        self.cancel_button.setObjectName(u"cancel_button")

        self.buttons_layout.addWidget(self.cancel_button)


        self.right_layout.addLayout(self.buttons_layout)

        self.splitter.addWidget(self.right_panel)

        self.main_layout.addWidget(self.splitter)


        self.retranslateUi(PlaceEditor)

        QMetaObject.connectSlotsByName(PlaceEditor)
    # setupUi

    def retranslateUi(self, PlaceEditor):
        PlaceEditor.setWindowTitle(QCoreApplication.translate("PlaceEditor", u"Platsredigerare", None))
        self.filter_label.setText(QCoreApplication.translate("PlaceEditor", u"Filtrera:", None))
        self.filter_input.setPlaceholderText(QCoreApplication.translate("PlaceEditor", u"S\u00f6k plats...", None))
        self.add_button.setText(QCoreApplication.translate("PlaceEditor", u"L\u00e4gg till", None))
        self.delete_button.setText(QCoreApplication.translate("PlaceEditor", u"Ta bort", None))
        self.type_label.setText(QCoreApplication.translate("PlaceEditor", u"Typ:", None))
        self.type_combo.setItemText(0, QCoreApplication.translate("PlaceEditor", u"Land", None))
        self.type_combo.setItemText(1, QCoreApplication.translate("PlaceEditor", u"L\u00e4n", None))
        self.type_combo.setItemText(2, QCoreApplication.translate("PlaceEditor", u"Socken", None))
        self.type_combo.setItemText(3, QCoreApplication.translate("PlaceEditor", u"Kyrka", None))
        self.type_combo.setItemText(4, QCoreApplication.translate("PlaceEditor", u"Kyrkog\u00e5rd", None))

        self.name_label.setText(QCoreApplication.translate("PlaceEditor", u"Namn:", None))
        self.name_input.setPlaceholderText(QCoreApplication.translate("PlaceEditor", u"Platsnamn (1\u2013200 tecken)", None))
        self.parent_label.setText(QCoreApplication.translate("PlaceEditor", u"\u00d6verordnad plats:", None))
        self.coordinates_check.setText(QCoreApplication.translate("PlaceEditor", u"Ange koordinater", None))
        self.latitude_label.setText(QCoreApplication.translate("PlaceEditor", u"Latitud:", None))
        self.longitude_label.setText(QCoreApplication.translate("PlaceEditor", u"Longitud:", None))
        self.notes_label.setText(QCoreApplication.translate("PlaceEditor", u"Anteckningar:", None))
        self.status_label.setText("")
        self.status_label.setStyleSheet(QCoreApplication.translate("PlaceEditor", u"color: red;", None))
        self.save_button.setText(QCoreApplication.translate("PlaceEditor", u"Spara", None))
        self.cancel_button.setText(QCoreApplication.translate("PlaceEditor", u"Avbryt", None))
    # retranslateUi

