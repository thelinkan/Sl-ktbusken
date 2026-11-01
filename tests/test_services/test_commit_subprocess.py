"""Real-process crash tests of the merge commit sequence (task 13.15).

Mandatory group d (crash recovery). A child Python process runs the real
``MergeEngine`` against a real project directory with a filesystem wrapper
that calls ``os._exit(42)`` at a chosen operation number (no ``finally``, no
``atexit``, no flushing). The parent then checks the disk state left behind and
reopens the project with a fresh ``ProjectService`` (startup recovery).

Checks (the same all-or-nothing checks as the crash matrix):
  * the child really died with exit code 42,
  * after recovery the project file and ``persons.json`` are both OLD or both
    NEW, never mixed (checked by checksum and content),
  * a recovery message exists exactly when a journal existed before open,
  * no journal, temp file, backup directory or lock remains,
  * no orphaned mapping or alias,
  * a second open changes nothing (recovery is idempotent).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from slaktbusken.model.person import Name, Person
from slaktbusken.persistence import translation_io
from slaktbusken.persistence.file_io import FilePersistence
from slaktbusken.persistence.translation_io import PersonMapping
from slaktbusken.services.commit.preflight import journal_path_for
from slaktbusken.services.project_service import ProjectService

pytestmark = pytest.mark.mandatory_integrity

REPO_ROOT = Path(__file__).resolve().parents[2]
EXIT_CODE = 42

# Child program: argv = project file, mode ("count" | "run" | "before" | "after" |
# "partial"), operation number. Prints a JSON line for "count" and "run".
_CHILD = textwrap.dedent(
    """
    import json, os, sys
    from pathlib import Path

    from slaktbusken.persistence import translation_io
    from slaktbusken.services.merge_engine import MergeEngine
    from slaktbusken.services.merge_planner import MergeDecisions, build_plan
    from slaktbusken.services.project_service import ProjectService
    from tests.helpers.fault_fs import CountingFs

    project, mode, n = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])


    class ExitFs(CountingFs):
        def _pre(self, op):
            if op.index != n:
                return
            if mode == "before":
                os._exit(42)
            if mode == "partial":
                if op.name == "write_file_durable":
                    path, data = op.args
                elif op.name == "copy_file_durable":
                    src, path = op.args
                    data = self.inner.read_bytes(src)
                else:
                    os._exit(42)
                with open(path, "wb") as fh:
                    fh.write(data[: len(data) // 2])
                os._exit(42)

        def _post(self, op, result):
            if op.index == n and mode == "after":
                os._exit(42)


    svc = ProjectService()
    svc.open_project(project)
    translation = translation_io.read_all(project.parent / "translation")
    decisions = MergeDecisions(
        "person_1", "person_2", survivor_id="person_1", survivor_confirmed=True
    )
    plan = build_plan(svc.data, translation, decisions, svc.content_revision)
    fs = ExitFs()
    outcome = MergeEngine(svc, None, fs=fs).execute(plan)
    print(json.dumps({"success": outcome.success, "message": outcome.message,
                      "ops": [[op.index, op.name] for op in fs.ops]}))
    """
)


def _person(pid: str, given: str) -> Person:
    return Person(id=pid, sex="F", names=[Name("birth", given, "Berg")])


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*")}


def _run_child(project: Path, mode: str, n: int) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["QT_QPA_PLATFORM"] = "offscreen"
    return subprocess.run(
        [sys.executable, "-c", _CHILD, str(project), mode, str(n)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture
def base(tmp_path: Path) -> tuple[Path, Path]:
    """A saved two-person project with a mapping for the merged-away person.

    Returns (root directory, project file relative to the root).
    """
    root = tmp_path / "base"
    root.mkdir()
    svc = ProjectService()
    svc.create_project("Test", root)
    svc.data.persons.extend([_person("person_1", "Anna"), _person("person_2", "Anna")])
    translation_io.write_persons(
        [PersonMapping("@I2@", "person_2", "fp2")],
        [],
        svc.project_path.parent / "translation" / "persons.json",
    )
    svc._dirty = True
    svc.save_project()
    return root, svc.project_path.relative_to(root)


def _copy_case(base_root: Path, rel_project: Path, dest: Path) -> Path:
    shutil.copytree(base_root, dest)
    return dest / rel_project


def _representative_points(ops: list[list]) -> list[tuple[str, int]]:
    """(phase, operation number) pairs covering every kind of mutating step.

    * ``before`` for every mutating operation (so the disk shows the state just
      before it), which includes both replaces (persons.json, then project file),
    * ``after`` for every replace, remove and rmtree (the points between the two
      replaces and around journal removal),
    * ``partial`` for every durable write (torn temp, backup, manifest, journal).
    """
    mutating = {
        "write_file_durable",
        "copy_file_durable",
        "replace",
        "remove",
        "rmtree",
        "create_exclusive",
        "mkdir",
    }
    points: list[tuple[str, int]] = []
    for index, name in ops:
        if name in mutating:
            points.append(("before", index))
        if name in ("replace", "remove", "rmtree", "create_exclusive"):
            points.append(("after", index))
        if name in ("write_file_durable", "copy_file_durable"):
            points.append(("partial", index))
    return points


def _read_state(project: Path) -> tuple[str, str]:
    return _digest(project), _digest(project.parent / "translation" / "persons.json")


def test_os_exit_at_representative_points(base: tuple[Path, Path], tmp_path: Path) -> None:
    base_root, rel_project = base
    original_tree = _tree(base_root)
    old_project = base_root / rel_project
    old_state = _read_state(old_project)

    # Dry run (also the reference for the NEW state): count and name every operation.
    dry = _copy_case(base_root, rel_project, tmp_path / "dry")
    result = _run_child(dry, "count", 0)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["success"], report["message"]
    ops = report["ops"]
    assert len(ops) >= 10, ops
    new_state = _read_state(dry)
    assert new_state[0] != old_state[0] and new_state[1] != old_state[1]

    points = _representative_points(ops)
    kinds = {name for _, name in ops}
    assert {"replace", "write_file_durable"} <= kinds
    assert sum(1 for _, i in points if ops[i - 1][1] == "replace") >= 2

    def one(item: tuple[int, tuple[str, int]]) -> tuple[str, int, Path, int, str]:
        case_no, (phase, n) = item
        project = _copy_case(base_root, rel_project, tmp_path / f"case_{case_no}")
        proc = _run_child(project, phase, n)
        return phase, n, project, proc.returncode, proc.stderr

    with ThreadPoolExecutor(max_workers=4) as pool:
        runs = list(pool.map(one, enumerate(points)))

    failures: list[str] = []
    saw_old = saw_new = saw_journal = False
    for phase, n, project, code, stderr in runs:
        label = f"{phase}@{n} ({ops[n - 1][1]})"
        if code != EXIT_CODE:
            failures.append(f"{label}: child exit code {code}, stderr: {stderr[-300:]}")
            continue

        journal_existed = journal_path_for(project).exists()
        saw_journal |= journal_existed

        service = ProjectService()
        try:
            service.open_project(project)
        except Exception as exc:  # recovery must never refuse after our own crash
            failures.append(f"{label}: open_project raised {type(exc).__name__}: {exc}")
            continue

        state = _read_state(project)
        is_old = state[0] == old_state[0] and state[1] == old_state[1]
        is_new = state[0] != old_state[0] and state[1] != old_state[1]
        translation = translation_io.read_all(project.parent / "translation")
        persons = [p.id for p in FilePersistence.load(project).persons]

        if is_old:
            saw_old = True
            if persons != ["person_1", "person_2"] or [m.gedcom_id for m in translation.persons] != ["@I2@"]:
                failures.append(f"{label}: OLD state has wrong content {persons}")
            if translation.person_aliases:
                failures.append(f"{label}: OLD state has an alias")
        elif is_new:
            saw_new = True
            if persons != ["person_1"] or translation.persons:
                failures.append(f"{label}: NEW state has wrong content {persons}")
            if [(a.gedcom_id, a.person_id) for a in translation.person_aliases] != [("@I2@", "person_1")]:
                failures.append(f"{label}: NEW state lacks the alias")
        else:
            failures.append(f"{label}: mixed state (project/persons.json differ in old/new)")

        if bool(service.last_recovery_message) != journal_existed:
            failures.append(
                f"{label}: recovery message {service.last_recovery_message!r} "
                f"but journal existed={journal_existed}"
            )
        leftovers = _tree(project.parents[len(rel_project.parents) - 1]) ^ original_tree
        if leftovers:
            failures.append(f"{label}: leftover/changed artifacts {sorted(leftovers)}")

        # Idempotent: a second open changes nothing.
        before_second = _read_state(project)
        again = ProjectService()
        again.open_project(project)
        if _read_state(project) != before_second or again.last_recovery_message:
            failures.append(f"{label}: second open changed state or reported a recovery")

    assert not failures, "\n".join(failures)
    # The chosen points must exercise both sides of the commit point and the journal.
    assert saw_old and saw_new and saw_journal
