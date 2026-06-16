# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'repository_editor.ui'
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
from PySide6.QtWidgets import (QApplication, QComboBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QPushButton, QSizePolicy, QSplitter,
    QTextEdit, QVBoxLayout, QWidget)


class Ui_RepositoryEditor(object):
    def setupUi(self, RepositoryEditor):
        if not RepositoryEditor.objectName():
            RepositoryEditor.setObjectName(u"RepositoryEditor")
        RepositoryEditor.resize(900, 600)

        # Main horizontal layout with splitter
        self.main_layout = QHBoxLayout(RepositoryEditor)
        self.main_layout.setObjectName(u"main_layout")

        self.splitter = QSplitter(RepositoryEditor)
        self.splitter.setObjectName(u"splitter")
        self.splitter.setOrientation(Qt.Orientation.Horizontal)

        # ---- Left panel: repository list ----
        self.left_panel = QWidget()
        self.left_panel.setObjectName(u"left_panel")
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_layout.setObjectName(u"left_layout")

        self.filter_input = QLineEdit(self.left_panel)
        self.filter_input.setObjectName(u"filter_input")
        self.filter_input.setPlaceholderText("")
        self.left_layout.addWidget(self.filter_input)

        self.repository_list = QListWidget(self.left_panel)
        self.repository_list.setObjectName(u"repository_list")
        self.left_layout.addWidget(self.repository_list)

        self.left_buttons_layout = QHBoxLayout()
        self.left_buttons_layout.setObjectName(u"left_buttons_layout")

        self.add_repository_button = QPushButton(self.left_panel)
        self.add_repository_button.setObjectName(u"add_repository_button")
        self.left_buttons_layout.addWidget(self.add_repository_button)

        self.delete_repository_button = QPushButton(self.left_panel)
        self.delete_repository_button.setObjectName(u"delete_repository_button")
        self.left_buttons_layout.addWidget(self.delete_repository_button)

        self.left_layout.addLayout(self.left_buttons_layout)

        self.splitter.addWidget(self.left_panel)

        # ---- Right panel: edit form ----
        self.right_panel = QWidget()
        self.right_panel.setObjectName(u"right_panel")
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setObjectName(u"right_layout")

        self.form_layout = QFormLayout()
        self.form_layout.setObjectName(u"form_layout")

        # Name
        self.name_label = QLabel(self.right_panel)
        self.name_label.setObjectName(u"name_label")
        self.name_input = QLineEdit(self.right_panel)
        self.name_input.setObjectName(u"name_input")
        self.form_layout.addRow(self.name_label, self.name_input)

        # Type
        self.type_label = QLabel(self.right_panel)
        self.type_label.setObjectName(u"type_label")
        self.type_combo = QComboBox(self.right_panel)
        self.type_combo.setObjectName(u"type_combo")
        self.form_layout.addRow(self.type_label, self.type_combo)

        # Address
        self.address_label = QLabel(self.right_panel)
        self.address_label.setObjectName(u"address_label")
        self.address_input = QLineEdit(self.right_panel)
        self.address_input.setObjectName(u"address_input")
        self.form_layout.addRow(self.address_label, self.address_input)

        self.right_layout.addLayout(self.form_layout)

        # Phone list
        self.phone_group = QGroupBox(self.right_panel)
        self.phone_group.setObjectName(u"phone_group")
        self.phone_group_layout = QVBoxLayout(self.phone_group)
        self.phone_group_layout.setObjectName(u"phone_group_layout")
        self.phone_list = QListWidget(self.phone_group)
        self.phone_list.setObjectName(u"phone_list")
        self.phone_list.setMaximumHeight(80)
        self.phone_group_layout.addWidget(self.phone_list)
        self.phone_buttons_layout = QHBoxLayout()
        self.phone_buttons_layout.setObjectName(u"phone_buttons_layout")
        self.add_phone_button = QPushButton(self.phone_group)
        self.add_phone_button.setObjectName(u"add_phone_button")
        self.phone_buttons_layout.addWidget(self.add_phone_button)
        self.remove_phone_button = QPushButton(self.phone_group)
        self.remove_phone_button.setObjectName(u"remove_phone_button")
        self.phone_buttons_layout.addWidget(self.remove_phone_button)
        self.phone_group_layout.addLayout(self.phone_buttons_layout)
        self.right_layout.addWidget(self.phone_group)

        # Email list
        self.email_group = QGroupBox(self.right_panel)
        self.email_group.setObjectName(u"email_group")
        self.email_group_layout = QVBoxLayout(self.email_group)
        self.email_group_layout.setObjectName(u"email_group_layout")
        self.email_list = QListWidget(self.email_group)
        self.email_list.setObjectName(u"email_list")
        self.email_list.setMaximumHeight(80)
        self.email_group_layout.addWidget(self.email_list)
        self.email_buttons_layout = QHBoxLayout()
        self.email_buttons_layout.setObjectName(u"email_buttons_layout")
        self.add_email_button = QPushButton(self.email_group)
        self.add_email_button.setObjectName(u"add_email_button")
        self.email_buttons_layout.addWidget(self.add_email_button)
        self.remove_email_button = QPushButton(self.email_group)
        self.remove_email_button.setObjectName(u"remove_email_button")
        self.email_buttons_layout.addWidget(self.remove_email_button)
        self.email_group_layout.addLayout(self.email_buttons_layout)
        self.right_layout.addWidget(self.email_group)

        # Web list
        self.web_group = QGroupBox(self.right_panel)
        self.web_group.setObjectName(u"web_group")
        self.web_group_layout = QVBoxLayout(self.web_group)
        self.web_group_layout.setObjectName(u"web_group_layout")
        self.web_list = QListWidget(self.web_group)
        self.web_list.setObjectName(u"web_list")
        self.web_list.setMaximumHeight(80)
        self.web_group_layout.addWidget(self.web_list)
        self.web_buttons_layout = QHBoxLayout()
        self.web_buttons_layout.setObjectName(u"web_buttons_layout")
        self.add_web_button = QPushButton(self.web_group)
        self.add_web_button.setObjectName(u"add_web_button")
        self.web_buttons_layout.addWidget(self.add_web_button)
        self.remove_web_button = QPushButton(self.web_group)
        self.remove_web_button.setObjectName(u"remove_web_button")
        self.web_buttons_layout.addWidget(self.remove_web_button)
        self.web_group_layout.addLayout(self.web_buttons_layout)
        self.right_layout.addWidget(self.web_group)

        # External IDs list
        self.external_ids_group = QGroupBox(self.right_panel)
        self.external_ids_group.setObjectName(u"external_ids_group")
        self.external_ids_group_layout = QVBoxLayout(self.external_ids_group)
        self.external_ids_group_layout.setObjectName(u"external_ids_group_layout")
        self.external_ids_list = QListWidget(self.external_ids_group)
        self.external_ids_list.setObjectName(u"external_ids_list")
        self.external_ids_list.setMaximumHeight(80)
        self.external_ids_group_layout.addWidget(self.external_ids_list)
        self.external_ids_buttons_layout = QHBoxLayout()
        self.external_ids_buttons_layout.setObjectName(u"external_ids_buttons_layout")
        self.add_external_id_button = QPushButton(self.external_ids_group)
        self.add_external_id_button.setObjectName(u"add_external_id_button")
        self.external_ids_buttons_layout.addWidget(self.add_external_id_button)
        self.remove_external_id_button = QPushButton(self.external_ids_group)
        self.remove_external_id_button.setObjectName(u"remove_external_id_button")
        self.external_ids_buttons_layout.addWidget(self.remove_external_id_button)
        self.external_ids_group_layout.addLayout(self.external_ids_buttons_layout)
        self.right_layout.addWidget(self.external_ids_group)

        # Notes
        self.notes_label = QLabel(self.right_panel)
        self.notes_label.setObjectName(u"notes_label")
        self.right_layout.addWidget(self.notes_label)
        self.notes_input = QTextEdit(self.right_panel)
        self.notes_input.setObjectName(u"notes_input")
        self.notes_input.setMaximumHeight(80)
        self.right_layout.addWidget(self.notes_input)

        # Save / Cancel buttons
        self.action_buttons_layout = QHBoxLayout()
        self.action_buttons_layout.setObjectName(u"action_buttons_layout")
        self.save_button = QPushButton(self.right_panel)
        self.save_button.setObjectName(u"save_button")
        self.action_buttons_layout.addWidget(self.save_button)
        self.cancel_button = QPushButton(self.right_panel)
        self.cancel_button.setObjectName(u"cancel_button")
        self.action_buttons_layout.addWidget(self.cancel_button)
        self.right_layout.addLayout(self.action_buttons_layout)

        # Status label
        self.status_label = QLabel(self.right_panel)
        self.status_label.setObjectName(u"status_label")
        self.right_layout.addWidget(self.status_label)

        self.splitter.addWidget(self.right_panel)

        # Set splitter sizes (left 30%, right 70%)
        self.splitter.setSizes([270, 630])

        self.main_layout.addWidget(self.splitter)

        self.retranslateUi(RepositoryEditor)

        QMetaObject.connectSlotsByName(RepositoryEditor)
    # setupUi

    def retranslateUi(self, RepositoryEditor):
        RepositoryEditor.setWindowTitle(QCoreApplication.translate("RepositoryEditor", u"Arkivredigerare", None))
        self.filter_input.setPlaceholderText(QCoreApplication.translate("RepositoryEditor", u"Filtrera arkiv...", None))
        self.add_repository_button.setText(QCoreApplication.translate("RepositoryEditor", u"Lägg till", None))
        self.delete_repository_button.setText(QCoreApplication.translate("RepositoryEditor", u"Ta bort", None))
        self.name_label.setText(QCoreApplication.translate("RepositoryEditor", u"Namn:", None))
        self.type_label.setText(QCoreApplication.translate("RepositoryEditor", u"Typ:", None))
        self.address_label.setText(QCoreApplication.translate("RepositoryEditor", u"Adress:", None))
        self.phone_group.setTitle(QCoreApplication.translate("RepositoryEditor", u"Telefon", None))
        self.add_phone_button.setText(QCoreApplication.translate("RepositoryEditor", u"Lägg till", None))
        self.remove_phone_button.setText(QCoreApplication.translate("RepositoryEditor", u"Ta bort", None))
        self.email_group.setTitle(QCoreApplication.translate("RepositoryEditor", u"E-post", None))
        self.add_email_button.setText(QCoreApplication.translate("RepositoryEditor", u"Lägg till", None))
        self.remove_email_button.setText(QCoreApplication.translate("RepositoryEditor", u"Ta bort", None))
        self.web_group.setTitle(QCoreApplication.translate("RepositoryEditor", u"Webb", None))
        self.add_web_button.setText(QCoreApplication.translate("RepositoryEditor", u"Lägg till", None))
        self.remove_web_button.setText(QCoreApplication.translate("RepositoryEditor", u"Ta bort", None))
        self.external_ids_group.setTitle(QCoreApplication.translate("RepositoryEditor", u"Externa ID", None))
        self.add_external_id_button.setText(QCoreApplication.translate("RepositoryEditor", u"Lägg till", None))
        self.remove_external_id_button.setText(QCoreApplication.translate("RepositoryEditor", u"Ta bort", None))
        self.notes_label.setText(QCoreApplication.translate("RepositoryEditor", u"Anteckningar:", None))
        self.save_button.setText(QCoreApplication.translate("RepositoryEditor", u"Spara", None))
        self.cancel_button.setText(QCoreApplication.translate("RepositoryEditor", u"Avbryt", None))
        self.status_label.setText("")

        self.type_combo.clear()
        self.type_combo.addItem(QCoreApplication.translate("RepositoryEditor", u"Arkiv", None))
        self.type_combo.addItem(QCoreApplication.translate("RepositoryEditor", u"Bibliotek", None))
        self.type_combo.addItem(QCoreApplication.translate("RepositoryEditor", u"Digitalt arkiv", None))
        self.type_combo.addItem(QCoreApplication.translate("RepositoryEditor", u"Museum", None))
        self.type_combo.addItem(QCoreApplication.translate("RepositoryEditor", u"Kyrkokontor", None))
        self.type_combo.addItem(QCoreApplication.translate("RepositoryEditor", u"\u00d6vrigt", None))
    # retranslateUi
