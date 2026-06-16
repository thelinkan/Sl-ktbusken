# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'person_editor.ui'
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

class Ui_PersonEditor(object):
    def setupUi(self, PersonEditor):
        if not PersonEditor.objectName():
            PersonEditor.setObjectName(u"PersonEditor")
        PersonEditor.resize(600, 400)

        self.retranslateUi(PersonEditor)

        QMetaObject.connectSlotsByName(PersonEditor)
    # setupUi

    def retranslateUi(self, PersonEditor):
        PersonEditor.setWindowTitle(QCoreApplication.translate("PersonEditor", u"Person Editor", None))
    # retranslateUi

