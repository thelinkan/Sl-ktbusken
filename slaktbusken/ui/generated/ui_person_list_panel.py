# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'person_list_panel.ui'
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

class Ui_PersonListPanel(object):
    def setupUi(self, PersonListPanel):
        if not PersonListPanel.objectName():
            PersonListPanel.setObjectName(u"PersonListPanel")
        PersonListPanel.resize(300, 600)

        self.retranslateUi(PersonListPanel)

        QMetaObject.connectSlotsByName(PersonListPanel)
    # setupUi

    def retranslateUi(self, PersonListPanel):
        PersonListPanel.setWindowTitle(QCoreApplication.translate("PersonListPanel", u"Person List", None))
    # retranslateUi

