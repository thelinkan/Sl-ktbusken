"""Kör de obligatoriska testgrupperna (Requirement 35) med ett enda kommando.

    python scripts/run_mandatory_tests.py

Skriptet sätter ``QT_QPA_PLATFORM=offscreen`` och ``SBK_MANDATORY_STRICT=1``, kör
``tests/test_meta`` och alla moduler i ``MANDATORY_GROUPS`` (utan ``-k``/``-m``),
läser JUnit-XML och kontrollerar per grupp att alla obligatoriska tester finns,
körts och gått igenom utan skip, xfail eller bortval. På win32 körs även
``tests/test_services/test_commit_preflight.py`` och ett hoppat ``windows_only``-test
räknas som fel.

Utgångskoder: 0 = allt grönt, 1 = fel eller hoppade tester, 3 = obligatoriska
tester eller moduler saknas (samma kod som strikt läge i conftest använder).
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.mandatory_groups import (  # noqa: E402
    GUARD_MODULE,
    MANDATORY_GROUPS,
    WINDOWS_ONLY_MODULE,
    WINDOWS_ONLY_TESTS,
)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_MISSING = 3

META_DIR = "tests/test_meta"


def _dotted(module: str) -> str:
    return module[:-3].replace("/", ".") if module.endswith(".py") else module.replace("/", ".")


def _base_name(name: str) -> str:
    """Testnamn utan parametrisering (``test_x[1]`` -> ``test_x``)."""
    return name.split("[", 1)[0]


def _parse_junit(path: Path) -> dict[str, list[tuple[str, str]]]:
    """Returnerar {modulsökväg: [(testnamn, utfall)]}; utfall är passed/failed/skipped."""
    by_module: dict[str, list[tuple[str, str]]] = defaultdict(list)
    if not path.exists():
        return by_module
    modules = {m for g in MANDATORY_GROUPS for m in g.modules}
    modules.update({GUARD_MODULE, WINDOWS_ONLY_MODULE})
    dotted = {_dotted(m): m for m in modules}
    for case in ET.parse(path).getroot().iter("testcase"):
        classname = case.get("classname", "")
        module = next(
            (
                dotted[d]
                for d in sorted(dotted, key=len, reverse=True)
                if classname == d or classname.startswith(d + ".")
            ),
            None,
        )
        if module is None:
            continue
        if case.find("failure") is not None or case.find("error") is not None:
            outcome = "failed"
        elif case.find("skipped") is not None:
            outcome = "skipped"
        else:
            outcome = "passed"
        by_module[module].append((_base_name(case.get("name", "")), outcome))
    return by_module


def _has(results: list[tuple[str, str]], pattern: str) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for name, _ in results)


def _evaluate(
    results: dict[str, list[tuple[str, str]]],
    missing_modules: set[str],
) -> tuple[bool, bool]:
    """Skriver en rad per grupp. Returnerar (har_fel, saknas)."""
    failed = False
    missing = False
    for group in MANDATORY_GROUPS:
        problems: list[str] = []
        absent = [
            e for e in group.required_tests
            if e.partition("::")[0] in missing_modules
            or not _has(results.get(e.partition("::")[0], []), e.partition("::")[2])
        ]
        group_cases = [c for m in group.modules for c in results.get(m, [])]
        if absent:
            missing = True
            problems.append(f"{len(absent)} obligatoriska tester saknas ({', '.join(absent[:3])}"
                            f"{', ...' if len(absent) > 3 else ''})")
        if len(group_cases) < len(group.required_tests):
            problems.append(
                f"endast {len(group_cases)} av minst {len(group.required_tests)} tester kördes"
            )
            if not group_cases:
                problems[-1] = "gruppen är tom, inga tester kördes"
        n_failed = sum(1 for _, o in group_cases if o == "failed")
        n_skipped = sum(1 for _, o in group_cases if o == "skipped")
        if n_failed:
            problems.append(f"{n_failed} tester misslyckades")
        if n_skipped:
            problems.append(f"{n_skipped} tester hoppades över")
        if problems:
            failed = failed or bool(
                n_failed or n_skipped or len(group_cases) < len(group.required_tests)
            )
            print(f"Obligatoriska testgrupper: {group.title_sv} ({group.requirement}): "
                  f"FEL, {'; '.join(problems)}")
        else:
            print(f"Obligatoriska testgrupper: {group.title_sv} ({group.requirement}): "
                  f"OK, {len(group_cases)} tester godkända")
    return failed, missing


def _check_windows(results: dict[str, list[tuple[str, str]]]) -> bool:
    """Returnerar True om Windows-kontrollen fann fel."""
    cases = results.get(WINDOWS_ONLY_MODULE, [])
    problems: list[str] = []
    if not cases:
        problems.append("inga tester kördes i " + WINDOWS_ONLY_MODULE)
    for entry in WINDOWS_ONLY_TESTS:
        name = entry.partition("::")[2]
        if not _has(cases, name):
            problems.append(f"{name} saknas")
    skipped = sorted({n for n, o in cases if o == "skipped"})
    if skipped:
        problems.append("hoppade över på Windows: " + ", ".join(skipped))
    failing = sum(1 for _, o in cases if o == "failed")
    if failing:
        problems.append(f"{failing} tester misslyckades")
    if problems:
        print("Obligatoriska testgrupper: Windows-specifika tester: FEL, " + "; ".join(problems))
        return True
    print(f"Obligatoriska testgrupper: Windows-specifika tester: OK, {len(cases)} tester godkända")
    return False


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    on_windows = sys.platform == "win32"
    wanted: list[str] = [META_DIR]
    for group in MANDATORY_GROUPS:
        for module in group.modules:
            if module not in wanted:
                wanted.append(module)
    if on_windows and WINDOWS_ONLY_MODULE not in wanted:
        wanted.append(WINDOWS_ONLY_MODULE)

    existing = [p for p in wanted if (ROOT / p).exists()]
    missing_modules = {p for p in wanted if p not in existing}
    if not (ROOT / GUARD_MODULE).exists():
        missing_modules.add(GUARD_MODULE)
    real_missing = sorted(m for m in missing_modules if m != META_DIR)

    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["SBK_MANDATORY_STRICT"] = "1"

    pytest_code = EXIT_OK
    results: dict[str, list[tuple[str, str]]] = {}
    if existing:
        with tempfile.TemporaryDirectory(prefix="sbk_mandatory_") as tmp:
            junit = Path(tmp) / "junit.xml"
            cmd = [
                sys.executable, "-m", "pytest", *existing,
                "--strict-markers", "-p", "no:randomly", f"--junitxml={junit}",
            ]
            print("Kör: " + " ".join(cmd), flush=True)
            pytest_code = subprocess.run(cmd, cwd=ROOT, env=env).returncode
            results = _parse_junit(junit)
    else:
        print("Inga obligatoriska testmoduler finns ännu.")

    print()
    if real_missing:
        print("Moduler som saknas:")
        for module in real_missing:
            print(f"  - {module}")
    failed, missing = _evaluate(results, set(real_missing))
    missing = missing or bool(real_missing)
    if on_windows and WINDOWS_ONLY_MODULE not in real_missing:
        failed = _check_windows(results) or failed
    elif on_windows:
        failed = True
        print("Obligatoriska testgrupper: Windows-specifika tester: FEL, "
              f"{WINDOWS_ONLY_MODULE} saknas")

    if pytest_code not in (0, EXIT_MISSING):
        failed = True
    print()
    if missing or pytest_code == EXIT_MISSING:
        print("Obligatoriska tester saknas eller har valts bort. Körningen underkänns "
              f"(utgångskod {EXIT_MISSING}).")
        return EXIT_MISSING
    if failed:
        print(f"Obligatoriska testgrupper: UNDERKÄND (utgångskod {EXIT_FAILED}).")
        return EXIT_FAILED
    print("Obligatoriska testgrupper: GODKÄND, alla grupper gröna utan skip.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
