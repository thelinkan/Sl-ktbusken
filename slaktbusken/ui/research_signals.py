"""Qt signal carrier for research change notifications.

``Application`` is a plain Python class and cannot own a Qt ``Signal``, and
``ProjectService`` must stay free of Qt. This small ``QObject`` bridges the two:
``ProjectService.notify_research_changed`` calls its ``changed.emit``, and every
open view that shows research-derived content connects its refresh slot to
``changed``.

Because ``changed`` is a real Qt signal, a view that connects a ``QObject``
method to it is disconnected automatically when that view is destroyed, so
closing an editor needs no manual deregistration.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class ResearchSignals(QObject):
    """Carries the signal emitted after research data changes.

    Signals:
        changed: Emitted after a committed create, update or delete of a
            research case, hypothesis, comment or action, and after a merge or
            deletion that rewires or leaves behind research references.
    """

    changed = Signal()
