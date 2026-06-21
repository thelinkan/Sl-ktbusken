# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'settings_dialog.ui'
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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QCheckBox, QDialog,
    QDialogButtonBox, QFormLayout, QGroupBox, QLabel,
    QSizePolicy, QSpacerItem, QSpinBox, QVBoxLayout,
    QWidget)

class Ui_SettingsDialog(object):
    def setupUi(self, SettingsDialog):
        if not SettingsDialog.objectName():
            SettingsDialog.setObjectName(u"SettingsDialog")
        SettingsDialog.resize(480, 520)
        self.verticalLayout = QVBoxLayout(SettingsDialog)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.personBoxGroup = QGroupBox(SettingsDialog)
        self.personBoxGroup.setObjectName(u"personBoxGroup")
        self.personBoxLayout = QVBoxLayout(self.personBoxGroup)
        self.personBoxLayout.setObjectName(u"personBoxLayout")
        self.checkName = QCheckBox(self.personBoxGroup)
        self.checkName.setObjectName(u"checkName")

        self.personBoxLayout.addWidget(self.checkName)

        self.checkBirthDate = QCheckBox(self.personBoxGroup)
        self.checkBirthDate.setObjectName(u"checkBirthDate")

        self.personBoxLayout.addWidget(self.checkBirthDate)

        self.checkBirthPlace = QCheckBox(self.personBoxGroup)
        self.checkBirthPlace.setObjectName(u"checkBirthPlace")

        self.personBoxLayout.addWidget(self.checkBirthPlace)

        self.checkDeathDate = QCheckBox(self.personBoxGroup)
        self.checkDeathDate.setObjectName(u"checkDeathDate")

        self.personBoxLayout.addWidget(self.checkDeathDate)

        self.checkDeathPlace = QCheckBox(self.personBoxGroup)
        self.checkDeathPlace.setObjectName(u"checkDeathPlace")

        self.personBoxLayout.addWidget(self.checkDeathPlace)

        self.checkMarriageDate = QCheckBox(self.personBoxGroup)
        self.checkMarriageDate.setObjectName(u"checkMarriageDate")

        self.personBoxLayout.addWidget(self.checkMarriageDate)

        self.checkMarriagePlace = QCheckBox(self.personBoxGroup)
        self.checkMarriagePlace.setObjectName(u"checkMarriagePlace")

        self.personBoxLayout.addWidget(self.checkMarriagePlace)

        self.checkOccupation = QCheckBox(self.personBoxGroup)
        self.checkOccupation.setObjectName(u"checkOccupation")

        self.personBoxLayout.addWidget(self.checkOccupation)

        self.checkPhoto = QCheckBox(self.personBoxGroup)
        self.checkPhoto.setObjectName(u"checkPhoto")

        self.personBoxLayout.addWidget(self.checkPhoto)

        self.checkDnaInfo = QCheckBox(self.personBoxGroup)
        self.checkDnaInfo.setObjectName(u"checkDnaInfo")

        self.personBoxLayout.addWidget(self.checkDnaInfo)

        self.checkNotes = QCheckBox(self.personBoxGroup)
        self.checkNotes.setObjectName(u"checkNotes")

        self.personBoxLayout.addWidget(self.checkNotes)

        self.checkCauseOfDeath = QCheckBox(self.personBoxGroup)
        self.checkCauseOfDeath.setObjectName(u"checkCauseOfDeath")

        self.personBoxLayout.addWidget(self.checkCauseOfDeath)

        self.checkClusters = QCheckBox(self.personBoxGroup)
        self.checkClusters.setObjectName(u"checkClusters")

        self.personBoxLayout.addWidget(self.checkClusters)


        self.verticalLayout.addWidget(self.personBoxGroup)

        self.diagramDepthGroup = QGroupBox(SettingsDialog)
        self.diagramDepthGroup.setObjectName(u"diagramDepthGroup")
        self.depthFormLayout = QFormLayout(self.diagramDepthGroup)
        self.depthFormLayout.setObjectName(u"depthFormLayout")
        self.labelAncestryDepth = QLabel(self.diagramDepthGroup)
        self.labelAncestryDepth.setObjectName(u"labelAncestryDepth")

        self.depthFormLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.labelAncestryDepth)

        self.spinAncestryDepth = QSpinBox(self.diagramDepthGroup)
        self.spinAncestryDepth.setObjectName(u"spinAncestryDepth")
        self.spinAncestryDepth.setMinimum(1)
        self.spinAncestryDepth.setMaximum(10)
        self.spinAncestryDepth.setValue(4)

        self.depthFormLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.spinAncestryDepth)

        self.labelDescendantsDepth = QLabel(self.diagramDepthGroup)
        self.labelDescendantsDepth.setObjectName(u"labelDescendantsDepth")

        self.depthFormLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.labelDescendantsDepth)

        self.spinDescendantsDepth = QSpinBox(self.diagramDepthGroup)
        self.spinDescendantsDepth.setObjectName(u"spinDescendantsDepth")
        self.spinDescendantsDepth.setMinimum(1)
        self.spinDescendantsDepth.setMaximum(10)
        self.spinDescendantsDepth.setValue(4)

        self.depthFormLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.spinDescendantsDepth)


        self.verticalLayout.addWidget(self.diagramDepthGroup)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout.addItem(self.verticalSpacer)

        self.buttonBox = QDialogButtonBox(SettingsDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)

        self.verticalLayout.addWidget(self.buttonBox)


        self.retranslateUi(SettingsDialog)
        self.buttonBox.accepted.connect(SettingsDialog.accept)
        self.buttonBox.rejected.connect(SettingsDialog.reject)

        QMetaObject.connectSlotsByName(SettingsDialog)
    # setupUi

    def retranslateUi(self, SettingsDialog):
        SettingsDialog.setWindowTitle(QCoreApplication.translate("SettingsDialog", u"Inst\u00e4llningar", None))
        self.personBoxGroup.setTitle(QCoreApplication.translate("SettingsDialog", u"Personruta \u2013 synliga f\u00e4lt", None))
        self.checkName.setText(QCoreApplication.translate("SettingsDialog", u"Namn", None))
        self.checkBirthDate.setText(QCoreApplication.translate("SettingsDialog", u"F\u00f6delsedatum", None))
        self.checkBirthPlace.setText(QCoreApplication.translate("SettingsDialog", u"F\u00f6delseort", None))
        self.checkDeathDate.setText(QCoreApplication.translate("SettingsDialog", u"D\u00f6dsdatum", None))
        self.checkDeathPlace.setText(QCoreApplication.translate("SettingsDialog", u"D\u00f6dsort", None))
        self.checkMarriageDate.setText(QCoreApplication.translate("SettingsDialog", u"Vigselsdatum", None))
        self.checkMarriagePlace.setText(QCoreApplication.translate("SettingsDialog", u"Vigselort", None))
        self.checkOccupation.setText(QCoreApplication.translate("SettingsDialog", u"Yrke", None))
        self.checkPhoto.setText(QCoreApplication.translate("SettingsDialog", u"Profilfoto", None))
        self.checkDnaInfo.setText(QCoreApplication.translate("SettingsDialog", u"DNA-information", None))
        self.checkNotes.setText(QCoreApplication.translate("SettingsDialog", u"Anteckningar", None))
        self.checkCauseOfDeath.setText(QCoreApplication.translate("SettingsDialog", u"D\u00f6dsorsak", None))
        self.checkClusters.setText(QCoreApplication.translate("SettingsDialog", u"DNA-kluster", None))
        self.diagramDepthGroup.setTitle(QCoreApplication.translate("SettingsDialog", u"Diagramdjup", None))
        self.labelAncestryDepth.setText(QCoreApplication.translate("SettingsDialog", u"Antal generationer upp\u00e5t (anor):", None))
        self.labelDescendantsDepth.setText(QCoreApplication.translate("SettingsDialog", u"Antal generationer ned\u00e5t (\u00e4ttlingar):", None))
    # retranslateUi

