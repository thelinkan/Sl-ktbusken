"""Performance benchmarks for person comparison and merge (Requirement 32).

Run with::

    pytest tests/benchmarks/test_merge_performance.py -m slow -s

Limits (upper limits fixed by the requirements, gated on the *maximum* of the
measured runs, never loosened here):

* candidate index: below 1 s at 20,000 persons / 2,000 candidates;
* comparison family views: below 2 s at the same size.

Recorded but not gated: the design targets (index under 50 ms, comparison
refresh under 600 ms, person-list indicators under 20 ms extra) and the
Merge_Plan build time, which only has a 10 s regression guard on the median.

Every run writes ``ENVIRONMENT.md`` and ``benchmark-results.json`` to
``docs/benchmarks`` (override with the environment variable
``SBK_BENCHMARK_OUT``). The benchmarks never write to the generated project.
"""

from __future__ import annotations

import gc
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.services.candidate_index import CandidateIndex
from slaktbusken.services.merge_planner import MergeDecisions, build_plan
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge.person_comparison_window import PersonComparisonWindow
from tests.benchmarks.synthetic_project import (
    DEFAULT_CANDIDATES,
    DEFAULT_PERSONS,
    DEFAULT_SEED,
    generate_project,
)

pytestmark = pytest.mark.slow

WARMUP_RUNS = 3
INDEX_RUNS = 30
COMPARISON_RUNS = 10
PLAN_RUNS = 5

INDEX_LIMIT_S = 1.0
COMPARISON_LIMIT_S = 2.0
PLAN_GUARD_S = 10.0

INDEX_TARGET_S = 0.050
COMPARISON_TARGET_S = 0.600
LIST_INDICATOR_TARGET_S = 0.020

_REPO = Path(__file__).resolve().parents[2]
_RESULTS: dict = {"metrics": {}}


# -- statistics and timing ---------------------------------------------------


def _percentile_nearest_rank(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100.0 * len(ordered)))
    return ordered[rank - 1]


def _summarise(samples: list[float]) -> dict:
    return {
        "median_s": statistics.median(samples),
        "p95_s": _percentile_nearest_rank(samples, 95),
        "max_s": max(samples),
        "min_s": min(samples),
        "runs": len(samples),
        "samples_s": samples,
    }


def _measure(fn, runs: int, warmups: int = WARMUP_RUNS, before=None) -> list[float]:
    """Run ``fn(i)`` ``warmups`` times (discarded) then ``runs`` times, timed."""
    for i in range(warmups):
        if before:
            before(i)
        fn(i)
    samples = []
    for i in range(runs):
        if before:
            before(warmups + i)
        gc.collect()
        start = time.perf_counter_ns()
        fn(warmups + i)
        samples.append((time.perf_counter_ns() - start) / 1e9)
    return samples


# -- environment record ------------------------------------------------------


def _powershell(command: str) -> str:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=30, check=False,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _environment() -> dict:
    import PySide6
    from PySide6 import QtCore
    from PySide6.QtGui import QGuiApplication

    cpu = platform.processor()
    ram_gb = None
    power_plan = "not recorded (not Windows)"
    if sys.platform == "win32":
        name = _powershell("(Get-CimInstance Win32_Processor | Select-Object -First 1).Name")
        cores = _powershell("(Get-CimInstance Win32_Processor | Select-Object -First 1).NumberOfCores")
        threads = _powershell(
            "(Get-CimInstance Win32_Processor | Select-Object -First 1).NumberOfLogicalProcessors"
        )
        if name:
            cpu = f"{name} ({cores} cores, {threads} threads)"
        mem = _powershell("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory")
        if mem.isdigit():
            ram_gb = round(int(mem) / 1024**3, 1)
        try:
            plan = subprocess.run(
                ["powercfg", "/getactivescheme"], capture_output=True, text=True, timeout=30
            )
            power_plan = plan.stdout.strip() or "unknown"
        except (OSError, subprocess.SubprocessError):
            power_plan = "unknown"
    app = QGuiApplication.instance()
    return {
        "cpu": cpu,
        "ram_gb": ram_gb,
        "os": platform.platform(),
        "python": sys.version.replace("\n", " "),
        "pyside6": PySide6.__version__,
        "qt": QtCore.qVersion(),
        "qt_platform": app.platformName() if app else os.environ.get("QT_QPA_PLATFORM", ""),
        "power_plan": power_plan,
        "seed": DEFAULT_SEED,
        "persons": DEFAULT_PERSONS,
        "candidates": DEFAULT_CANDIDATES,
        "warmup_runs": WARMUP_RUNS,
        "measured_runs": {
            "candidate_index": INDEX_RUNS,
            "comparison_views": COMPARISON_RUNS,
            "plan_build": PLAN_RUNS,
        },
        "statistics": "median, p95 (nearest rank), maximum; gate on the maximum",
    }


