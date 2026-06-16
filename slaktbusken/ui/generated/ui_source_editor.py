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
from PySide6.QtWidgets import (QApplication, QSizePolicy, QWidget)

class Ui_SourceEditor(object):
    def setupUi(self, SourceEditor):
        if not SourceEditor.objectName():
            SourceEditor.setObjectName(u"SourceEditor")
        SourceEditor.resize(600, 400)

        self.retranslateUi(SourceEditor)

        QMetaObject.connectSlotsByName(SourceEditor)
    # setupUi

    def retranslateUi(self, SourceEditor):
        SourceEditor.setWindowTitle(QCoreApplication.translate("SourceEditor", u"Source Editor", None))
    # retranslateUi

