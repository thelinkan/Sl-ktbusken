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
from PySide6.QtWidgets import (QApplication, QSizePolicy, QWidget)

class Ui_PlaceEditor(object):
    def setupUi(self, PlaceEditor):
        if not PlaceEditor.objectName():
            PlaceEditor.setObjectName(u"PlaceEditor")
        PlaceEditor.resize(600, 400)

        self.retranslateUi(PlaceEditor)

        QMetaObject.connectSlotsByName(PlaceEditor)
    # setupUi

    def retranslateUi(self, PlaceEditor):
        PlaceEditor.setWindowTitle(QCoreApplication.translate("PlaceEditor", u"Place Editor", None))
    # retranslateUi

