# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'place_translation_editor.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QSpacerItem,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)


class Ui_PlaceTranslationEditor(object):
    def setupUi(self, PlaceTranslationEditor):
        if not PlaceTranslationEditor.objectName():
            PlaceTranslationEditor.setObjectName(u"PlaceTranslationEditor")
        PlaceTranslationEditor.resize(750, 550)
        self.main_layout = QVBoxLayout(PlaceTranslationEditor)
        self.main_layout.setObjectName(u"main_layout")
        self.search_input = QLineEdit(PlaceTranslationEditor)
        self.search_input.setObjectName(u"search_input")

        self.main_layout.addWidget(self.search_input)

        self.mapping_table = QTableWidget(PlaceTranslationEditor)
        if (self.mapping_table.columnCount() < 2):
            self.mapping_table.setColumnCount(2)
        __qtablewidgetitem = QTableWidgetItem()
        self.mapping_table.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.mapping_table.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        self.mapping_table.setObjectName(u"mapping_table")
        self.mapping_table.setColumnCount(2)
        self.mapping_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.mapping_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.main_layout.addWidget(self.mapping_table)

        self.edit_group = QGroupBox(PlaceTranslationEditor)
        self.edit_group.setObjectName(u"edit_group")
        self.edit_form_layout = QFormLayout(self.edit_group)
        self.edit_form_layout.setObjectName(u"edit_form_layout")
        self.gedcom_place_label = QLabel(self.edit_group)
        self.gedcom_place_label.setObjectName(u"gedcom_place_label")

        self.edit_form_layout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.gedcom_place_label)

        self.gedcom_place_input = QLineEdit(self.edit_group)
        self.gedcom_place_input.setObjectName(u"gedcom_place_input")

        self.edit_form_layout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.gedcom_place_input)

        self.app_place_label = QLabel(self.edit_group)
        self.app_place_label.setObjectName(u"app_place_label")

        self.edit_form_layout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.app_place_label)

        self.app_place_combo = QComboBox(self.edit_group)
        self.app_place_combo.setObjectName(u"app_place_combo")
        self.app_place_combo.setEditable(False)

        self.edit_form_layout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.app_place_combo)

        self.hierarchy_title_label = QLabel(self.edit_group)
        self.hierarchy_title_label.setObjectName(u"hierarchy_title_label")

        self.edit_form_layout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.hierarchy_title_label)

        self.hierarchy_label = QLabel(self.edit_group)
        self.hierarchy_label.setObjectName(u"hierarchy_label")

        self.edit_form_layout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.hierarchy_label)

        self.validation_label = QLabel(self.edit_group)
        self.validation_label.setObjectName(u"validation_label")

        self.edit_form_layout.setWidget(3, QFormLayout.ItemRole.LabelRole, self.validation_label)

        self.validation_indicator = QLabel(self.edit_group)
        self.validation_indicator.setObjectName(u"validation_indicator")

        self.edit_form_layout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.validation_indicator)


        self.main_layout.addWidget(self.edit_group)

        self.button_layout = QHBoxLayout()
        self.button_layout.setObjectName(u"button_layout")
        self.add_button = QPushButton(PlaceTranslationEditor)
        self.add_button.setObjectName(u"add_button")

        self.button_layout.addWidget(self.add_button)

        self.edit_button = QPushButton(PlaceTranslationEditor)
        self.edit_button.setObjectName(u"edit_button")

        self.button_layout.addWidget(self.edit_button)

        self.remove_button = QPushButton(PlaceTranslationEditor)
        self.remove_button.setObjectName(u"remove_button")

        self.button_layout.addWidget(self.remove_button)

        self.button_spacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.button_layout.addItem(self.button_spacer)

        self.save_button = QPushButton(PlaceTranslationEditor)
        self.save_button.setObjectName(u"save_button")

        self.button_layout.addWidget(self.save_button)


        self.main_layout.addLayout(self.button_layout)

        self.status_label = QLabel(PlaceTranslationEditor)
        self.status_label.setObjectName(u"status_label")

        self.main_layout.addWidget(self.status_label)


        self.retranslateUi(PlaceTranslationEditor)

        QMetaObject.connectSlotsByName(PlaceTranslationEditor)
    # setupUi

    def retranslateUi(self, PlaceTranslationEditor):
        PlaceTranslationEditor.setWindowTitle(QCoreApplication.translate("PlaceTranslationEditor", u"Plats\u00f6vers\u00e4ttningsredigerare", None))
        self.search_input.setPlaceholderText(QCoreApplication.translate("PlaceTranslationEditor", u"S\u00f6k...", None))
        ___qtablewidgetitem = self.mapping_table.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("PlaceTranslationEditor", u"GEDCOM-platss\u0074r\u00e4ng", None))
        ___qtablewidgetitem1 = self.mapping_table.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("PlaceTranslationEditor", u"App_JSON Plats", None))
        self.edit_group.setTitle(QCoreApplication.translate("PlaceTranslationEditor", u"Redigera mappning", None))
        self.gedcom_place_label.setText(QCoreApplication.translate("PlaceTranslationEditor", u"GEDCOM-platss\u0074r\u00e4ng:", None))
        self.gedcom_place_input.setPlaceholderText(QCoreApplication.translate("PlaceTranslationEditor", u"T.ex. Ljusdal, G\u00e4vleborgs l\u00e4n, Sverige", None))
        self.app_place_label.setText(QCoreApplication.translate("PlaceTranslationEditor", u"App_JSON-plats:", None))
        self.hierarchy_title_label.setText(QCoreApplication.translate("PlaceTranslationEditor", u"Hierarki:", None))
        self.hierarchy_label.setText("")
        self.validation_label.setText("")
        self.validation_indicator.setText("")
        self.add_button.setText(QCoreApplication.translate("PlaceTranslationEditor", u"L\u00e4gg till", None))
        self.edit_button.setText(QCoreApplication.translate("PlaceTranslationEditor", u"Redigera", None))
        self.remove_button.setText(QCoreApplication.translate("PlaceTranslationEditor", u"Ta bort", None))
        self.save_button.setText(QCoreApplication.translate("PlaceTranslationEditor", u"Spara", None))
        self.status_label.setText("")
    # retranslateUi
