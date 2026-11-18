"""Qt signal holder for merge change notifications."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class MergeSignals(QObject):
    """Emits ``changed`` after merge candidates or merge history changed."""

    changed = Signal()
