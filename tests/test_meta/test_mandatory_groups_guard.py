"""Guard test for the Mandatory_Test_Groups (task 17.6, Requirement 35).

Static and fast: every module of ``MANDATORY_GROUPS`` (plus the merge persistence,
candidate service and order modules and this guard) is parsed with ``ast``. The
guard fails when a mandatory test can be skipped, xfail-ed, deselected, weakened
(fewer than 100 Hypothesis examples, derandomised), is missing, or is not
tagged with its design property number. The detection itself is proven with
temporary fixture modules and a temporary project for the conftest hooks.
"""

from __future__ import annotations

import ast
import configparser
import fnmatch
import os
import re
import shlex
import subprocess
import sys
import textwrap
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests.mandatory_groups import (
    GUARD_MODULE,
    MANDATORY_GROUPS,
    WINDOWS_ONLY_MODULE,
    WINDOWS_ONLY_SKIPIF_CONDITION,
    WINDOWS_ONLY_TESTS,
    all_required_tests,
)

pytestmark = pytest.mark.mandatory_integrity

ROOT = Path(__file__).resolve().parents[2]

# Modules outside the six groups that must obey the same static rules.
EXTRA_MODULES: tuple[str, ...] = (
    "tests/test_persistence/test_merge_persistence.py",
    "tests/test_services/test_merge_candidate_service.py",
    "tests/test_services/test_merge_order.py",
)

FORBIDDEN_NAMES = frozenset(
    {
        "skip", "skipif", "xfail", "slow", "optional", "windows_only",
        "importorskip", "skipIf", "skipUnless",
    }
)
_FORBIDDEN_ROOTS = frozenset({"pytest", "mark", "unittest"})
_PROPERTY_TAG = "# Feature: person-comparison-and-merge, Property {n}:"


def _group_modules() -> list[str]:
    seen: list[str] = []
    for group in MANDATORY_GROUPS:
        for module in group.modules:
            if module not in seen:
                seen.append(module)
    return seen


def scanned_modules() -> list[str]:
    modules = _group_modules()
    for extra in (*EXTRA_MODULES, GUARD_MODULE):
        if extra not in modules:
            modules.append(extra)
    return modules


# ---------------------------------------------------------------------------
# Static analysis helpers (operate on source text so fixtures can prove them)
# ---------------------------------------------------------------------------


def _chain(node: ast.AST) -> list[str]:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return list(reversed(parts))


def forbidden_constructs(source: str) -> list[str]:
    """Skip, xfail, slow, optional and similar constructs (also inside marks=)."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute):
            parts = _chain(node)
            if len(parts) >= 2 and parts[0] in _FORBIDDEN_ROOTS and parts[-1] in FORBIDDEN_NAMES:
                found.append(f"{'.'.join(parts)} (rad {node.lineno})")
        elif isinstance(node, ast.ImportFrom) and node.module in ("pytest", "unittest"):
            for alias in node.names:
                if alias.name in FORBIDDEN_NAMES:
                    found.append(f"from {node.module} import {alias.name} (rad {node.lineno})")
    return found


def has_mandatory_pytestmark(source: str) -> bool:
    for node in ast.parse(source).body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        if value is None:
            continue
        if any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets):
            if "mandatory_integrity" in ast.unparse(value):
                return True
    return False


def weak_settings(source: str) -> list[str]:
    """``settings(max_examples=N<100)`` and ``derandomize=True``."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name != "settings":
            continue
        for kw in node.keywords:
            if (
                kw.arg == "max_examples"
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, int)
                and kw.value.value < 100
            ):
                found.append(f"max_examples={kw.value.value} (rad {node.lineno})")
            if (
                kw.arg == "derandomize"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value is True
            ):
                found.append(f"derandomize=True (rad {node.lineno})")
    return found


