# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'new_project_dialog.ui'
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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSizePolicy, QSpacerItem, QVBoxLayout,
    QWidget)

class Ui_NewProjectDialog(object):
    def setupUi(self, NewProjectDialog):
        if not NewProjectDialog.objectName():
            NewProjectDialog.setObjectName(u"NewProjectDialog")
        NewProjectDialog.resize(500, 200)
        self.verticalLayout = QVBoxLayout(NewProjectDialog)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.labelName = QLabel(NewProjectDialog)
        self.labelName.setObjectName(u"labelName")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.labelName)

        self.lineEditName = QLineEdit(NewProjectDialog)
        self.lineEditName.setObjectName(u"lineEditName")
        self.lineEditName.setMaxLength(100)

        self.formLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lineEditName)

        self.labelLocation = QLabel(NewProjectDialog)
        self.labelLocation.setObjectName(u"labelLocation")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.labelLocation)

        self.locationLayout = QHBoxLayout()
        self.locationLayout.setObjectName(u"locationLayout")
        self.labelLocationPath = QLabel(NewProjectDialog)
        self.labelLocationPath.setObjectName(u"labelLocationPath")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.labelLocationPath.sizePolicy().hasHeightForWidth())
        self.labelLocationPath.setSizePolicy(sizePolicy)

        self.locationLayout.addWidget(self.labelLocationPath)

        self.buttonBrowse = QPushButton(NewProjectDialog)
        self.buttonBrowse.setObjectName(u"buttonBrowse")

        self.locationLayout.addWidget(self.buttonBrowse)


        self.formLayout.setLayout(1, QFormLayout.ItemRole.FieldRole, self.locationLayout)


        self.verticalLayout.addLayout(self.formLayout)

        self.labelError = QLabel(NewProjectDialog)
        self.labelError.setObjectName(u"labelError")

        self.verticalLayout.addWidget(self.labelError)

        self.verticalSpacer = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout.addItem(self.verticalSpacer)

        self.buttonBox = QDialogButtonBox(NewProjectDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)

        self.verticalLayout.addWidget(self.buttonBox)


        self.retranslateUi(NewProjectDialog)
        self.buttonBox.rejected.connect(NewProjectDialog.reject)

        QMetaObject.connectSlotsByName(NewProjectDialog)
    # setupUi

    def retranslateUi(self, NewProjectDialog):
        NewProjectDialog.setWindowTitle(QCoreApplication.translate("NewProjectDialog", u"Nytt projekt", None))
        self.labelName.setText(QCoreApplication.translate("NewProjectDialog", u"Projektnamn:", None))
        self.lineEditName.setPlaceholderText(QCoreApplication.translate("NewProjectDialog", u"Ange projektnamn", None))
        self.labelLocation.setText(QCoreApplication.translate("NewProjectDialog", u"Plats:", None))
        self.labelLocationPath.setText("")
        self.buttonBrowse.setText(QCoreApplication.translate("NewProjectDialog", u"V\u00e4lj mapp...", None))
        self.labelError.setText("")
        self.labelError.setStyleSheet(QCoreApplication.translate("NewProjectDialog", u"color: red;", None))
    # retranslateUi

