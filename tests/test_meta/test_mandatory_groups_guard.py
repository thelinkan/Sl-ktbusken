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

from tests.reduced_example_counts import (  # noqa: E402
    ABSOLUTE_FLOOR,
    DEFAULT_FLOOR,
    REDUCED_COUNT_ALLOWLIST,
    ReducedCount,
    conftest_profile_problems,
    hypothesis_override_problems,
    profile_max_examples,
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


DATASKYDD_PREFIX = "tests/test_dataskydd/"


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


def weak_settings(source: str, min_examples: int = 100) -> list[str]:
    """``settings(max_examples=N<min_examples)`` and ``derandomize=True``."""
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
                and kw.value.value < min_examples
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
        # Dataskydd counts are judged by the allow-list rule (Requirement 23.8 to
        # 23.11) in test_dataskydd_example_counts; here only derandomize applies.
        minimum = 0 if module.startswith(DATASKYDD_PREFIX) else DEFAULT_FLOOR
        problems += [f"{module}: {hit}" for hit in weak_settings(_read(module), minimum)]
    assert not problems, "Försvagade Hypothesis-inställningar:\n" + "\n".join(problems)


# ---------------------------------------------------------------------------
# Hypothesis example counts of the Dataskydd group (Requirement 23.8 to 23.14)
# ---------------------------------------------------------------------------

_MEASURED_WINDOW = 25  # lines above the first decorator that may hold the measurement


def _is_name(node: ast.AST, name: str) -> bool:
    return (isinstance(node, ast.Name) and node.id == name) or (
        isinstance(node, ast.Attribute) and node.attr == name
    )


def _module_constants(tree: ast.Module) -> dict[str, ast.AST]:
    consts: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    consts[target.id] = node.value
    return consts


def _resolve_kwargs(call: ast.Call, consts: dict[str, ast.AST], profile: int) -> tuple[dict, list[str]]:
    """Keyword values of a ``settings(...)`` call, following ``**NAME`` and constants.

    Returns ({"max_examples": int | None, "derandomize": bool}, unresolved reasons).
    ``None`` for max_examples means "not set here".
    """
    out: dict = {"max_examples": None, "derandomize": False}
    bad: list[str] = []

    def value_of(node: ast.AST):
        if isinstance(node, ast.Name) and node.id in consts:
            node = consts[node.id]
        return node.value if isinstance(node, ast.Constant) else ast.unparse(node)

    for arg in call.args:  # settings(parent, ...): only the sbk profile is understood
        if (
            isinstance(arg, ast.Call)
            and _is_name(arg.func, "get_profile")
            and arg.args
            and isinstance(arg.args[0], ast.Constant)
            and arg.args[0].value == "sbk"
        ):
            out["max_examples"] = profile
        else:
            bad.append(f"positionellt argument {ast.unparse(arg)}")
    for kw in call.keywords:
        if kw.arg is None:  # **NAME
            target = consts.get(kw.value.id) if isinstance(kw.value, ast.Name) else None
            if isinstance(target, ast.Call) and _is_name(target.func, "dict"):
                inner = ast.Call(func=ast.Name(id="settings", ctx=ast.Load()), args=[], keywords=target.keywords)
            elif isinstance(target, ast.Dict) and all(isinstance(k, ast.Constant) for k in target.keys):
                inner = ast.Call(
                    func=ast.Name(id="settings", ctx=ast.Load()), args=[],
                    keywords=[ast.keyword(arg=k.value, value=v) for k, v in zip(target.keys, target.values)],
                )
            else:
                bad.append(f"**{ast.unparse(kw.value)} kan inte tolkas")
                continue
            sub, sub_bad = _resolve_kwargs(inner, consts, profile)
            bad += sub_bad
            if sub["max_examples"] is not None:
                out["max_examples"] = sub["max_examples"]
            out["derandomize"] = out["derandomize"] or sub["derandomize"]
        elif kw.arg == "max_examples":
            value = value_of(kw.value)
            if isinstance(value, int) and not isinstance(value, bool):
                out["max_examples"] = value
            else:
                bad.append(f"max_examples={value}")
        elif kw.arg == "derandomize":
            value = value_of(kw.value)
            if value is True or not isinstance(value, bool):
                out["derandomize"] = True
    return out, bad


def property_test_counts(source: str, profile: int = DEFAULT_FLOOR) -> dict[str, dict]:
    """Effective Hypothesis settings per ``@given`` test function of one module.

    Returns {name: {"count": int | None, "derandomize": bool, "unresolved": [..],
    "measured": bool}}. ``count`` is None when it cannot be resolved (fail closed).
    """
    tree = ast.parse(source)
    lines = source.splitlines()
    consts = _module_constants(tree)
    found: dict[str, dict] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorators = node.decorator_list
        if not any(_is_name(d.func if isinstance(d, ast.Call) else d, "given") for d in decorators):
            continue
        count: int | None = profile
        derandomize = False
        unresolved: list[str] = []
        for deco in decorators:
            if isinstance(deco, ast.Call) and _is_name(deco.func, "settings"):
                resolved, bad = _resolve_kwargs(deco, consts, profile)
                unresolved += bad
                if resolved["max_examples"] is not None:
                    count = resolved["max_examples"]
                derandomize = derandomize or resolved["derandomize"]
        first = min(d.lineno for d in decorators)
        window = "\n".join(lines[max(0, first - 1 - _MEASURED_WINDOW): max(d.end_lineno or d.lineno for d in decorators)])
        found[node.name] = {
            "count": None if unresolved else count,
            "derandomize": derandomize,
            "unresolved": unresolved,
            "measured": "MEASURED" in window,
        }
    return found


def example_count_problems(
    sources: dict[str, str],
    allowlist: dict[str, ReducedCount],
    profile: int = DEFAULT_FLOOR,
) -> list[str]:
    """Violations of the Default_Floor / Reduced_Count_Allowlist rule (Req. 23.8 to 23.11)."""
    problems: list[str] = []
    seen: dict[str, dict] = {}
    for module, source in sorted(sources.items()):
        for name, info in property_test_counts(source, profile).items():
            test_id = f"{module}::{name}"
            seen[test_id] = info
            if info["unresolved"]:
                problems.append(
                    f"{test_id}: max_examples kan inte läsas statiskt ({'; '.join(info['unresolved'])})"
                )
                continue
            if info["derandomize"]:
                problems.append(f"{test_id}: derandomize=True är förbjudet")
            count = info["count"]
            entry = allowlist.get(test_id)
            if entry is None and count < DEFAULT_FLOOR:
                problems.append(
                    f"{test_id}: max_examples={count}, minst {DEFAULT_FLOOR} krävs "
                    "utan post i REDUCED_COUNT_ALLOWLIST"
                )
            elif entry is not None and count < entry.min_examples:
                problems.append(
                    f"{test_id}: max_examples={count} understiger postens min_examples={entry.min_examples}"
                )
    for test_id, entry in sorted(allowlist.items()):
        info = seen.get(test_id)
        if entry.min_examples < ABSOLUTE_FLOOR:
            problems.append(
                f"{test_id}: min_examples={entry.min_examples} understiger absolutgolvet {ABSOLUTE_FLOOR}"
            )
        if entry.min_examples >= DEFAULT_FLOOR:
            problems.append(f"{test_id}: föråldrad post, min_examples={entry.min_examples} är minst {DEFAULT_FLOOR}")
        if entry.measured_s_per_example <= 0 or not entry.reason.strip():
            problems.append(f"{test_id}: posten saknar uppmätt tid eller skäl")
        if info is None:
            problems.append(f"{test_id}: föråldrad post, testet finns inte")
            continue
        if info["count"] is not None and info["count"] >= DEFAULT_FLOOR:
            problems.append(
                f"{test_id}: föråldrad post, testets max_examples={info['count']} är minst {DEFAULT_FLOOR}"
            )
        if not info["measured"]:
            problems.append(f"{test_id}: föråldrad post, ingen MEASURED-dokumentation bredvid @settings")
    return problems


def _dataskydd_sources() -> dict[str, str]:
    return {
        m: _read(m)
        for m in sorted(str(p.relative_to(ROOT).as_posix()) for p in (ROOT / "tests/test_dataskydd").glob("test_*.py"))
    }


def _conftest_profile() -> int:
    return profile_max_examples((ROOT / "tests" / "conftest.py").read_text(encoding="utf-8-sig"))


def test_dataskydd_example_counts() -> None:
    problems = example_count_problems(_dataskydd_sources(), REDUCED_COUNT_ALLOWLIST, _conftest_profile())
    assert not problems, "Hypothesis-antal i Dataskydd:\n" + "\n".join(problems)


def test_hypothesis_profile_is_not_lowered() -> None:
    assert _conftest_profile() >= DEFAULT_FLOOR
    problems = hypothesis_override_problems([], {}, ROOT)
    assert not problems, "Hypothesis-profil eller -åsidosättning:\n" + "\n".join(problems)


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


_PROP_MODULE = "tests/test_dataskydd/test_fixture.py"
_TEST_ID = f"{_PROP_MODULE}::test_property_x"


def _prop_source(count: object, *, measured: bool = False, extra: str = "") -> str:
    note = "MEASURED_S_PER_EXAMPLE = 0.5  # measured, fixture\n" if measured else ""
    return (
        "from hypothesis import given, settings, strategies as st\n"
        f"{note}"
        f"@settings(max_examples={count}, deadline=None{extra})\n"
        "@given(st.integers())\n"
        "def test_property_x(n): pass\n"
    )


def _entry(minimum: int = 30) -> dict[str, ReducedCount]:
    return {_TEST_ID: ReducedCount(minimum, 0.5, "full GEDCOM import per example")}


def test_guard_requires_100_examples_by_default() -> None:
    assert DEFAULT_FLOOR == 100
    assert example_count_problems({_PROP_MODULE: _prop_source(99)}, {}) != []
    assert example_count_problems({_PROP_MODULE: _prop_source(100)}, {}) == []
    # no @settings at all: the profile count applies
    plain = "from hypothesis import given, strategies as st\n@given(st.integers())\ndef test_property_x(n): pass\n"
    assert example_count_problems({_PROP_MODULE: plain}, {}, profile=100) == []
    assert example_count_problems({_PROP_MODULE: plain}, {}, profile=50) != []
    # a count the guard cannot resolve fails closed
    assert example_count_problems({_PROP_MODULE: _prop_source("SOME_NAME")}, {}) != []
    # a shared dict of settings is followed
    shared = (
        "from hypothesis import given, settings, strategies as st\n"
        "_S = dict(max_examples=40, deadline=None)\n"
        "@settings(**_S)\n@given(st.integers())\ndef test_property_x(n): pass\n"
    )
    assert example_count_problems({_PROP_MODULE: shared}, {}) != []
    # derandomize=True is rejected, also through a shared dict
    assert example_count_problems({_PROP_MODULE: _prop_source(100, extra=", derandomize=True")}, {}) != []
    assert example_count_problems({_PROP_MODULE: shared.replace("40", "100").replace("deadline=None", "derandomize=True")}, {}) != []


def test_guard_accepts_allowlisted_reduced_count() -> None:
    source = _prop_source(30, measured=True)
    assert example_count_problems({_PROP_MODULE: source}, _entry(30)) == []
    # a count below the entry's minimum is rejected
    assert example_count_problems({_PROP_MODULE: _prop_source(29, measured=True)}, _entry(30)) != []


def test_guard_rejects_count_below_absolute_floor() -> None:
    assert ABSOLUTE_FLOOR == 20
    problems = example_count_problems({_PROP_MODULE: _prop_source(19, measured=True)}, _entry(19))
    assert any("absolutgolvet" in p for p in problems)
    assert example_count_problems({_PROP_MODULE: _prop_source(20, measured=True)}, _entry(20)) == []


def test_guard_rejects_stale_allowlist_entry() -> None:
    # unknown test
    assert any("testet finns inte" in p for p in example_count_problems({}, _entry()))
    # the test now uses 100 examples
    problems = example_count_problems({_PROP_MODULE: _prop_source(100, measured=True)}, _entry())
    assert any("föråldrad" in p and _TEST_ID in p for p in problems)
    # no documented measurement next to @settings
    problems = example_count_problems({_PROP_MODULE: _prop_source(30)}, _entry())
    assert any("MEASURED" in p for p in problems)
    # the real allow-list has no stale entry (also covered by test_dataskydd_example_counts)
    assert not [p for p in example_count_problems(_dataskydd_sources(), REDUCED_COUNT_ALLOWLIST, _conftest_profile()) if "föråldrad" in p]


def test_runner_rejects_hypothesis_override(tmp_path: Path) -> None:
    import importlib.util

    assert hypothesis_override_problems([], {}, ROOT) == []
    assert hypothesis_override_problems(["--hypothesis-profile=ci"], {}, ROOT)
    assert hypothesis_override_problems([], {"HYPOTHESIS_PROFILE": "fast"}, ROOT)
    assert hypothesis_override_problems([], {"PYTEST_ADDOPTS": "--hypothesis-seed=1"}, ROOT)
    # a conftest that registers or loads another profile, or lowers sbk
    for body in (
        "from hypothesis import settings\nsettings.register_profile('fast', max_examples=5)\n",
        "from hypothesis import settings\nsettings.load_profile('fast')\n",
        "from hypothesis import settings\nsettings.register_profile('sbk', max_examples=10)\n"
        "settings.load_profile('sbk')\n",
    ):
        project = tmp_path / str(abs(hash(body)))
        (project / "tests").mkdir(parents=True)
        (project / "tests" / "conftest.py").write_text(body, encoding="utf-8")
        assert hypothesis_override_problems([], {}, project), body
    assert conftest_profile_problems(
        "from hypothesis import settings\nsettings.register_profile('sbk', max_examples=100)\n"
        "settings.load_profile('sbk')\n", "tests/conftest.py", root_conftest=True) == []
    # the runner script itself refuses to start with an override
    spec = importlib.util.spec_from_file_location("sbk_runner", ROOT / "scripts" / "run_mandatory_tests.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    old_argv, old_env = sys.argv, os.environ.get("HYPOTHESIS_PROFILE")
    try:
        sys.argv = ["run_mandatory_tests.py", "--hypothesis-profile=fast"]
        assert runner.main() == runner.EXIT_FAILED
        sys.argv = ["run_mandatory_tests.py"]
        os.environ["HYPOTHESIS_PROFILE"] = "fast"
        assert runner.main() == runner.EXIT_FAILED
    finally:
        sys.argv = old_argv
        if old_env is None:
            os.environ.pop("HYPOTHESIS_PROFILE", None)
        else:
            os.environ["HYPOTHESIS_PROFILE"] = old_env


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
