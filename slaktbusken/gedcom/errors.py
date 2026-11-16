"""Exceptions of the GEDCOM import.

Two kinds of problems exist during an import:

* ``RecoverableInputProblem``: a known, explicitly recognised problem in the
  input (an uninterpretable date, an unknown tag). The importer logs a
  warning, keeps the original text as unparsed data and continues.
* ``ImportAborted``: anything else. An unexpected exception, invalid internal
  state or a failed validation stops the whole import. The Import_Service
  drops the working copy, so nothing has changed.

Validates: Requirements 20.5, 20.23, 20.24, 20.26, 20.27
"""

from __future__ import annotations

import traceback
from typing import Optional

MSG_ABORT_PREFIX = "Importen avbröts och ingenting har ändrats."


class RecoverableInputProblem(Exception):
    """A known input problem that is logged as a warning and skipped.

    Raise it only from an explicit check of a recognised problem, and catch it
    at the one place that handles that problem.
    """


def format_abort_message(
    xref: Optional[str], label: Optional[str], exc: BaseException
) -> str:
    """Build the Swedish user message for an aborted import."""
    text = str(exc).strip() or type(exc).__name__
    if xref:
        who = f"{xref} ({label})" if label else xref
        return f"{MSG_ABORT_PREFIX} Fel i post {who}: {text}"
    if label:
        return f"{MSG_ABORT_PREFIX} Fel i {label}: {text}"
    return f"{MSG_ABORT_PREFIX} Ett oväntat fel inträffade ({text})."


class ImportAborted(Exception):
    """The import was stopped by an unexpected error.

    Attributes:
        message_sv: Swedish message for the user.
        xref: GEDCOM xref of the affected record, when known.
        label: Name or tag of the affected record, when known.
        phase: Import phase ("källor", "personer", ...), when known.
        traceback_text: Formatted traceback of the original exception.
    The original exception is ``__cause__``.
    """

    def __init__(
        self,
        message_sv: str,
        *,
        xref: Optional[str] = None,
        label: Optional[str] = None,
        phase: Optional[str] = None,
        traceback_text: str = "",
    ) -> None:
        super().__init__(message_sv)
        self.message_sv = message_sv
        self.xref = xref
        self.label = label
        self.phase = phase
        self.traceback_text = traceback_text

    @classmethod
    def from_exception(
        cls,
        exc: BaseException,
        *,
        xref: Optional[str] = None,
        label: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> "ImportAborted":
        """Wrap *exc*. The caller raises the result ``from exc``."""
        return cls(
            format_abort_message(xref, label, exc),
            xref=xref,
            label=label,
            phase=phase,
            traceback_text="".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ),
        )