def defined_names(source: str) -> set[str]:
    return {
        n.name
        for n in ast.walk(ast.parse(source))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def required_violations(root: Path, entries: tuple[str, ...]) -> list[str]:
    """Entries ``module::name`` (name may end in ``*``) not defined in their module."""
    problems: list[str] = []
    cache: dict[str, set[str] | None] = {}
    for entry in entries:
        module, _, pattern = entry.partition("::")
        if module not in cache:
            path = root / module
            cache[module] = defined_names(path.read_text(encoding="utf-8-sig")) if path.exists() else None
        names = cache[module]
        if names is None:
            problems.append(f"{entry}: modulen saknas")
        elif not any(fnmatch.fnmatchcase(n, pattern) for n in names):
            problems.append(f"{entry}: testet saknas")
    return problems


def _read(module: str) -> str:
    return (ROOT / module).read_text(encoding="utf-8-sig")


def _existing(modules: list[str]) -> list[str]:
    return [m for m in modules if (ROOT / m).exists()]


def _missing_modules_message(modules: list[str]) -> list[str]:
    return [f"{m}: modulen saknas" for m in modules if not (ROOT / m).exists()]


# ---------------------------------------------------------------------------
# Static checks on the real mandatory modules
# ---------------------------------------------------------------------------


def test_registry_required_tests_are_defined() -> None:
    problems = required_violations(ROOT, all_required_tests())
    assert not problems, "Obligatoriska tester saknas:\n" + "\n".join(problems)


def test_no_skip_xfail_slow_or_optional_constructs() -> None:
    modules = scanned_modules()
    problems = _missing_modules_message(modules)
    for module in _existing(modules):
        problems += [f"{module}: {hit}" for hit in forbidden_constructs(_read(module))]
    assert not problems, "Förbjudna konstruktioner i obligatoriska moduler:\n" + "\n".join(problems)


def test_every_mandatory_module_has_pytestmark() -> None:
    modules = scanned_modules()
    problems = _missing_modules_message(modules)
    problems += [
        f"{m}: pytestmark = pytest.mark.mandatory_integrity saknas"
        for m in _existing(modules)
        if not has_mandatory_pytestmark(_read(m))
    ]
    assert not problems, "\n".join(problems)


def test_hypothesis_settings_not_weakened() -> None:
    problems: list[str] = []
    for module in _existing(scanned_modules()):
        problems += [f"{module}: {hit}" for hit in weak_settings(_read(module))]
    assert not problems, "Försvagade Hypothesis-inställningar:\n" + "\n".join(problems)


def test_every_mandatory_property_is_tagged() -> None:
    problems: list[str] = []
    for group in MANDATORY_GROUPS:
        text = "\n".join(_read(m) for m in _existing(list(group.modules)))
        for number in group.properties:
            pattern = re.escape(_PROPERTY_TAG.format(n=number))
            if not re.search(pattern + r"(?!\d)", text):
                problems.append(
                    f"{group.key}: Property {number} saknar taggen "
                    f"'{_PROPERTY_TAG.format(n=number)}'"
                )
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# Configuration scan
# ---------------------------------------------------------------------------

_BAD_ADDOPT_PREFIXES = ("--deselect", "--ignore")


def addopts_findings(addopts: str) -> list[str]:
    """Selection-narrowing options in an ``addopts`` string."""
    found: list[str] = []
    for token in shlex.split(addopts, posix=True):
        if token.startswith("--"):
            if token.startswith(_BAD_ADDOPT_PREFIXES):
                found.append(token)
        elif token.startswith(("-m", "-k")):
            found.append(token)
    return found


def _config_options(path: Path) -> dict[str, str]:
    """``addopts`` and ``markers`` of one pytest configuration file (empty if none)."""
    name = path.name
    out: dict[str, str] = {}
    if name == "pyproject.toml":
        table = tomllib.loads(path.read_text(encoding="utf-8-sig")).get("tool", {}).get("pytest", {})
        opts = table.get("ini_options", {})
        addopts = opts.get("addopts", "")
        out["addopts"] = " ".join(addopts) if isinstance(addopts, list) else str(addopts)
        out["markers"] = "\n".join(opts.get("markers", []))
        return out
    section = "tool:pytest" if name == "setup.cfg" else "pytest"
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    if parser.has_section(section):
        out["addopts"] = parser.get(section, "addopts", fallback="").replace("\n", " ")
        out["markers"] = parser.get(section, "markers", fallback="")
    return out


_CONFIG_NAMES = ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini")
_SKIP_DIRS = {"venv", ".venv", ".git", ".hypothesis", "node_modules", "__pycache__", "build", "dist"}


def conftest_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.endswith(".egg-info")]
        if "conftest.py" in filenames:
            found.append(Path(dirpath) / "conftest.py")
    return found


