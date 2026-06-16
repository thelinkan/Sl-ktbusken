# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'source_translation_editor.ui'
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

class Ui_SourceTranslationEditor(object):
    def setupUi(self, SourceTranslationEditor):
        if not SourceTranslationEditor.objectName():
            SourceTranslationEditor.setObjectName(u"SourceTranslationEditor")
        SourceTranslationEditor.resize(700, 500)
        self.main_layout = QVBoxLayout(SourceTranslationEditor)
        self.main_layout.setObjectName(u"main_layout")
        self.search_input = QLineEdit(SourceTranslationEditor)
        self.search_input.setObjectName(u"search_input")

        self.main_layout.addWidget(self.search_input)

        self.mapping_table = QTableWidget(SourceTranslationEditor)
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

        self.edit_group = QGroupBox(SourceTranslationEditor)
        self.edit_group.setObjectName(u"edit_group")
        self.edit_form_layout = QFormLayout(self.edit_group)
        self.edit_form_layout.setObjectName(u"edit_form_layout")
        self.gedcom_id_label = QLabel(self.edit_group)
        self.gedcom_id_label.setObjectName(u"gedcom_id_label")

        self.edit_form_layout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.gedcom_id_label)

        self.gedcom_id_input = QLineEdit(self.edit_group)
        self.gedcom_id_input.setObjectName(u"gedcom_id_input")

        self.edit_form_layout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.gedcom_id_input)

        self.app_source_label = QLabel(self.edit_group)
        self.app_source_label.setObjectName(u"app_source_label")

        self.edit_form_layout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.app_source_label)

        self.app_source_combo = QComboBox(self.edit_group)
        self.app_source_combo.setObjectName(u"app_source_combo")
        self.app_source_combo.setEditable(False)

        self.edit_form_layout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.app_source_combo)

        self.validation_label = QLabel(self.edit_group)
        self.validation_label.setObjectName(u"validation_label")

        self.edit_form_layout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.validation_label)

        self.validation_indicator = QLabel(self.edit_group)
        self.validation_indicator.setObjectName(u"validation_indicator")

        self.edit_form_layout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.validation_indicator)


        self.main_layout.addWidget(self.edit_group)

        self.button_layout = QHBoxLayout()
        self.button_layout.setObjectName(u"button_layout")
        self.add_button = QPushButton(SourceTranslationEditor)
        self.add_button.setObjectName(u"add_button")

        self.button_layout.addWidget(self.add_button)

        self.edit_button = QPushButton(SourceTranslationEditor)
        self.edit_button.setObjectName(u"edit_button")

        self.button_layout.addWidget(self.edit_button)

        self.remove_button = QPushButton(SourceTranslationEditor)
        self.remove_button.setObjectName(u"remove_button")

        self.button_layout.addWidget(self.remove_button)

        self.button_spacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.button_layout.addItem(self.button_spacer)

        self.save_button = QPushButton(SourceTranslationEditor)
        self.save_button.setObjectName(u"save_button")

        self.button_layout.addWidget(self.save_button)


        self.main_layout.addLayout(self.button_layout)

        self.status_label = QLabel(SourceTranslationEditor)
        self.status_label.setObjectName(u"status_label")

        self.main_layout.addWidget(self.status_label)


        self.retranslateUi(SourceTranslationEditor)

        QMetaObject.connectSlotsByName(SourceTranslationEditor)
    # setupUi

    def retranslateUi(self, SourceTranslationEditor):
        SourceTranslationEditor.setWindowTitle(QCoreApplication.translate("SourceTranslationEditor", u"K\u00e4ll\u00f6vers\u00e4ttningsredigerare", None))
        self.search_input.setPlaceholderText(QCoreApplication.translate("SourceTranslationEditor", u"S\u00f6k...", None))
        ___qtablewidgetitem = self.mapping_table.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("SourceTranslationEditor", u"GEDCOM-ID", None))
        ___qtablewidgetitem1 = self.mapping_table.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("SourceTranslationEditor", u"App_JSON K\u00e4lla", None))
        self.edit_group.setTitle(QCoreApplication.translate("SourceTranslationEditor", u"Redigera mappning", None))
        self.gedcom_id_label.setText(QCoreApplication.translate("SourceTranslationEditor", u"GEDCOM-ID:", None))
        self.gedcom_id_input.setPlaceholderText(QCoreApplication.translate("SourceTranslationEditor", u"T.ex. @S1@", None))
        self.app_source_label.setText(QCoreApplication.translate("SourceTranslationEditor", u"App_JSON-k\u00e4lla:", None))
        self.validation_label.setText("")
        self.validation_indicator.setText("")
        self.add_button.setText(QCoreApplication.translate("SourceTranslationEditor", u"L\u00e4gg till", None))
        self.edit_button.setText(QCoreApplication.translate("SourceTranslationEditor", u"Redigera", None))
        self.remove_button.setText(QCoreApplication.translate("SourceTranslationEditor", u"Ta bort", None))
        self.save_button.setText(QCoreApplication.translate("SourceTranslationEditor", u"Spara", None))
        self.status_label.setText("")
    # retranslateUi

