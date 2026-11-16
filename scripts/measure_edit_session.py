# ---------------------------------------------------------------------------
# MEASURED FIGURES (task 1.2). Task 7.3 copies this block into
# tests/test_dataskydd/test_edit_session_performance.py.
# Project: 10,000 persons, 25,000 events, 4,000 families, 2,000 places,
#          800 sources (tests/helpers/large_project.py make_project).
# Machine: Windows 10 (10.0.26200), Python 3.11.3, AMD64 Family 25 Model 80
#          (AuthenticAMD), two runs.
# Snapshot (full, deepcopy per entity): 2.703 s and 2.527 s
# Restore (in place, 200 persons edited, 100 events removed): 0.100 s and 0.096 s
# Total: 2.803 s and 2.622 s  -> EXCEEDS the 1.5 s goal (reported; the
# snapshot scope is NOT reduced, Requirements 1.12 and 1.13).
# ---------------------------------------------------------------------------
"""Time the full edit-session snapshot and in-place restore on 10,000 persons.

Run: python scripts/measure_edit_session.py
Snapshot scope is never reduced to meet the 1.5 s target (Requirements 1.12, 1.13).
"""

from __future__ import annotations

import copy
import dataclasses
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from slaktbusken.model.project import ProjectData  # noqa: E402
from tests.helpers.large_project import make_project  # noqa: E402

EXCLUDED = {
    "format", "version", "merge_load_findings",
    "unreadable_merge_items", "id_high_water_marks",
}


def take_snapshot(data: ProjectData):
    lists: dict[str, list] = {}
    for f in dataclasses.fields(ProjectData):
        if f.name in EXCLUDED or f.name in ("project", "connection_overrides"):
            continue
        lists[f.name] = [(e, copy.deepcopy(e)) for e in getattr(data, f.name)]
    return (lists, copy.deepcopy(data.project), copy.deepcopy(data.connection_overrides))


def restore(data: ProjectData, snap) -> None:
    lists, project, overrides = snap
    for name, pairs in lists.items():
        lst = getattr(data, name)
        lst[:] = [e for e, _ in pairs]
        for entity, saved in pairs:
            if entity != saved:
                entity.__dict__.clear()
                entity.__dict__.update(saved.__dict__)
    data.project.__dict__.clear()
    data.project.__dict__.update(project.__dict__)
    data.connection_overrides.clear()
    data.connection_overrides.update(overrides)


def main() -> None:
    data = make_project(10_000)
    print(f"persons={len(data.persons)} events={len(data.events)} "
          f"families={len(data.families)} places={len(data.places)} "
          f"sources={len(data.sources)}")
    t0 = time.perf_counter()
    snap = take_snapshot(data)
    t1 = time.perf_counter()
    # Mutate a little so the restore does real work.
    for p in data.persons[:200]:
        p.notes = "ändrad"
    del data.events[:100]
    t2 = time.perf_counter()
    restore(data, snap)
    t3 = time.perf_counter()
    snap_s, rest_s = t1 - t0, t3 - t2
    print(f"snapshot: {snap_s:.3f} s")
    print(f"restore:  {rest_s:.3f} s")
    print(f"total:    {snap_s + rest_s:.3f} s (target 1.5 s)")
    if snap_s + rest_s > 1.5:
        print("WARNING: total exceeds 1.5 s; reported, scope not reduced.")
    print(f"python {platform.python_version()} on {platform.platform()} "
          f"({platform.processor()})")


if __name__ == "__main__":
    main()