def config_problems(root: Path, mandatory: set[str]) -> tuple[list[str], bool]:
    """Returns (problems, marker_registered)."""
    problems: list[str] = []
    registered = False
    for name in _CONFIG_NAMES:
        path = root / name
        if not path.exists():
            continue
        options = _config_options(path)
        for token in addopts_findings(options.get("addopts", "")):
            problems.append(f"{name}: addopts innehåller {token}")
        if re.search(r"^\s*mandatory_integrity\b", options.get("markers", ""), re.MULTILINE):
            registered = True
    basenames = {Path(m).name for m in mandatory}
    for conftest in conftest_files(root):
        rel = conftest.relative_to(root).as_posix()
        source = conftest.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in ("collect_ignore", "collect_ignore_glob")
                for t in node.targets
            ):
                for const in ast.walk(node.value):
                    if isinstance(const, ast.Constant) and isinstance(const.value, str):
                        value = const.value.replace("\\", "/")
                        if any(
                            fnmatch.fnmatch(m, f"*{value}") or fnmatch.fnmatch(m, value)
                            or Path(m).name == Path(value).name
                            for m in mandatory
                        ) or value in basenames:
                            problems.append(f"{rel}: collect_ignore nämner {value}")
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and "addopts" in source:
                if node.value.lstrip().startswith(("-m ", "-k ", "--deselect", "--ignore")):
                    problems.append(f"{rel}: addopts-liknande värde {node.value!r}")
        if re.search(r"addinivalue_line\(\s*[\"']markers[\"']\s*,\s*[\"']mandatory_integrity", source):
            registered = True
    return problems, registered


def test_config_does_not_narrow_selection() -> None:
    problems, _ = config_problems(ROOT, set(_group_modules()) | {GUARD_MODULE})
    assert not problems, "\n".join(problems)


def test_mandatory_integrity_marker_registered() -> None:
    _, registered = config_problems(ROOT, set())
    assert registered, "mandatory_integrity är inte registrerad i pytest-konfigurationen"


def _collect_all() -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env.pop("SBK_MANDATORY_STRICT", None)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=900,
    )


def collected_names(output: str) -> dict[str, set[str]]:
    names: dict[str, set[str]] = {}
    for line in output.splitlines():
        if "::" not in line:
            continue
        module, _, rest = line.strip().partition("::")
        name = rest.split("::")[-1].split("[", 1)[0]
        names.setdefault(module.replace("\\", "/"), set()).add(name)
    return names


def test_collect_only_lists_every_required_test() -> None:
    result = _collect_all()
    names = collected_names(result.stdout)
    missing = []
    for entry in all_required_tests():
        module, _, pattern = entry.partition("::")
        if not any(fnmatch.fnmatchcase(n, pattern) for n in names.get(module, set())):
            missing.append(entry)
    assert not missing, "Inte insamlade obligatoriska tester:\n" + "\n".join(missing)


def test_ci_workflow_calls_mandatory_runner() -> None:
    workflows = ROOT / ".github" / "workflows"
    if not workflows.exists():
        return  # nothing to check without a CI directory
    texts = [
        p.read_text(encoding="utf-8-sig")
        for p in [*workflows.glob("*.yml"), *workflows.glob("*.yaml")]
    ]
    assert any("scripts/run_mandatory_tests.py" in t for t in texts), (
        "Ingen CI-workflow anropar scripts/run_mandatory_tests.py"
    )


# ---------------------------------------------------------------------------
# Windows-only preflight tests
# ---------------------------------------------------------------------------


def windows_only_problems(source: str) -> list[str]:
    problems: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        skipifs = [
            d for d in node.decorator_list
            if isinstance(d, ast.Call) and _chain(d.func)[-1:] == ["skipif"]
        ]
        marked = any(_chain(d.func if isinstance(d, ast.Call) else d)[-1:] == ["windows_only"]
                     for d in node.decorator_list)
        for deco in skipifs:
            condition = ast.unparse(deco.args[0]).replace("'", '"') if deco.args else ""
            if condition != WINDOWS_ONLY_SKIPIF_CONDITION:
                problems.append(f"{node.name}: skipif-villkoret är {condition!r}")
            if not marked:
                problems.append(f"{node.name}: skipif utan windows_only")
    return problems


def test_windows_only_skipif_condition() -> None:
    path = ROOT / WINDOWS_ONLY_MODULE
    assert path.exists(), f"{WINDOWS_ONLY_MODULE}: modulen saknas"
    source = path.read_text(encoding="utf-8-sig")
    assert not windows_only_problems(source)
    for entry in WINDOWS_ONLY_TESTS:
        assert entry.partition("::")[2] in defined_names(source), f"{entry} saknas"


