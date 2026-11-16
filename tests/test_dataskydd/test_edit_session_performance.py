"""Edit-session cost on a 10,000-person project (Requirements 1.12, 1.13).

# ---------------------------------------------------------------------------
# MEASURED FIGURES (task 1.2, scripts/measure_edit_session.py).
# Project: 10,000 persons, 25,000 events, 4,000 families, 2,000 places,
#          800 sources (tests/helpers/large_project.py make_project).
# Machine: Windows 10 (10.0.26200), Python 3.11.3, AMD64 Family 25 Model 80
#          (AuthenticAMD), two runs.
# Snapshot (full, deepcopy per entity): 2.703 s and 2.527 s
# Restore (in place, 200 persons edited, 100 events removed): 0.100 s and 0.096 s
# Total: 2.803 s and 2.622 s  -> EXCEEDS the 1.5 s goal (reported; the
# snapshot scope is NOT reduced, Requirements 1.12 and 1.13).
# ---------------------------------------------------------------------------

The 1.5 s goal is reported with a ``UserWarning``; the test fails only above 10 s.
"""

from __future__ import annotations

import time
import warnings

import pytest

from slaktbusken.services.project_service import ProjectService
from tests.helpers.large_project import make_project

pytestmark = pytest.mark.mandatory_integrity

GOAL_SECONDS = 1.5
FAIL_SECONDS = 10.0


def test_edit_session_10k_persons_reports_time_within_bound():
    data = make_project(10_000)
    service = ProjectService()
    service._project_data = data

    t0 = time.perf_counter()
    session = service.begin_edit_session("Personredigerare")
    t1 = time.perf_counter()
    for person in data.persons[:200]:
        person.notes = "ändrad"
    del data.events[:100]
    t2 = time.perf_counter()
    session.rollback()
    t3 = time.perf_counter()

    snapshot, restore = t1 - t0, t3 - t2
    total = snapshot + restore
    print(f"edit session snapshot: {snapshot:.3f} s, restore: {restore:.3f} s, "
          f"total: {total:.3f} s (goal {GOAL_SECONDS} s, limit {FAIL_SECONDS} s)")

    assert len(data.events) == 25_000 and data.persons[0].notes != "ändrad"
    if total > GOAL_SECONDS:
        warnings.warn(
            f"Edit session snapshot and restore took {total:.2f} s on 10,000 "
            f"persons, above the {GOAL_SECONDS} s goal.",
            UserWarning,
            stacklevel=1,
        )
    assert total < FAIL_SECONDS
