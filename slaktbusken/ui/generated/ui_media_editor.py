# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'media_editor.ui'
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
from PySide6.QtWidgets import (QApplication, QComboBox, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QSizePolicy,
    QSpacerItem, QSplitter, QTextEdit, QVBoxLayout,
    QWidget)


class Ui_MediaEditor(object):
    def setupUi(self, MediaEditor):
        if not MediaEditor.objectName():
            MediaEditor.setObjectName(u"MediaEditor")
        MediaEditor.resize(1100, 750)
        self.main_layout = QHBoxLayout(MediaEditor)
        self.main_layout.setObjectName(u"main_layout")

        # Splitter: left panel (media list) + right panel (edit form)
        self.splitter = QSplitter(MediaEditor)
        self.splitter.setObjectName(u"splitter")
        self.splitter.setOrientation(Qt.Orientation.Horizontal)

        # --- Left panel: media list ---
        self.left_panel = QWidget(self.splitter)
        self.left_panel.setObjectName(u"left_panel")
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_layout.setObjectName(u"left_layout")

        self.search_input = QLineEdit(self.left_panel)
        self.search_input.setObjectName(u"search_input")
        self.left_layout.addWidget(self.search_input)

        self.media_list = QListWidget(self.left_panel)
        self.media_list.setObjectName(u"media_list")
        self.left_layout.addWidget(self.media_list)

        self.list_buttons_layout = QHBoxLayout()
        self.list_buttons_layout.setObjectName(u"list_buttons_layout")
        self.add_media_button = QPushButton(self.left_panel)
        self.add_media_button.setObjectName(u"add_media_button")
        self.list_buttons_layout.addWidget(self.add_media_button)

        self.delete_media_button = QPushButton(self.left_panel)
        self.delete_media_button.setObjectName(u"delete_media_button")
        self.list_buttons_layout.addWidget(self.delete_media_button)

        self.list_buttons_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.list_buttons_layout.addItem(self.list_buttons_spacer)
        self.left_layout.addLayout(self.list_buttons_layout)

        self.splitter.addWidget(self.left_panel)

        # --- Right panel: edit form ---
        self.right_panel = QWidget(self.splitter)
        self.right_panel.setObjectName(u"right_panel")
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setObjectName(u"right_layout")

        # Basic fields group
        self.basic_group = QGroupBox(self.right_panel)
        self.basic_group.setObjectName(u"basic_group")
        self.basic_layout = QVBoxLayout(self.basic_group)
        self.basic_layout.setObjectName(u"basic_layout")

        # File path + browse button
        self.file_layout = QHBoxLayout()
        self.file_layout.setObjectName(u"file_layout")
        self.file_label = QLabel(self.basic_group)
        self.file_label.setObjectName(u"file_label")
        self.file_layout.addWidget(self.file_label)
        self.file_input = QLineEdit(self.basic_group)
        self.file_input.setObjectName(u"file_input")
        self.file_layout.addWidget(self.file_input)
        self.browse_button = QPushButton(self.basic_group)
        self.browse_button.setObjectName(u"browse_button")
        self.file_layout.addWidget(self.browse_button)
        self.basic_layout.addLayout(self.file_layout)

        # Missing file indicator
        self.missing_file_label = QLabel(self.basic_group)
        self.missing_file_label.setObjectName(u"missing_file_label")
        self.missing_file_label.setVisible(False)
        self.basic_layout.addWidget(self.missing_file_label)

        # Media type combo
        self.type_layout = QHBoxLayout()
        self.type_layout.setObjectName(u"type_layout")
        self.type_label = QLabel(self.basic_group)
        self.type_label.setObjectName(u"type_label")
        self.type_layout.addWidget(self.type_label)
        self.media_type_combo = QComboBox(self.basic_group)
        self.media_type_combo.setObjectName(u"media_type_combo")
        self.type_layout.addWidget(self.media_type_combo)
        self.basic_layout.addLayout(self.type_layout)

        # Title
        self.title_layout = QHBoxLayout()
        self.title_layout.setObjectName(u"title_layout")
        self.title_label = QLabel(self.basic_group)
        self.title_label.setObjectName(u"title_label")
        self.title_layout.addWidget(self.title_label)
        self.title_input = QLineEdit(self.basic_group)
        self.title_input.setObjectName(u"title_input")
        self.title_input.setMaxLength(500)
        self.title_layout.addWidget(self.title_input)
        self.basic_layout.addLayout(self.title_layout)

        self.right_layout.addWidget(self.basic_group)

        # Linked entities group
        self.linked_entities_group = QGroupBox(self.right_panel)
        self.linked_entities_group.setObjectName(u"linked_entities_group")
        self.linked_entities_layout = QVBoxLayout(self.linked_entities_group)
        self.linked_entities_layout.setObjectName(u"linked_entities_layout")

        self.linked_entities_list = QListWidget(self.linked_entities_group)
        self.linked_entities_list.setObjectName(u"linked_entities_list")
        self.linked_entities_list.setMaximumHeight(100)
        self.linked_entities_layout.addWidget(self.linked_entities_list)

        # Entity input row: type combo, id input, role input
        self.entity_input_layout = QHBoxLayout()
        self.entity_input_layout.setObjectName(u"entity_input_layout")
        self.entity_type_combo = QComboBox(self.linked_entities_group)
        self.entity_type_combo.setObjectName(u"entity_type_combo")
        self.entity_input_layout.addWidget(self.entity_type_combo)
        self.entity_id_input = QLineEdit(self.linked_entities_group)
        self.entity_id_input.setObjectName(u"entity_id_input")
        self.entity_input_layout.addWidget(self.entity_id_input)
        self.entity_role_input = QLineEdit(self.linked_entities_group)
        self.entity_role_input.setObjectName(u"entity_role_input")
        self.entity_input_layout.addWidget(self.entity_role_input)
        self.linked_entities_layout.addLayout(self.entity_input_layout)

        # Entity buttons
        self.entity_buttons_layout = QHBoxLayout()
        self.entity_buttons_layout.setObjectName(u"entity_buttons_layout")
        self.add_entity_button = QPushButton(self.linked_entities_group)
        self.add_entity_button.setObjectName(u"add_entity_button")
        self.entity_buttons_layout.addWidget(self.add_entity_button)
        self.remove_entity_button = QPushButton(self.linked_entities_group)
        self.remove_entity_button.setObjectName(u"remove_entity_button")
        self.entity_buttons_layout.addWidget(self.remove_entity_button)
        self.entity_buttons_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.entity_buttons_layout.addItem(self.entity_buttons_spacer)
        self.linked_entities_layout.addLayout(self.entity_buttons_layout)

        self.right_layout.addWidget(self.linked_entities_group)

        # Type-specific fields group
        self.type_specific_group = QGroupBox(self.right_panel)
        self.type_specific_group.setObjectName(u"type_specific_group")
        self.type_specific_layout = QVBoxLayout(self.type_specific_group)
        self.type_specific_layout.setObjectName(u"type_specific_layout")

        # Publication fields (for death_notice)
        self.newspaper_layout = QHBoxLayout()
        self.newspaper_layout.setObjectName(u"newspaper_layout")
        self.newspaper_label = QLabel(self.type_specific_group)
        self.newspaper_label.setObjectName(u"newspaper_label")
        self.newspaper_layout.addWidget(self.newspaper_label)
        self.newspaper_input = QLineEdit(self.type_specific_group)
        self.newspaper_input.setObjectName(u"newspaper_input")
        self.newspaper_layout.addWidget(self.newspaper_input)
        self.type_specific_layout.addLayout(self.newspaper_layout)

        self.pub_date_layout = QHBoxLayout()
        self.pub_date_layout.setObjectName(u"pub_date_layout")
        self.pub_date_label = QLabel(self.type_specific_group)
        self.pub_date_label.setObjectName(u"pub_date_label")
        self.pub_date_layout.addWidget(self.pub_date_label)
        self.pub_date_input = QLineEdit(self.type_specific_group)
        self.pub_date_input.setObjectName(u"pub_date_input")
        self.pub_date_layout.addWidget(self.pub_date_input)
        self.type_specific_layout.addLayout(self.pub_date_layout)

        self.pub_page_layout = QHBoxLayout()
        self.pub_page_layout.setObjectName(u"pub_page_layout")
        self.pub_page_label = QLabel(self.type_specific_group)
        self.pub_page_label.setObjectName(u"pub_page_label")
        self.pub_page_layout.addWidget(self.pub_page_label)
        self.pub_page_input = QLineEdit(self.type_specific_group)
        self.pub_page_input.setObjectName(u"pub_page_input")
        self.pub_page_layout.addWidget(self.pub_page_input)
        self.type_specific_layout.addLayout(self.pub_page_layout)

        # Transcription
        self.transcription_layout = QVBoxLayout()
        self.transcription_layout.setObjectName(u"transcription_layout")
        self.transcription_label = QLabel(self.type_specific_group)
        self.transcription_label.setObjectName(u"transcription_label")
        self.transcription_layout.addWidget(self.transcription_label)
        self.transcription_input = QTextEdit(self.type_specific_group)
        self.transcription_input.setObjectName(u"transcription_input")
        self.transcription_input.setMaximumHeight(100)
        self.transcription_layout.addWidget(self.transcription_input)
        self.type_specific_layout.addLayout(self.transcription_layout)

        # Mentioned persons
        self.mentioned_layout = QVBoxLayout()
        self.mentioned_layout.setObjectName(u"mentioned_layout")
        self.mentioned_label = QLabel(self.type_specific_group)
        self.mentioned_label.setObjectName(u"mentioned_label")
        self.mentioned_layout.addWidget(self.mentioned_label)
        self.mentioned_persons_list = QListWidget(self.type_specific_group)
        self.mentioned_persons_list.setObjectName(u"mentioned_persons_list")
        self.mentioned_persons_list.setMaximumHeight(80)
        self.mentioned_layout.addWidget(self.mentioned_persons_list)

        self.mentioned_buttons_layout = QHBoxLayout()
        self.mentioned_buttons_layout.setObjectName(u"mentioned_buttons_layout")
        self.mentioned_person_input = QLineEdit(self.type_specific_group)
        self.mentioned_person_input.setObjectName(u"mentioned_person_input")
        self.mentioned_buttons_layout.addWidget(self.mentioned_person_input)
        self.add_mentioned_button = QPushButton(self.type_specific_group)
        self.add_mentioned_button.setObjectName(u"add_mentioned_button")
        self.mentioned_buttons_layout.addWidget(self.add_mentioned_button)
        self.remove_mentioned_button = QPushButton(self.type_specific_group)
        self.remove_mentioned_button.setObjectName(u"remove_mentioned_button")
        self.mentioned_buttons_layout.addWidget(self.remove_mentioned_button)
        self.mentioned_layout.addLayout(self.mentioned_buttons_layout)
        self.type_specific_layout.addLayout(self.mentioned_layout)

        self.right_layout.addWidget(self.type_specific_group)

        # Status label
        self.status_label = QLabel(self.right_panel)
        self.status_label.setObjectName(u"status_label")
        self.right_layout.addWidget(self.status_label)

        # Save/Cancel buttons
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
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)

        self.main_layout.addWidget(self.splitter)

        self.retranslateUi(MediaEditor)

        QMetaObject.connectSlotsByName(MediaEditor)
    # setupUi

    def retranslateUi(self, MediaEditor):
        MediaEditor.setWindowTitle(QCoreApplication.translate("MediaEditor", u"Mediaredigerare", None))
        self.search_input.setPlaceholderText(QCoreApplication.translate("MediaEditor", u"S\u00f6k media (titel eller filnamn)...", None))
        self.add_media_button.setText(QCoreApplication.translate("MediaEditor", u"L\u00e4gg till", None))
        self.delete_media_button.setText(QCoreApplication.translate("MediaEditor", u"Ta bort", None))
        self.basic_group.setTitle(QCoreApplication.translate("MediaEditor", u"Grunduppgifter", None))
        self.file_label.setText(QCoreApplication.translate("MediaEditor", u"Fil:", None))
        self.file_input.setPlaceholderText(QCoreApplication.translate("MediaEditor", u"S\u00f6kv\u00e4g till mediafil...", None))
        self.browse_button.setText(QCoreApplication.translate("MediaEditor", u"Bl\u00e4ddra...", None))
        self.missing_file_label.setText(QCoreApplication.translate("MediaEditor", u"\u26a0 Filen saknas p\u00e5 disk", None))
        self.missing_file_label.setStyleSheet(QCoreApplication.translate("MediaEditor", u"color: red; font-weight: bold;", None))
        self.type_label.setText(QCoreApplication.translate("MediaEditor", u"Mediatyp:", None))
        self.title_label.setText(QCoreApplication.translate("MediaEditor", u"Titel:", None))
        self.title_input.setPlaceholderText(QCoreApplication.translate("MediaEditor", u"Mediaobjektets titel", None))
        self.linked_entities_group.setTitle(QCoreApplication.translate("MediaEditor", u"L\u00e4nkade entiteter", None))
        self.entity_id_input.setPlaceholderText(QCoreApplication.translate("MediaEditor", u"Entitets-ID", None))
        self.entity_role_input.setPlaceholderText(QCoreApplication.translate("MediaEditor", u"Roll (valfri)", None))
        self.add_entity_button.setText(QCoreApplication.translate("MediaEditor", u"L\u00e4gg till entitet", None))
        self.remove_entity_button.setText(QCoreApplication.translate("MediaEditor", u"Ta bort entitet", None))
        self.type_specific_group.setTitle(QCoreApplication.translate("MediaEditor", u"Typspecifika f\u00e4lt", None))
        self.newspaper_label.setText(QCoreApplication.translate("MediaEditor", u"Tidning:", None))
        self.pub_date_label.setText(QCoreApplication.translate("MediaEditor", u"Publiceringsdatum:", None))
        self.pub_page_label.setText(QCoreApplication.translate("MediaEditor", u"Sida:", None))
        self.transcription_label.setText(QCoreApplication.translate("MediaEditor", u"Transkription:", None))
        self.mentioned_label.setText(QCoreApplication.translate("MediaEditor", u"Omn\u00e4mnda personer:", None))
        self.mentioned_person_input.setPlaceholderText(QCoreApplication.translate("MediaEditor", u"Person-ID", None))
        self.add_mentioned_button.setText(QCoreApplication.translate("MediaEditor", u"L\u00e4gg till", None))
        self.remove_mentioned_button.setText(QCoreApplication.translate("MediaEditor", u"Ta bort", None))
        self.status_label.setText("")
        self.status_label.setStyleSheet(QCoreApplication.translate("MediaEditor", u"color: red;", None))
        self.save_button.setText(QCoreApplication.translate("MediaEditor", u"Spara", None))
        self.cancel_button.setText(QCoreApplication.translate("MediaEditor", u"Avbryt", None))
    # retranslateUi
