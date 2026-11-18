"""ProjectService integration of startup recovery and the journal save guard (task 13.6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from slaktbusken.services.commit.preflight import journal_path_for
from slaktbusken.services.commit.recovery import RecoveryRefusedError
from slaktbusken.services.project_service import (
    MERGE_UNFINISHED_MESSAGE,
    MergeInProgressError,
    MergeNotFinishedError,
    ProjectService,
)


def _make_project(tmp_path: Path, name: str) -> Path:
    service = ProjectService()
    service.create_project(name, tmp_path)
    return tmp_path / name / f"{name}.json.gz"


def test_open_without_journal_has_no_recovery_message(tmp_path):
    path = _make_project(tmp_path, "A")
    service = ProjectService()
    service.open_project(path)
    assert service.last_recovery_message == ""
    assert not service.is_merge_journal_pending()
    service.save_project()  # ordinary save still works


def test_save_refused_while_journal_exists(tmp_path):
    path = _make_project(tmp_path, "A")
    service = ProjectService()
    service.open_project(path)
    journal_path_for(path).write_text("{}", encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(MergeNotFinishedError, match="Starta om Släktbusken") as info:
        service.save_project()
    assert str(info.value) == MERGE_UNFINISHED_MESSAGE
    assert isinstance(info.value, MergeInProgressError)
    assert path.read_bytes() == before


def test_refusal_keeps_previous_project_and_blocks_save(tmp_path):
    good = _make_project(tmp_path, "Good")
    bad = _make_project(tmp_path, "Bad")
    journal = journal_path_for(bad)
    journal.write_text("not json", encoding="utf-8")
    bad_bytes = bad.read_bytes()

    service = ProjectService()
    service.open_project(good)
    previous = service.data

    with pytest.raises(RecoveryRefusedError):
        service.open_project(bad)

    assert service.data is previous
    assert service.project_path == good
    assert journal.read_text(encoding="utf-8") == "not json"  # refusal is read-only
    assert bad.read_bytes() == bad_bytes
    service.save_project()  # the previous project is unaffected


def test_refusal_then_save_of_same_project_is_refused(tmp_path):
    path = _make_project(tmp_path, "A")
    service = ProjectService()
    service.open_project(path)
    journal_path_for(path).write_text("not json", encoding="utf-8")
    with pytest.raises(RecoveryRefusedError):
        service.open_project(path)
    with pytest.raises(MergeNotFinishedError):
        service.save_project()
