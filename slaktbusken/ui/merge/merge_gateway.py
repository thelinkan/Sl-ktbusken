"""Bridge between merge-related widgets and the application's merge actions.

Widgets such as the person editor section or the comparison window only know
the project data. Opening a comparison, marking candidates or opening the
register needs the application. ``Application`` registers a
:class:`MergeGateway` here and widgets reach it through
:func:`get_merge_gateway`. Without a gateway the buttons do nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol

from PySide6.QtCore import SignalInstance


class MergeGateway(Protocol):
    """What merge widgets may ask of the application."""

    @property
    def merge_changed(self) -> SignalInstance:
        """Signal emitted after candidates or merge history changed."""

    def open_comparison(self, person_1_id: str = "", person_2_id: str = "") -> None: ...

    def mark_candidates(self, person_1_id: str, person_2_id: str) -> None: ...

    def open_candidate(self, candidate_id: str) -> None: ...

    def open_register(self, person_id: Optional[str] = None) -> None: ...

    def open_history(self, person_id: Optional[str] = None) -> None: ...


@dataclass(frozen=True)
class MergeExecutionResult:
    """Outcome of an execution request (Swedish ``message`` on failure)."""

    success: bool
    message: str = ""


class MergeExecutor(Protocol):
    """The only thing the wizard needs from the merge engine.

    The wizard never imports the engine. ``Application`` registers an adapter
    around the engine with :func:`set_merge_executor`; tests pass a fake.
    """

    def execute(self, plan: Any) -> MergeExecutionResult:
        """Run the merge described by a ``MergePlan``."""
        ...


_gateway: Optional[MergeGateway] = None
_executor: Optional[MergeExecutor] = None


def set_merge_executor(executor: Optional[MergeExecutor]) -> None:
    """Register (or with None, remove) the engine adapter."""
    global _executor
    _executor = executor


def get_merge_executor() -> Optional[MergeExecutor]:
    """Return the registered engine adapter, or None."""
    return _executor


def set_merge_gateway(gateway: Optional[MergeGateway]) -> None:
    """Register (or with None, remove) the application's gateway."""
    global _gateway
    _gateway = gateway


def get_merge_gateway() -> Optional[MergeGateway]:
    """Return the registered gateway, or None."""
    return _gateway
