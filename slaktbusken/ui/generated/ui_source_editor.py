# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'source_editor.ui'
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
from PySide6.QtWidgets import (QApplication, QComboBox, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QSizePolicy, QSpacerItem, QSplitter,
    QTextEdit, QVBoxLayout, QWidget)

class Ui_SourceEditor(object):
    def setupUi(self, SourceEditor):
        if not SourceEditor.objectName():
            SourceEditor.setObjectName(u"SourceEditor")
        SourceEditor.resize(1000, 700)
        self.main_layout = QHBoxLayout(SourceEditor)
        self.main_layout.setObjectName(u"main_layout")
        self.splitter = QSplitter(SourceEditor)
        self.splitter.setObjectName(u"splitter")
        self.splitter.setOrientation(Qt.Horizontal)
        self.left_panel = QWidget(self.splitter)
        self.left_panel.setObjectName(u"left_panel")
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_layout.setObjectName(u"left_layout")
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.search_input = QLineEdit(self.left_panel)
        self.search_input.setObjectName(u"search_input")

        self.left_layout.addWidget(self.search_input)

        self.source_list = QListWidget(self.left_panel)
        self.source_list.setObjectName(u"source_list")

        self.left_layout.addWidget(self.source_list)

        self.list_buttons_layout = QHBoxLayout()
        self.list_buttons_layout.setObjectName(u"list_buttons_layout")
        self.add_source_button = QPushButton(self.left_panel)
        self.add_source_button.setObjectName(u"add_source_button")

        self.list_buttons_layout.addWidget(self.add_source_button)

        self.delete_source_button = QPushButton(self.left_panel)
        self.delete_source_button.setObjectName(u"delete_source_button")

        self.list_buttons_layout.addWidget(self.delete_source_button)


        self.left_layout.addLayout(self.list_buttons_layout)

        self.splitter.addWidget(self.left_panel)
        self.right_panel = QWidget(self.splitter)
        self.right_panel.setObjectName(u"right_panel")
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setObjectName(u"right_layout")
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.basic_group = QGroupBox(self.right_panel)
        self.basic_group.setObjectName(u"basic_group")
        self.basic_layout = QVBoxLayout(self.basic_group)
        self.basic_layout.setObjectName(u"basic_layout")
        self.provider_layout = QHBoxLayout()
        self.provider_layout.setObjectName(u"provider_layout")
        self.provider_label = QLabel(self.basic_group)
        self.provider_label.setObjectName(u"provider_label")

        self.provider_layout.addWidget(self.provider_label)

        self.provider_input = QLineEdit(self.basic_group)
        self.provider_input.setObjectName(u"provider_input")
        self.provider_input.setMaxLength(200)

        self.provider_layout.addWidget(self.provider_input)


        self.basic_layout.addLayout(self.provider_layout)

        self.type_layout = QHBoxLayout()
        self.type_layout.setObjectName(u"type_layout")
        self.type_label = QLabel(self.basic_group)
        self.type_label.setObjectName(u"type_label")

        self.type_layout.addWidget(self.type_label)

        self.source_type_combo = QComboBox(self.basic_group)
        self.source_type_combo.setObjectName(u"source_type_combo")

        self.type_layout.addWidget(self.source_type_combo)


        self.basic_layout.addLayout(self.type_layout)

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

        self.ref_text_layout = QHBoxLayout()
        self.ref_text_layout.setObjectName(u"ref_text_layout")
        self.ref_text_label = QLabel(self.basic_group)
        self.ref_text_label.setObjectName(u"ref_text_label")

        self.ref_text_layout.addWidget(self.ref_text_label)

        self.reference_text_input = QLineEdit(self.basic_group)
        self.reference_text_input.setObjectName(u"reference_text_input")
        self.reference_text_input.setMaxLength(500)

        self.ref_text_layout.addWidget(self.reference_text_input)


        self.basic_layout.addLayout(self.ref_text_layout)

        self.provider_ref_layout = QHBoxLayout()
        self.provider_ref_layout.setObjectName(u"provider_ref_layout")
        self.provider_ref_label = QLabel(self.basic_group)
        self.provider_ref_label.setObjectName(u"provider_ref_label")

        self.provider_ref_layout.addWidget(self.provider_ref_label)

        self.provider_ref_input = QLineEdit(self.basic_group)
        self.provider_ref_input.setObjectName(u"provider_ref_input")
        self.provider_ref_input.setMaxLength(200)

        self.provider_ref_layout.addWidget(self.provider_ref_input)


        self.basic_layout.addLayout(self.provider_ref_layout)

        self.short_note_layout = QHBoxLayout()
        self.short_note_layout.setObjectName(u"short_note_layout")
        self.short_note_label = QLabel(self.basic_group)
        self.short_note_label.setObjectName(u"short_note_label")

        self.short_note_layout.addWidget(self.short_note_label)

        self.short_note_input = QLineEdit(self.basic_group)
        self.short_note_input.setObjectName(u"short_note_input")
        self.short_note_input.setMaxLength(200)

        self.short_note_layout.addWidget(self.short_note_input)


        self.basic_layout.addLayout(self.short_note_layout)

        self.free_note_layout = QVBoxLayout()
        self.free_note_layout.setObjectName(u"free_note_layout")
        self.free_note_label = QLabel(self.basic_group)
        self.free_note_label.setObjectName(u"free_note_label")

        self.free_note_layout.addWidget(self.free_note_label)

        self.free_note_input = QTextEdit(self.basic_group)
        self.free_note_input.setObjectName(u"free_note_input")
        self.free_note_input.setMaximumSize(QSize(16777215, 80))

        self.free_note_layout.addWidget(self.free_note_input)


        self.basic_layout.addLayout(self.free_note_layout)


        self.right_layout.addWidget(self.basic_group)

        self.structured_ref_group = QGroupBox(self.right_panel)
        self.structured_ref_group.setObjectName(u"structured_ref_group")
        self.structured_ref_layout = QVBoxLayout(self.structured_ref_group)
        self.structured_ref_layout.setObjectName(u"structured_ref_layout")
        self.parish_layout = QHBoxLayout()
        self.parish_layout.setObjectName(u"parish_layout")
        self.parish_label = QLabel(self.structured_ref_group)
        self.parish_label.setObjectName(u"parish_label")

        self.parish_layout.addWidget(self.parish_label)

        self.parish_input = QLineEdit(self.structured_ref_group)
        self.parish_input.setObjectName(u"parish_input")

        self.parish_layout.addWidget(self.parish_input)


        self.structured_ref_layout.addLayout(self.parish_layout)

        self.county_code_layout = QHBoxLayout()
        self.county_code_layout.setObjectName(u"county_code_layout")
        self.county_code_label = QLabel(self.structured_ref_group)
        self.county_code_label.setObjectName(u"county_code_label")

        self.county_code_layout.addWidget(self.county_code_label)

        self.county_code_input = QLineEdit(self.structured_ref_group)
        self.county_code_input.setObjectName(u"county_code_input")

        self.county_code_layout.addWidget(self.county_code_input)


        self.structured_ref_layout.addLayout(self.county_code_layout)

        self.series_layout = QHBoxLayout()
        self.series_layout.setObjectName(u"series_layout")
        self.series_label = QLabel(self.structured_ref_group)
        self.series_label.setObjectName(u"series_label")

        self.series_layout.addWidget(self.series_label)

        self.series_input = QLineEdit(self.structured_ref_group)
        self.series_input.setObjectName(u"series_input")

        self.series_layout.addWidget(self.series_input)


        self.structured_ref_layout.addLayout(self.series_layout)

        self.volume_layout = QHBoxLayout()
        self.volume_layout.setObjectName(u"volume_layout")
        self.volume_label = QLabel(self.structured_ref_group)
        self.volume_label.setObjectName(u"volume_label")

        self.volume_layout.addWidget(self.volume_label)

        self.volume_input = QLineEdit(self.structured_ref_group)
        self.volume_input.setObjectName(u"volume_input")

        self.volume_layout.addWidget(self.volume_input)


        self.structured_ref_layout.addLayout(self.volume_layout)

        self.years_layout = QHBoxLayout()
        self.years_layout.setObjectName(u"years_layout")
        self.years_label = QLabel(self.structured_ref_group)
        self.years_label.setObjectName(u"years_label")

        self.years_layout.addWidget(self.years_label)

        self.years_input = QLineEdit(self.structured_ref_group)
        self.years_input.setObjectName(u"years_input")

        self.years_layout.addWidget(self.years_input)


        self.structured_ref_layout.addLayout(self.years_layout)

        self.image_layout = QHBoxLayout()
        self.image_layout.setObjectName(u"image_layout")
        self.image_label = QLabel(self.structured_ref_group)
        self.image_label.setObjectName(u"image_label")

        self.image_layout.addWidget(self.image_label)

        self.image_input = QLineEdit(self.structured_ref_group)
        self.image_input.setObjectName(u"image_input")

        self.image_layout.addWidget(self.image_input)


        self.structured_ref_layout.addLayout(self.image_layout)

        self.page_layout = QHBoxLayout()
        self.page_layout.setObjectName(u"page_layout")
        self.page_label = QLabel(self.structured_ref_group)
        self.page_label.setObjectName(u"page_label")

        self.page_layout.addWidget(self.page_label)

        self.page_input = QLineEdit(self.structured_ref_group)
        self.page_input.setObjectName(u"page_input")

        self.page_layout.addWidget(self.page_input)


        self.structured_ref_layout.addLayout(self.page_layout)

        self.database_name_layout = QHBoxLayout()
        self.database_name_layout.setObjectName(u"database_name_layout")
        self.database_name_label = QLabel(self.structured_ref_group)
        self.database_name_label.setObjectName(u"database_name_label")

        self.database_name_layout.addWidget(self.database_name_label)

        self.database_name_input = QLineEdit(self.structured_ref_group)
        self.database_name_input.setObjectName(u"database_name_input")

        self.database_name_layout.addWidget(self.database_name_input)


        self.structured_ref_layout.addLayout(self.database_name_layout)

        self.record_id_layout = QHBoxLayout()
        self.record_id_layout.setObjectName(u"record_id_layout")
        self.record_id_label = QLabel(self.structured_ref_group)
        self.record_id_label.setObjectName(u"record_id_label")

        self.record_id_layout.addWidget(self.record_id_label)

        self.record_id_input = QLineEdit(self.structured_ref_group)
        self.record_id_input.setObjectName(u"record_id_input")

        self.record_id_layout.addWidget(self.record_id_input)


        self.structured_ref_layout.addLayout(self.record_id_layout)

        self.dn_newspaper_layout = QHBoxLayout()
        self.dn_newspaper_layout.setObjectName(u"dn_newspaper_layout")
        self.dn_newspaper_label = QLabel(self.structured_ref_group)
        self.dn_newspaper_label.setObjectName(u"dn_newspaper_label")

        self.dn_newspaper_layout.addWidget(self.dn_newspaper_label)

        self.dn_newspaper_input = QLineEdit(self.structured_ref_group)
        self.dn_newspaper_input.setObjectName(u"dn_newspaper_input")

        self.dn_newspaper_layout.addWidget(self.dn_newspaper_input)


        self.structured_ref_layout.addLayout(self.dn_newspaper_layout)

        self.publication_date_layout = QHBoxLayout()
        self.publication_date_layout.setObjectName(u"publication_date_layout")
        self.publication_date_label = QLabel(self.structured_ref_group)
        self.publication_date_label.setObjectName(u"publication_date_label")

        self.publication_date_layout.addWidget(self.publication_date_label)

        self.publication_date_input = QLineEdit(self.structured_ref_group)
        self.publication_date_input.setObjectName(u"publication_date_input")

        self.publication_date_layout.addWidget(self.publication_date_input)


        self.structured_ref_layout.addLayout(self.publication_date_layout)

        self.dn_page_layout = QHBoxLayout()
        self.dn_page_layout.setObjectName(u"dn_page_layout")
        self.dn_page_label = QLabel(self.structured_ref_group)
        self.dn_page_label.setObjectName(u"dn_page_label")

        self.dn_page_layout.addWidget(self.dn_page_label)

        self.dn_page_input = QLineEdit(self.structured_ref_group)
        self.dn_page_input.setObjectName(u"dn_page_input")

        self.dn_page_layout.addWidget(self.dn_page_input)


        self.structured_ref_layout.addLayout(self.dn_page_layout)

        self.np_newspaper_layout = QHBoxLayout()
        self.np_newspaper_layout.setObjectName(u"np_newspaper_layout")
        self.np_newspaper_label = QLabel(self.structured_ref_group)
        self.np_newspaper_label.setObjectName(u"np_newspaper_label")

        self.np_newspaper_layout.addWidget(self.np_newspaper_label)

        self.np_newspaper_input = QLineEdit(self.structured_ref_group)
        self.np_newspaper_input.setObjectName(u"np_newspaper_input")

        self.np_newspaper_layout.addWidget(self.np_newspaper_input)


        self.structured_ref_layout.addLayout(self.np_newspaper_layout)

        self.np_date_layout = QHBoxLayout()
        self.np_date_layout.setObjectName(u"np_date_layout")
        self.np_date_label = QLabel(self.structured_ref_group)
        self.np_date_label.setObjectName(u"np_date_label")

        self.np_date_layout.addWidget(self.np_date_label)

        self.np_date_input = QLineEdit(self.structured_ref_group)
        self.np_date_input.setObjectName(u"np_date_input")

        self.np_date_layout.addWidget(self.np_date_input)


        self.structured_ref_layout.addLayout(self.np_date_layout)

        self.np_page_layout = QHBoxLayout()
        self.np_page_layout.setObjectName(u"np_page_layout")
        self.np_page_label = QLabel(self.structured_ref_group)
        self.np_page_label.setObjectName(u"np_page_label")

        self.np_page_layout.addWidget(self.np_page_label)

        self.np_page_input = QLineEdit(self.structured_ref_group)
        self.np_page_input.setObjectName(u"np_page_input")

        self.np_page_layout.addWidget(self.np_page_input)


        self.structured_ref_layout.addLayout(self.np_page_layout)

        self.article_title_layout = QHBoxLayout()
        self.article_title_layout.setObjectName(u"article_title_layout")
        self.article_title_label = QLabel(self.structured_ref_group)
        self.article_title_label.setObjectName(u"article_title_label")

        self.article_title_layout.addWidget(self.article_title_label)

        self.article_title_input = QLineEdit(self.structured_ref_group)
        self.article_title_input.setObjectName(u"article_title_input")

        self.article_title_layout.addWidget(self.article_title_input)


        self.structured_ref_layout.addLayout(self.article_title_layout)


        self.right_layout.addWidget(self.structured_ref_group)

        self.media_group = QGroupBox(self.right_panel)
        self.media_group.setObjectName(u"media_group")
        self.media_group_layout = QVBoxLayout(self.media_group)
        self.media_group_layout.setObjectName(u"media_group_layout")
        self.media_list = QListWidget(self.media_group)
        self.media_list.setObjectName(u"media_list")

        self.media_group_layout.addWidget(self.media_list)

        self.media_buttons_layout = QHBoxLayout()
        self.media_buttons_layout.setObjectName(u"media_buttons_layout")
        self.add_media_button = QPushButton(self.media_group)
        self.add_media_button.setObjectName(u"add_media_button")

        self.media_buttons_layout.addWidget(self.add_media_button)

        self.remove_media_button = QPushButton(self.media_group)
        self.remove_media_button.setObjectName(u"remove_media_button")

        self.media_buttons_layout.addWidget(self.remove_media_button)


        self.media_group_layout.addLayout(self.media_buttons_layout)


        self.right_layout.addWidget(self.media_group)

        self.repository_group = QGroupBox(self.right_panel)
        self.repository_group.setObjectName(u"repository_group")
        self.repository_group_layout = QVBoxLayout(self.repository_group)
        self.repository_group_layout.setObjectName(u"repository_group_layout")
        self.repository_list = QListWidget(self.repository_group)
        self.repository_list.setObjectName(u"repository_list")

        self.repository_group_layout.addWidget(self.repository_list)

        self.repository_buttons_layout = QHBoxLayout()
        self.repository_buttons_layout.setObjectName(u"repository_buttons_layout")
        self.add_repository_button = QPushButton(self.repository_group)
        self.add_repository_button.setObjectName(u"add_repository_button")

        self.repository_buttons_layout.addWidget(self.add_repository_button)

        self.remove_repository_button = QPushButton(self.repository_group)
        self.remove_repository_button.setObjectName(u"remove_repository_button")

        self.repository_buttons_layout.addWidget(self.remove_repository_button)


        self.repository_group_layout.addLayout(self.repository_buttons_layout)


        self.right_layout.addWidget(self.repository_group)

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


        self.retranslateUi(SourceEditor)

        QMetaObject.connectSlotsByName(SourceEditor)
    # setupUi

    def retranslateUi(self, SourceEditor):
        SourceEditor.setWindowTitle(QCoreApplication.translate("SourceEditor", u"K\u00e4llredigerare", None))
        self.search_input.setPlaceholderText(QCoreApplication.translate("SourceEditor", u"S\u00f6k k\u00e4lla (titel eller leverant\u00f6r)...", None))
        self.add_source_button.setText(QCoreApplication.translate("SourceEditor", u"L\u00e4gg till", None))
        self.delete_source_button.setText(QCoreApplication.translate("SourceEditor", u"Ta bort", None))
        self.basic_group.setTitle(QCoreApplication.translate("SourceEditor", u"K\u00e4lluppgifter", None))
        self.provider_label.setText(QCoreApplication.translate("SourceEditor", u"Leverant\u00f6r:", None))
        self.type_label.setText(QCoreApplication.translate("SourceEditor", u"K\u00e4lltyp:", None))
        self.title_label.setText(QCoreApplication.translate("SourceEditor", u"Titel:", None))
        self.ref_text_label.setText(QCoreApplication.translate("SourceEditor", u"Referenstext:", None))
        self.provider_ref_label.setText(QCoreApplication.translate("SourceEditor", u"Leverant\u00f6rsref:", None))
        self.short_note_label.setText(QCoreApplication.translate("SourceEditor", u"Kort notering:", None))
        self.free_note_label.setText(QCoreApplication.translate("SourceEditor", u"Fri anteckning:", None))
        self.structured_ref_group.setTitle(QCoreApplication.translate("SourceEditor", u"Strukturerad referens", None))
        self.parish_label.setText(QCoreApplication.translate("SourceEditor", u"F\u00f6rsamling:", None))
        self.county_code_label.setText(QCoreApplication.translate("SourceEditor", u"L\u00e4nskod:", None))
        self.series_label.setText(QCoreApplication.translate("SourceEditor", u"Serie:", None))
        self.volume_label.setText(QCoreApplication.translate("SourceEditor", u"Volym:", None))
        self.years_label.setText(QCoreApplication.translate("SourceEditor", u"\u00c5r:", None))
        self.image_label.setText(QCoreApplication.translate("SourceEditor", u"Bild:", None))
        self.page_label.setText(QCoreApplication.translate("SourceEditor", u"Sida:", None))
        self.database_name_label.setText(QCoreApplication.translate("SourceEditor", u"Databasnamn:", None))
        self.record_id_label.setText(QCoreApplication.translate("SourceEditor", u"Post-ID:", None))
        self.dn_newspaper_label.setText(QCoreApplication.translate("SourceEditor", u"Tidning:", None))
        self.publication_date_label.setText(QCoreApplication.translate("SourceEditor", u"Publiceringsdatum:", None))
        self.dn_page_label.setText(QCoreApplication.translate("SourceEditor", u"Sida:", None))
        self.np_newspaper_label.setText(QCoreApplication.translate("SourceEditor", u"Tidning:", None))
        self.np_date_label.setText(QCoreApplication.translate("SourceEditor", u"Datum:", None))
        self.np_page_label.setText(QCoreApplication.translate("SourceEditor", u"Sida:", None))
        self.article_title_label.setText(QCoreApplication.translate("SourceEditor", u"Artikeltitel:", None))
        self.media_group.setTitle(QCoreApplication.translate("SourceEditor", u"L\u00e4nkade media", None))
        self.add_media_button.setText(QCoreApplication.translate("SourceEditor", u"L\u00e4gg till media", None))
        self.remove_media_button.setText(QCoreApplication.translate("SourceEditor", u"Ta bort media", None))
        self.repository_group.setTitle(QCoreApplication.translate("SourceEditor", u"Arkivreferenser", None))
        self.add_repository_button.setText(QCoreApplication.translate("SourceEditor", u"L\u00e4gg till arkiv", None))
        self.remove_repository_button.setText(QCoreApplication.translate("SourceEditor", u"Ta bort arkiv", None))
        self.status_label.setText("")
        self.status_label.setStyleSheet(QCoreApplication.translate("SourceEditor", u"color: red;", None))
        self.save_button.setText(QCoreApplication.translate("SourceEditor", u"Spara", None))
        self.cancel_button.setText(QCoreApplication.translate("SourceEditor", u"Avbryt", None))
    # retranslateUi

