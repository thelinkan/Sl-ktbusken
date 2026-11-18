"""An unexpected error aborts the whole GEDCOM import (Requirements 20.5, 20.23 to 20.28).

An ordinary unexpected exception inside the importer (``RuntimeError``,
``KeyError``, ``AttributeError``, ``AssertionError``) never turns into a
"Hoppades över" warning. The import is aborted with ``ImportAborted``: a Swedish
message that names the record, the original exception as ``__cause__``, the
traceback as text, and nothing has changed (project data, Dirty_State,
Content_Revision, Pending_Translation and Translation_File bytes). Recognised
input problems (an uninterpretable date, an unknown level-0 tag) and findings
that were already in the project still only warn.

Every test imports through ``ImportService.run`` into a real project on disk.

**Validates: Requirements 20.5, 20.23, 20.24, 20.25, 20.26, 20.27, 20.28, 23.1, 23.2**
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from hypothesis import HealthCheck, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import slaktbusken.app as app_module  # noqa: E402
from slaktbusken.gedcom.errors import MSG_ABORT_PREFIX, ImportAborted  # noqa: E402
from slaktbusken.gedcom.importer import GEDCOMImporter  # noqa: E402
from slaktbusken.gedcom.translation import TranslationManager  # noqa: E402
from slaktbusken.model.event import Event, PlaceRef  # noqa: E402
from slaktbusken.persistence.serialization import serialize  # noqa: E402
from slaktbusken.persistence.translation_io import (  # noqa: E402
    dumps_persons,
    dumps_places,
    dumps_sources,
)
from slaktbusken.services.import_service import ImportService  # noqa: E402
from slaktbusken.services.project_service import ProjectService  # noqa: E402
from slaktbusken.services.validation_service import ValidationService  # noqa: E402
from slaktbusken.ui.merge import recovery_dialogs  # noqa: E402

pytestmark = pytest.mark.mandatory_integrity

_TRANSLATION_NAMES = ("persons.json", "places.json", "sources.json")
_EXCEPTION_TYPES = (RuntimeError, KeyError, AttributeError, AssertionError)
_STATES = ("saved", "pending")
_INJECTED_TEXT = "injicerat fel"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------
class World:
    """A real project on disk and the service that imports into it."""

    def __init__(self, root: Path) -> None:
        self.ps = ProjectService()
        self.ps.create_project("Projekt", root)
        self.folder = self.ps.project_path.parent
        self.translation = self.folder / "translation"
        self.service = ImportService(ValidationService())
        self._n = 0

    @property
    def data(self):
        return self.ps.data

    def write(self, text: str) -> Path:
        self._n += 1
        path = self.folder / f"import_{self._n}.ged"
        path.write_text(text, encoding="utf-8")
        return path

    def run(self, text: str):
        return self.service.run(self.ps.data, self.write(text), self.folder, self.ps)

    def snapshot(self) -> tuple:
        pending = self.ps.pending_translation
        files = {
            n: (self.translation / n).read_bytes() if (self.translation / n).exists() else None
            for n in _TRANSLATION_NAMES
        }
        return (
            serialize(self.ps.data),
            None
            if pending is None
            else (
                dumps_persons(
                    pending.data.persons, pending.data.families, pending.data.person_aliases
                ),
                dumps_places(pending.data.places),
                dumps_sources(pending.data.sources),
                dict(pending.base),
            ),
            files,
            self.ps.is_dirty,
            self.ps.content_revision,
            self.ps.revision,
        )


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def person_lines(
    n: int,
    given: str,
    surname: str,
    birth: str = "1900",
    place: str = "Testby, Sverige",
    resi: Optional[str] = "Boplats, Sverige",
    famc: Optional[str] = None,
    fams: Optional[str] = None,
    source: Optional[str] = None,
) -> list[str]:
    lines = [f"0 @I{n}@ INDI", f"1 NAME {given} /{surname}/", "1 SEX F"]
    lines += ["1 BIRT", f"2 DATE {birth}", f"2 PLAC {place}"]
    if source:
        lines.append(f"2 SOUR {source}")
    if resi:
        lines += ["1 RESI", "2 DATE 1910", f"2 PLAC {resi}"]
    if famc:
        lines.append(f"1 FAMC {famc}")
    if fams:
        lines.append(f"1 FAMS {fams}")
    return lines


def family_lines(n: int, husb: int, wife: int, children: list[int]) -> list[str]:
    lines = [f"0 @F{n}@ FAM", f"1 HUSB @I{husb}@", f"1 WIFE @I{wife}@"]
    lines += [f"1 CHIL @I{c}@" for c in children]
    lines += ["1 MARR", "2 DATE 1925"]
    return lines


def ged(*blocks: list[str]) -> str:
    lines = ["0 HEAD", "1 CHAR UTF-8"]
    for block in blocks:
        lines += block
    lines.append("0 TRLR")
    return "\n".join(lines)


def source_lines(n: int, title: str) -> list[str]:
    return [f"0 @S{n}@ SOUR", f"1 TITL {title}"]


# File A is the base content of the project; file B has other xrefs, names,
# places and sources, so importing it creates every record.
FILE_A = ged(
    source_lines(1, "Första källan"),
    person_lines(1, "Anna", "Svensson", famc="@F1@", source="@S1@"),
    person_lines(2, "Erik", "Olsson", "1905", "Annanby, Sverige", "Hemma, Sverige", fams="@F1@"),
    family_lines(1, 2, 1, []),
)
FILE_B = ged(
    source_lines(11, "Källa Elva"),
    person_lines(
        11, "Zacharias", "Berg", "1880", "Nybyn, Sverige", "Skogsby, Sverige",
        fams="@F11@", source="@S11@",
    ),
    person_lines(12, "Ylva", "Berg", "1882", "Ödeby, Sverige", "Mellanby, Sverige", fams="@F11@"),
    family_lines(11, 11, 12, []),
)


@dataclass(frozen=True)
class Kind:
    """An injection point and the record that the abort message must name."""

    name: str
    owner: type
    method: str
    reimport: bool  # True: the project already holds file B and B is imported again
    xref: str
    label: str  # text that the message contains after the xref


KINDS: dict[str, Kind] = {
    k.name: k
    for k in (
        Kind("person_create", GEDCOMImporter, "_create_person", False, "@I11@", "Zacharias Berg"),
        Kind("person_update", GEDCOMImporter, "_update_person", True, "@I11@", "Zacharias Berg"),
        Kind("event", GEDCOMImporter, "_create_event", False, "@I11@", "Zacharias Berg"),
        Kind("residence", GEDCOMImporter, "_add_residence", False, "@I11@", "Zacharias Berg"),
        Kind("family_create", GEDCOMImporter, "_create_family", False, "@F11@", "FAM"),
        Kind("family_update", GEDCOMImporter, "_update_family", True, "@F11@", "FAM"),
        Kind("place", GEDCOMImporter, "_resolve_place", False, "@I11@", "Zacharias Berg"),
        Kind("source", TranslationManager, "map_source", False, "@S11@", "Källa Elva"),
    )
}


class Injector:
    """Raises *exc* on the *position*-th call of ``owner.method``."""

    def __init__(self, owner: type, method: str, position: int, exc: BaseException) -> None:
        self.owner, self.method, self.position, self.exc = owner, method, position, exc
        self.calls = 0
        self.fired = False

    @contextmanager
    def active(self):
        original = getattr(self.owner, self.method)
        injector = self

        def wrapper(*args, **kwargs):
            injector.calls += 1
            if injector.calls == injector.position:
                injector.fired = True
                raise injector.exc
            return original(*args, **kwargs)

        with patch.object(self.owner, self.method, wrapper):
            yield self


def prepare(world: World, state: str, base: str) -> None:
    """Import *base*; ``saved`` saves the project, ``pending`` leaves the translation staged."""
    world.run(base)
    if state == "saved":
        world.ps.save_project()
        assert world.ps.pending_translation is None
    else:
        assert world.ps.pending_translation is not None


def abort_import(
    world: World, kind: Kind, text: str, exc_type: type, position: int = 1
) -> tuple[ImportAborted, BaseException]:
    """Import *text* with a failure injected into *kind* and check the invariants.

    Returns the ``ImportAborted`` and the injected exception.
    """
    before = world.snapshot()
    pending_before = world.ps.pending_translation
    exc = exc_type(_INJECTED_TEXT)
    injector = Injector(kind.owner, kind.method, position, exc)
    result = None
    with injector.active():
        with pytest.raises(ImportAborted) as raised:
            result = world.run(text)
    assert injector.fired, f"{kind.name}: the injection point was never reached"
    assert result is None  # no ImportResult exists
    assert world.snapshot() == before
    assert world.ps.pending_translation is pending_before
    assert not world.ps.import_in_progress
    return raised.value, exc


def start(world: World, kind: Kind, state: str) -> None:
    prepare(world, state, FILE_B if kind.reimport else FILE_A)


def assert_swedish_record_message(aborted: ImportAborted, kind: Kind, exc: BaseException) -> None:
    message = aborted.message_sv
    assert message == aborted.args[0]
    assert message.startswith(f"{MSG_ABORT_PREFIX} Fel i post {kind.xref} (")
    assert kind.label in message.split(":", 1)[0]
    assert _INJECTED_TEXT in message
    assert "Hoppades över" not in message
    assert aborted.xref == kind.xref


def assert_traceback(aborted: ImportAborted, exc: BaseException) -> None:
    assert aborted.traceback_text.strip()
    assert type(exc).__name__ in aborted.traceback_text
    assert "Traceback (most recent call last)" in aborted.traceback_text
    assert aborted.__cause__ is exc


def _run_kind(world: World, kind_name: str, state: str, exc_type: type):
    kind = KINDS[kind_name]
    start(world, kind, state)
    return kind, *abort_import(world, kind, FILE_B, exc_type)


# ---------------------------------------------------------------------------
# One test per entity kind (Requirement 20.28)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("state", _STATES)
@pytest.mark.parametrize("exc_type", _EXCEPTION_TYPES)
def test_import_abort_person_create(world: World, state: str, exc_type: type) -> None:
    kind, aborted, exc = _run_kind(world, "person_create", state, exc_type)
    assert_swedish_record_message(aborted, kind, exc)
    assert_traceback(aborted, exc)


@pytest.mark.parametrize("state", _STATES)
@pytest.mark.parametrize("exc_type", _EXCEPTION_TYPES)
def test_import_abort_person_update(world: World, state: str, exc_type: type) -> None:
    kind, aborted, exc = _run_kind(world, "person_update", state, exc_type)
    assert_swedish_record_message(aborted, kind, exc)
    assert_traceback(aborted, exc)


@pytest.mark.parametrize("state", _STATES)
@pytest.mark.parametrize("exc_type", _EXCEPTION_TYPES)
def test_import_abort_event(world: World, state: str, exc_type: type) -> None:
    kind, aborted, exc = _run_kind(world, "event", state, exc_type)
    assert_swedish_record_message(aborted, kind, exc)
    assert_traceback(aborted, exc)


@pytest.mark.parametrize("state", _STATES)
@pytest.mark.parametrize("exc_type", _EXCEPTION_TYPES)
def test_import_abort_residence(world: World, state: str, exc_type: type) -> None:
    kind, aborted, exc = _run_kind(world, "residence", state, exc_type)
    assert_swedish_record_message(aborted, kind, exc)
    assert_traceback(aborted, exc)


@pytest.mark.parametrize("kind_name", ["family_create", "family_update"])
@pytest.mark.parametrize("state", _STATES)
@pytest.mark.parametrize("exc_type", _EXCEPTION_TYPES)
def test_import_abort_family(world: World, kind_name: str, state: str, exc_type: type) -> None:
    kind, aborted, exc = _run_kind(world, kind_name, state, exc_type)
    assert_swedish_record_message(aborted, kind, exc)
    assert_traceback(aborted, exc)


@pytest.mark.parametrize("kind_name", ["place", "source"])
@pytest.mark.parametrize("state", _STATES)
@pytest.mark.parametrize("exc_type", _EXCEPTION_TYPES)
def test_import_abort_place_and_source(
    world: World, kind_name: str, state: str, exc_type: type
) -> None:
    kind, aborted, exc = _run_kind(world, kind_name, state, exc_type)
    assert_swedish_record_message(aborted, kind, exc)
    assert_traceback(aborted, exc)


# ---------------------------------------------------------------------------
# Message, traceback and result for every kind
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kind_name", list(KINDS))
def test_import_abort_message_names_record_in_swedish(world: World, kind_name: str) -> None:
    kind, aborted, exc = _run_kind(world, kind_name, "pending", RuntimeError)
    assert_swedish_record_message(aborted, kind, exc)
    assert aborted.label is not None and kind.label in aborted.label
    # The message is the user text: it carries no traceback.
    assert "Traceback" not in aborted.message_sv


@pytest.mark.parametrize("kind_name", list(KINDS))
def test_import_abort_traceback_available(world: World, kind_name: str) -> None:
    kind, aborted, exc = _run_kind(world, kind_name, "saved", KeyError)
    assert_traceback(aborted, exc)
    assert kind.method in aborted.traceback_text or "wrapper" in aborted.traceback_text


@pytest.mark.parametrize("kind_name", list(KINDS))
def test_import_abort_no_successful_result(world: World, kind_name: str) -> None:
    kind = KINDS[kind_name]
    start(world, kind, "saved")
    before = world.snapshot()
    injector = Injector(kind.owner, kind.method, 1, AttributeError(_INJECTED_TEXT))
    outcome = []
    with injector.active():
        try:
            outcome.append(world.run(FILE_B))
        except ImportAborted as aborted:
            outcome.append(aborted)
    assert len(outcome) == 1 and isinstance(outcome[0], ImportAborted)
    assert "Hoppades över" not in outcome[0].message_sv
    # A later import without the failure still works, and only then changes the project.
    assert world.snapshot() == before
    result = world.run(FILE_B)
    assert not [w for w in result.warnings if "Hoppades över" in str(w)]


# ---------------------------------------------------------------------------
# Recoverable input still warns and continues
# ---------------------------------------------------------------------------
def _warning_text(result) -> str:
    return "\n".join(str(w) for w in result.warnings)


def test_recoverable_date_problem_still_warns_and_continues(world: World) -> None:
    text = ged(
        person_lines(1, "Anna", "Svensson", birth="runt midsommar någon gång"),
        person_lines(2, "Erik", "Olsson", "1905", "Annanby, Sverige", "Hemma, Sverige"),
    )
    result = world.run(text)
    assert result.persons_added == 2
    assert "runt midsommar" in _warning_text(result)
    unparsed = [
        e for e in world.data.events if e.date is not None and e.date.qualifier == "unparsed"
    ]
    assert [e.date.original_text for e in unparsed] == ["runt midsommar någon gång"]
    assert world.ps.is_dirty


def test_recoverable_unknown_level0_tag_warns_and_continues(world: World) -> None:
    text = ged(person_lines(1, "Anna", "Svensson"), ["0 _OKANDTAG", "1 DATA värde"])
    result = world.run(text)
    assert result.persons_added == 1
    warnings = _warning_text(result)
    assert "ej stödd GEDCOM-taggtyp '_OKANDTAG'" in warnings


def test_preexisting_validation_finding_still_warns(world: World) -> None:
    broken = Event(
        id="evt-sedan-tidigare",
        type="birth",
        participants=[],
        place=PlaceRef(place_id="plats-saknas"),
    )
    world.data.events.append(broken)
    pre_existing = {(e.entity_id, e.message) for e in ValidationService().validate_project(world.data)}
    assert pre_existing
    result = world.run(ged(person_lines(1, "Anna", "Svensson")))
    assert result.persons_added == 1
    assert "Valideringsvarning" in _warning_text(result)
    assert any(e.id == "evt-sedan-tidigare" for e in world.data.events)


# ---------------------------------------------------------------------------
# Application level
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def boxes(monkeypatch):
    box = MagicMock()
    monkeypatch.setattr(app_module, "QMessageBox", box)
    monkeypatch.setattr(app_module.QApplication, "processEvents", staticmethod(lambda: None))
    monkeypatch.setattr(recovery_dialogs, "QMessageBox", box)
    return box


def _fake_app(world: World, **extra):
    return SimpleNamespace(
        main_window=MagicMock(),
        project_service=world.ps,
        import_service=world.service,
        _update_status=MagicMock(),
        _update_diagram_panel=MagicMock(),
        _write_import_log=MagicMock(return_value=None),
        _prompt_select_main_person=MagicMock(),
        **extra,
    )


@pytest.mark.parametrize("state", _STATES)
def test_import_abort_app_shows_critical_message_only(
    qapp, boxes, monkeypatch, world: World, state: str
) -> None:
    """The application shows the Swedish message as a critical box and no success report."""
    prepare(world, state, FILE_A)
    path = world.write(FILE_B)
    dialog = MagicMock()
    dialog.getOpenFileName.return_value = (str(path), "")
    monkeypatch.setattr(app_module, "QFileDialog", dialog)

    def boom(self, *args, **kwargs):
        raise RuntimeError(_INJECTED_TEXT)

    monkeypatch.setattr(GEDCOMImporter, "_create_event", boom)
    fake = _fake_app(world)
    before = world.snapshot()
    pending = world.ps.pending_translation

    app_module.Application.import_gedcom(fake)

    boxes.critical.assert_called_once()
    message = boxes.critical.call_args.args[2]
    assert message.startswith(
        f"{MSG_ABORT_PREFIX} Fel i post @I11@ (Zacharias Berg): "
    )
    assert _INJECTED_TEXT in message
    boxes.information.assert_not_called()
    boxes.warning.assert_not_called()
    fake._write_import_log.assert_not_called()
    fake._prompt_select_main_person.assert_not_called()
    assert world.snapshot() == before
    assert world.ps.pending_translation is pending


# ---------------------------------------------------------------------------
# Property: any injection leaves everything unchanged
# ---------------------------------------------------------------------------
_FRESH_GIVEN = ["Zacharias", "Ylva", "Xenia", "Wilhelm", "Vera", "Ulrika"]
_FRESH_SURNAME = ["Berg", "Lind", "Dahl"]
_FRESH_PLACES = ["Nybyn, Sverige", "Ödeby, Sverige", "Skogsby, Sverige", "Mellanby, Sverige"]
_YEARS = ["1880", "1890", "1901"]

# Largest call number that every generated file reaches, per injection point.
_MAX_POSITION = {
    "person_create": 2,
    "person_update": 2,
    "event": 2,
    "residence": 2,
    "family_create": 1,
    "family_update": 1,
    "place": 2,
    "source": 1,
}


@st.composite
def fresh_files(draw) -> tuple[str, list[tuple[str, str]]]:
    """A GEDCOM file with two or three persons, a family and a source.

    Returns the text and the (xref, name) of its persons in file order.
    """
    n = draw(st.integers(2, 3))
    givens = draw(st.lists(st.sampled_from(_FRESH_GIVEN), min_size=n, max_size=n, unique=True))
    persons: list[list[str]] = []
    info: list[tuple[str, str]] = []
    for i, given in enumerate(givens):
        number = 11 + i
        surname = draw(st.sampled_from(_FRESH_SURNAME))
        persons.append(
            person_lines(
                number,
                given,
                surname,
                draw(st.sampled_from(_YEARS)),
                draw(st.sampled_from(_FRESH_PLACES)),
                draw(st.sampled_from(_FRESH_PLACES)),
                famc="@F11@" if i == 2 else None,
                fams="@F11@" if i < 2 else None,
                source="@S11@" if i == 0 else None,
            )
        )
        info.append((f"@I{number}@", f"{given} {surname}"))
    text = ged(
        source_lines(11, "Källa Elva"),
        *persons,
        family_lines(11, 11, 12, [13] if n == 3 else []),
    )
    return text, info


# Hypothesis settings: a full import (twice) into a real project on disk.
# MEASURED_S_PER_EXAMPLE = 0.044  # 100 examples in 4.4 s (typical 29-57 ms each).
# That is fast enough for the Default_Floor of 100, so no reduced count and no
# allow-list entry are needed.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    generated=fresh_files(),
    kind_name=st.sampled_from(sorted(KINDS)),
    position=st.integers(1, 2),
    exc_type=st.sampled_from(_EXCEPTION_TYPES),
    state=st.sampled_from(_STATES),
)
def test_import_abort_property_leaves_everything_unchanged(
    generated: tuple[str, list[tuple[str, str]]],
    kind_name: str,
    position: int,
    exc_type: type,
    state: str,
) -> None:
    """**Validates: Requirements 20.5, 20.25, 20.26, 20.27, 20.28**

    The same invariants as the per-kind tests, for a generated file and a
    generated injection point (importer method, call number, exception type).
    """
    text, persons = generated
    kind = KINDS[kind_name]
    position = min(position, _MAX_POSITION[kind_name])
    root = Path(tempfile.mkdtemp())
    try:
        world = World(root)
        prepare(world, state, text if kind.reimport else FILE_A)
        aborted, exc = abort_import(world, kind, text, exc_type, position)
        assert aborted.message_sv.startswith(MSG_ABORT_PREFIX)
        assert _INJECTED_TEXT in aborted.message_sv
        assert "Hoppades över" not in aborted.message_sv
        assert aborted.traceback_text.strip()
        assert type(exc).__name__ in aborted.traceback_text
        assert aborted.__cause__ is exc
        if kind_name in ("person_create", "person_update", "event", "residence"):
            xref, name = persons[position - 1]
            assert f"Fel i post {xref} ({name}):" in aborted.message_sv
        elif kind_name == "place":
            assert re.search(r"Fel i post @I\d+@ \(", aborted.message_sv)
        elif kind_name in ("family_create", "family_update"):
            assert "Fel i post @F11@ (FAM):" in aborted.message_sv
        else:
            assert "Fel i post @S11@ (Källa Elva):" in aborted.message_sv
    finally:
        shutil.rmtree(root, ignore_errors=True)