def test_windows_only_tests_run_on_windows(tmp_path: Path) -> None:
    test_windows_only_skipif_condition()
    if sys.platform != "win32":
        return
    junit = tmp_path / "junit.xml"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env.pop("SBK_MANDATORY_STRICT", None)  # a one-module run must not abort in strict mode
    subprocess.run(
        [sys.executable, "-m", "pytest", WINDOWS_ONLY_MODULE, "-q", "-p", "no:cacheprovider",
         f"--junitxml={junit}"],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=600,
    )
    cases = list(ET.parse(junit).getroot().iter("testcase"))
    skipped = [c.get("name") for c in cases if c.find("skipped") is not None]
    assert not skipped, f"windows_only-test hoppades över på Windows: {skipped}"
    ran = {(c.get("name") or "").split("[", 1)[0] for c in cases}
    for entry in WINDOWS_ONLY_TESTS:
        assert entry.partition("::")[2] in ran


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


def test_environment_available() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import hypothesis  # noqa: F401
    import pytestqt  # noqa: F401
    import slaktbusken.gedcom.importer  # noqa: F401
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    assert app is not None
    assert app.platformName() == "offscreen"


# ---------------------------------------------------------------------------
# Proof that the detection works
# ---------------------------------------------------------------------------

_FORBIDDEN_SNIPPETS = {
    "mark.skip": "@pytest.mark.skip\ndef test_a(): pass",
    "mark.skipif": "@pytest.mark.skipif(True, reason='x')\ndef test_a(): pass",
    "mark.xfail": "@pytest.mark.xfail\ndef test_a(): pass",
    "mark.slow": "@pytest.mark.slow\ndef test_a(): pass",
    "mark.optional": "@pytest.mark.optional\ndef test_a(): pass",
    "pytest.skip": "def test_a():\n    pytest.skip('x')",
    "pytest.xfail": "def test_a():\n    pytest.xfail('x')",
    "pytest.importorskip": "x = pytest.importorskip('nothing')",
    "unittest.skip": "@unittest.skip('x')\ndef test_a(): pass",
    "unittest.skipIf": "@unittest.skipIf(True, 'x')\ndef test_a(): pass",
    "unittest.skipUnless": "@unittest.skipUnless(False, 'x')\ndef test_a(): pass",
    "parametrize marks": (
        "@pytest.mark.parametrize('v', [pytest.param(1, marks=pytest.mark.skip)])\n"
        "def test_a(v): pass"
    ),
    "from import": "from pytest import skip\ndef test_a(): pass",
}


@pytest.mark.parametrize("snippet", list(_FORBIDDEN_SNIPPETS))
def test_detects_each_forbidden_construct(snippet: str, tmp_path: Path) -> None:
    module = tmp_path / "test_bad.py"
    module.write_text("import pytest, unittest\n" + _FORBIDDEN_SNIPPETS[snippet], encoding="utf-8")
    assert forbidden_constructs(module.read_text(encoding="utf-8-sig")), snippet


def test_detects_missing_pytestmark_and_weak_settings(tmp_path: Path) -> None:
    bad = tmp_path / "test_weak.py"
    bad.write_text(
        "from hypothesis import settings\n"
        "@settings(max_examples=99)\ndef test_a(): pass\n"
        "@settings(derandomize=True)\ndef test_b(): pass\n",
        encoding="utf-8",
    )
    source = bad.read_text(encoding="utf-8-sig")
    assert not has_mandatory_pytestmark(source)
    hits = weak_settings(source)
    assert any("max_examples=99" in h for h in hits)
    assert any("derandomize" in h for h in hits)


def test_detects_registry_entry_naming_missing_test(tmp_path: Path) -> None:
    (tmp_path / "test_x.py").write_text("def test_present(): pass\n", encoding="utf-8")
    problems = required_violations(
        tmp_path,
        ("test_x.py::test_present", "test_x.py::test_absent", "test_x.py::test_prop_*",
         "test_nowhere.py::test_a"),
    )
    assert len(problems) == 3
    assert not any("test_present" in p for p in problems)


def test_clean_module_passes(tmp_path: Path) -> None:
    source = textwrap.dedent(
        """
        import pytest
        from hypothesis import settings
        pytestmark = pytest.mark.mandatory_integrity

        @settings(max_examples=100, deadline=None)
        def test_property_1_ok(): pass
        """
    )
    assert forbidden_constructs(source) == []
    assert has_mandatory_pytestmark(source)
    assert weak_settings(source) == []
    assert required_violations(tmp_path, ()) == []


