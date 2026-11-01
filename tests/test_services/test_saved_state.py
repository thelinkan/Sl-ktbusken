"""Tests for the revision counters and saved state of ProjectService.

Mandatory group c (failed merges); required, never skipped.
"""

from pathlib import Path

import pytest

from slaktbusken.services.project_service import ProjectService

pytestmark = pytest.mark.mandatory_integrity


@pytest.fixture
def service(tmp_path: Path) -> ProjectService:
    svc = ProjectService()
    svc.create_project("Test", tmp_path)
    return svc


@pytest.fixture
def notifications(service: ProjectService) -> list[int]:
    calls: list[int] = []
    service.add_merge_listener(lambda: calls.append(1))
    return calls


def test_dirty_true_increments_both_counters_and_notifies_once(
    service: ProjectService, notifications: list[int]
) -> None:
    rev, content = service.revision, service.content_revision
    service._dirty = True
    assert service.revision == rev + 1
    assert service.content_revision == content + 1
    assert len(notifications) == 1
    assert service.is_dirty


def test_dirty_false_increments_nothing(
    service: ProjectService, notifications: list[int]
) -> None:
    service._dirty = True
    notifications.clear()
    rev, content = service.revision, service.content_revision
    service._dirty = False
    assert service.revision == rev
    assert service.content_revision == content
    assert notifications == []


def test_save_increments_revision_only(
    service: ProjectService, notifications: list[int]
) -> None:
    service._dirty = True
    notifications.clear()
    rev, content = service.revision, service.content_revision
    service.save_project()
    assert service.revision == rev + 1
    assert service.content_revision == content
    assert service.clean_content_revision == content
    assert len(notifications) == 1
    assert service.is_saved_state()


def test_is_saved_state_false_for_mutation_that_forgot_flag(
    service: ProjectService,
) -> None:
    assert service.is_saved_state()
    # A mutation that raised the content revision but never set the flag.
    service._record_change(content=True, notify=False)
    assert not service.is_dirty
    assert not service.is_saved_state()


def test_adopt_committed_state_clears_dirty_and_counts_once(
    service: ProjectService, notifications: list[int]
) -> None:
    service._dirty = True
    notifications.clear()
    rev, content = service.revision, service.content_revision
    service.adopt_committed_state()
    assert not service.is_dirty
    assert service.revision == rev + 1
    assert service.content_revision == content + 1
    assert service.clean_content_revision == service.content_revision
    assert len(notifications) == 1
    assert service.is_saved_state()