def _fmt_ms(seconds: float) -> str:
    return f"{seconds * 1000:.1f} ms"


def _write_outputs() -> None:
    out_dir = Path(os.environ.get("SBK_BENCHMARK_OUT", _REPO / "docs" / "benchmarks"))
    out_dir.mkdir(parents=True, exist_ok=True)
    env = _RESULTS.setdefault("environment", _environment())
    payload = {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "environment": env,
        "metrics": _RESULTS["metrics"],
    }
    (out_dir / "benchmark-results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    lines = [
        "# Benchmark environment",
        "",
        "Written by `tests/benchmarks/test_merge_performance.py` (requirement 32.11).",
        f"Recorded at {payload['recorded_at']}.",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| CPU | {env['cpu']} |",
        f"| RAM | {env['ram_gb']} GB |" if env["ram_gb"] else "| RAM | not recorded |",
        f"| Operating system | {env['os']} |",
        f"| Python | {env['python']} |",
        f"| PySide6 / Qt | {env['pyside6']} / {env['qt']} |",
        f"| Qt platform | {env['qt_platform']} |",
        f"| Power plan | {env['power_plan']} |",
        f"| Seed and sizes | {env['seed']}; {env['persons']:,} persons; {env['candidates']:,} candidates |",
        f"| Runs | warm-up {env['warmup_runs']} (discarded); measured "
        f"{INDEX_RUNS} / {COMPARISON_RUNS} / {PLAN_RUNS} |",
        f"| Figures reported | {env['statistics']} |",
        "",
        "## Results",
        "",
        "| Metric | Median | p95 | Max | Limit or target | Kind |",
        "|--------|--------|-----|-----|-----------------|------|",
    ]
    for key, m in _RESULTS["metrics"].items():
        if "median_s" not in m:
            continue
        limit = m.get("limit_s")
        target = m.get("target_s")
        if limit is not None:
            bound, kind = f"< {limit * 1000:.0f} ms (on max)", "gated"
        elif target is not None:
            bound, kind = f"< {target * 1000:.0f} ms", "target, not gated"
        else:
            bound, kind = "-", "recorded"
        lines.append(
            f"| {m['label']} | {_fmt_ms(m['median_s'])} | {_fmt_ms(m['p95_s'])} | "
            f"{_fmt_ms(m['max_s'])} | {bound} | {kind} |"
        )
    (out_dir / "ENVIRONMENT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _record(key: str, label: str, samples: list[float], **extra) -> dict:
    entry = {"label": label, **_summarise(samples), **extra}
    _RESULTS["metrics"][key] = entry
    _write_outputs()
    return entry


def _gate(entry: dict, limit_s: float, what: str) -> None:
    """Fail with the measured duration and the limit (32.8)."""
    assert entry["max_s"] < limit_s, (
        f"{what}: uppmätt längsta tid {entry['max_s']:.3f} s överskrider gränsen "
        f"{limit_s:.3f} s (median {entry['median_s']:.3f} s, p95 {entry['p95_s']:.3f} s)"
    )


# -- fixtures ------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def project():
    start = time.perf_counter()
    data = generate_project(DEFAULT_SEED, DEFAULT_PERSONS, DEFAULT_CANDIDATES)
    _RESULTS["generation_s"] = time.perf_counter() - start
    assert len(data.persons) == DEFAULT_PERSONS
    assert len(data.merge_candidates) == DEFAULT_CANDIDATES
    return data


def _busiest_pairs(data, count: int) -> list[tuple[str, str]]:
    """Candidate pairs with the largest family neighbourhoods (worst case views)."""
    degree: dict[str, int] = {}
    for family in data.families:
        size = len(family.children) + len(family.partners)
        for pid in [p.person_id for p in family.partners] + list(family.children):
            degree[pid] = degree.get(pid, 0) + size
    ranked = sorted(
        (c for c in data.merge_candidates if c.person_1_id != c.person_2_id),
        key=lambda c: (-(degree.get(c.person_1_id, 0) + degree.get(c.person_2_id, 0)), c.id),
    )
    return [(c.person_1_id, c.person_2_id) for c in ranked[:count]]


# -- benchmarks ----------------------------------------------------------------


def test_candidate_index_below_one_second(project):
    """Index build plus the per-person relations and colour for every involved person."""
    involved = sorted({p for c in project.merge_candidates for p in (c.person_1_id, c.person_2_id)})

    def build_only(_i):
        CandidateIndex.build(project)

    def build_and_colours(_i):
        index = CandidateIndex.build(project)
        for pid in involved:
            index.colour(pid)

    build_samples = _measure(build_only, INDEX_RUNS)
    _record(
        "candidate_index_build", "Candidate index build", build_samples,
        target_s=INDEX_TARGET_S,
    )
    samples = _measure(build_and_colours, INDEX_RUNS)
    entry = _record(
        "candidate_index", "Candidate index build + colour of all involved persons",
        samples, limit_s=INDEX_LIMIT_S,
    )
    _gate(entry, INDEX_LIMIT_S, "Kandidatindex")


def test_person_list_indicator_cost_recorded(project):
    """Informational: colour lookup for every person in the list, no gate."""
    persons = [p.id for p in project.persons]

    def lookup_all(_i):
        index = CandidateIndex.build(project)
        for pid in persons:
            index.colour(pid)

    samples = _measure(lookup_all, INDEX_RUNS)
    _record(
        "person_list_indicators",
        "Person list indicators (index + colour of all 20,000 persons; upper bound of the extra cost)",
        samples, target_s=LIST_INDICATOR_TARGET_S,
    )


def test_comparison_family_views_below_two_seconds(project, qapp):
    """``set_slot`` for both slots through refresh of both views, table, markers and a grab."""
    pairs = _busiest_pairs(project, WARMUP_RUNS + COMPARISON_RUNS)
    assert len(pairs) == WARMUP_RUNS + COMPARISON_RUNS
    service = ProjectService()
    service._project_data = project
    window = PersonComparisonWindow(service)
    window.resize(1400, 800)
    window.show()
    qapp.processEvents()

    def reset(_i):
        window.clear_slot(0)
        window.clear_slot(1)
        qapp.processEvents()

    def run(i):
        a, b = pairs[i]
        window.session.set_slot(0, a)
        window.session.set_slot(1, b)
        window.refresh()
        for view in window.family_views:
            view.graphics_view.grab()

    try:
        samples = _measure(run, COMPARISON_RUNS, before=reset)
        boxes = sum(len(v.person_boxes()) for v in window.family_views)
    finally:
        window.close()
        service._project_data = None
    entry = _record(
        "comparison_family_views", "Comparison views (set_slot, refresh of both views and table, grab)",
        samples, limit_s=COMPARISON_LIMIT_S, target_s=COMPARISON_TARGET_S,
        boxes_in_last_run=boxes,
    )
    _gate(entry, COMPARISON_LIMIT_S, "Jämförelsevyerna")


def test_plan_build_regression_guard(project):
    """Merge_Plan build time: recorded, with a 10 s guard on the median only."""
    pairs = _busiest_pairs(project, WARMUP_RUNS + PLAN_RUNS)

    def run(i):
        a, b = pairs[i]
        build_plan(project, None, MergeDecisions(a, b, survivor_id=a, survivor_confirmed=True))

    samples = _measure(run, PLAN_RUNS)
    entry = _record("plan_build", "Merge_Plan build (regression guard on median)", samples,
                    guard_median_s=PLAN_GUARD_S)
    assert entry["median_s"] < PLAN_GUARD_S, (
        f"Sammanslagningsplan: uppmätt median {entry['median_s']:.3f} s överskrider "
        f"regressionsgränsen {PLAN_GUARD_S:.1f} s"
    )
