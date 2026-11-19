"""The abort log: an aborted import leaves a file with every finding.

Regression: a validation abort only reached the Python logger, so the user had
neither a log folder nor the full list of findings (the message box names five).
"""

from __future__ import annotations

from pathlib import Path

from slaktbusken.app import _write_abort_log
from slaktbusken.gedcom.errors import ImportAborted


def _aborted() -> ImportAborted:
    details = "\n".join(f"Place place_{i}: fel {i}" for i in range(1, 42))
    return ImportAborted(
        "Importen avbröts och ingenting har ändrats. 41 fel, t.ex. Place place_1: fel 1",
        phase="validation",
        traceback_text=f"Nya valideringsfel (41):\n{details}",
    )


def test_the_abort_log_holds_every_finding(tmp_path: Path) -> None:
    log = _write_abort_log(_aborted(), tmp_path / "in.ged", tmp_path)

    assert log is not None and log.parent == tmp_path / "log"
    text = log.read_text(encoding="utf-8")
    assert "IMPORTEN AVBRÖTS" in text and "Fas: validation" in text
    assert "Fil: in.ged" in text
    assert "Place place_41: fel 41" in text  # beyond the five named in the message


def test_a_second_abort_does_not_overwrite_the_first(tmp_path: Path) -> None:
    first = _write_abort_log(_aborted(), tmp_path / "in.ged", tmp_path)
    assert first is not None
    first.write_text("keep", encoding="utf-8")
    import time

    time.sleep(1.1)
    second = _write_abort_log(_aborted(), tmp_path / "in.ged", tmp_path)
    assert second is not None and second != first
    assert first.read_text(encoding="utf-8") == "keep"


def test_an_unwritable_log_folder_does_not_hide_the_abort(tmp_path: Path) -> None:
    blocker = tmp_path / "log"
    blocker.write_text("a file where the folder should be", encoding="utf-8")
    assert _write_abort_log(_aborted(), tmp_path / "in.ged", tmp_path) is None