def test_detects_narrowing_addopts_and_collect_ignore(tmp_path: Path) -> None:
    for opts in ("-m 'not slow'", "-k foo", "--deselect a::b", "--ignore=tests/x", "-mfoo"):
        assert addopts_findings(opts), opts
    assert not addopts_findings("--strict-markers -ra")
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\naddopts = -m 'not slow'\nmarkers =\n    other: x\n", encoding="utf-8"
    )
    (tmp_path / "conftest.py").write_text(
        "collect_ignore = ['tests/test_services/test_retired_ids.py']\n", encoding="utf-8"
    )
    problems, registered = config_problems(
        tmp_path, {"tests/test_services/test_retired_ids.py"}
    )
    assert not registered
    assert any("addopts" in p for p in problems)
    assert any("collect_ignore" in p for p in problems)


def test_detects_bad_windows_only_condition() -> None:
    bad = (
        "import sys, pytest\n"
        "@pytest.mark.skipif(sys.platform == 'linux', reason='x')\n"
        "def test_a(): pass\n"
    )
    good = (
        "import sys, pytest\n@pytest.mark.windows_only\n"
        "@pytest.mark.skipif(sys.platform != 'win32', reason='x')\ndef test_a(): pass\n"
    )
    assert windows_only_problems(bad)
    assert windows_only_problems(good) == []


# --- conftest hooks in a temporary project --------------------------------

_TMP_REGISTRY = textwrap.dedent(
    '''
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class MandatoryGroup:
        key: str
        title_sv: str
        requirement: str
        modules: tuple
        properties: tuple
        required_tests: tuple

    MANDATORY_GROUPS = (
        MandatoryGroup("g", "G", "35", ("tests/test_mand.py",), (),
                       ("tests/test_mand.py::test_one", "tests/test_mand.py::test_two")),
    )
    GUARD_MODULE = "tests/test_meta/none.py"

    def mandatory_modules():
        return frozenset({"tests/test_mand.py"})
    '''
)


def _temp_project(tmp_path: Path, body: str) -> Path:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "__init__.py").write_text("", encoding="utf-8")
    (tests / "conftest.py").write_text(
        (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8-sig"), encoding="utf-8"
    )
    (tests / "mandatory_groups.py").write_text(_TMP_REGISTRY, encoding="utf-8")
    (tests / "test_mand.py").write_text(body, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\ntestpaths = tests\naddopts = --strict-markers\nmarkers =\n"
        "    mandatory_integrity: x\n    windows_only: x\n    slow: x\n",
        encoding="utf-8",
    )
    return tmp_path


def _run_temp(project: Path, *args: str, strict: bool = False) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("SBK_MANDATORY_STRICT", None)
    if strict:
        env["SBK_MANDATORY_STRICT"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args],
        cwd=project, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300,
    )


_CLEAN_BODY = "def test_one(): pass\ndef test_two(): pass\n"


def test_hook_runtime_skip_becomes_failure(tmp_path: Path) -> None:
    project = _temp_project(
        tmp_path, "import pytest\ndef test_one():\n    pytest.skip('x')\ndef test_two(): pass\n"
    )
    result = _run_temp(project, "tests/test_mand.py")
    assert result.returncode == 1, result.stdout
    assert "1 failed" in result.stdout and "skipped" not in result.stdout


def test_hook_xpass_becomes_failure(tmp_path: Path) -> None:
    body = (
        "import pytest\n"
        "def test_one():\n    pytest.xfail('x')\n"
        "def test_two(): pass\n"
    )
    result = _run_temp(_temp_project(tmp_path, body), "tests/test_mand.py")
    assert result.returncode == 1, result.stdout
    assert "1 failed" in result.stdout and "xfailed" not in result.stdout
    # a skip/xfail *marker* on a mandatory test is refused at collection
    marked = "import pytest\n@pytest.mark.xfail\ndef test_one(): pass\ndef test_two(): pass\n"
    (tmp_path / "tests" / "test_mand.py").write_text(marked, encoding="utf-8")
    result = _run_temp(tmp_path, "tests/test_mand.py")
    assert result.returncode != 0
    assert "Obligatoriskt test har skip, skipif eller xfail" in result.stdout + result.stderr


def test_hook_deselected_required_test_aborts_strict_run(tmp_path: Path) -> None:
    project = _temp_project(tmp_path, _CLEAN_BODY)
    result = _run_temp(project, "tests/test_mand.py", "-k", "test_one", strict=True)
    assert result.returncode == 3, result.stdout + result.stderr
    assert "Obligatoriskt test bortvalt" in result.stdout + result.stderr


def test_hook_clean_strict_run_passes(tmp_path: Path) -> None:
    result = _run_temp(_temp_project(tmp_path, _CLEAN_BODY), "tests/test_mand.py", strict=True)
    assert result.returncode == 0, result.stdout + result.stderr
