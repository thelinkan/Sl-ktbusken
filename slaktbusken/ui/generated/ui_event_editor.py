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
from PySide6.QtWidgets import (QApplication, QSizePolicy, QWidget)

class Ui_EventEditor(object):
    def setupUi(self, EventEditor):
        if not EventEditor.objectName():
            EventEditor.setObjectName(u"EventEditor")
        EventEditor.resize(600, 400)

        self.retranslateUi(EventEditor)

        QMetaObject.connectSlotsByName(EventEditor)
    # setupUi

    def retranslateUi(self, EventEditor):
        EventEditor.setWindowTitle(QCoreApplication.translate("EventEditor", u"Event Editor", None))
    # retranslateUi

