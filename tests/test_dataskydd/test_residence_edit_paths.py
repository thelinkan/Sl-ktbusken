"""Residence origins through every residence edit operation (Requirement 22.22).

An operation that keeps the residence id keeps ``origins`` unchanged. A split
gives both halves a complete copy, a merge gives the earlier residence's origins
followed by the later residence's origins with a new Origin_Key. A static guard
fails on a ``ResidenceFact(...)`` construction in ``slaktbusken/ui`` or
``slaktbusken/services`` that neither passes ``origins=`` nor is allow-listed.
"""

from __future__ import annotations

import ast
import copy
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from PySide6.QtWidgets import QMessageBox

from slaktbusken.model.event import SourceRef
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.record_origin import RecordOrigin, origin_key
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.services.residence_coverage import CoverageGap, coverage_gaps
from slaktbusken.services.residence_edit_ops import (
    attach_observations,
    merge,
    remove_observation,
    split_at_gap,
    use_as_exact_end,
    use_as_exact_start,
)
from slaktbusken.ui.editors.residence_editor import ResidenceEditor
from tests.test_dataskydd.residence_construction_allowlist import (
    RESIDENCE_CONSTRUCTION_ALLOWLIST,
)
from tests.test_dataskydd.strategies import residence_origins

pytestmark = pytest.mark.mandatory_integrity

_PACKAGE = Path(__file__).resolve().parents[2] / "slaktbusken"
_REPO = _PACKAGE.parent


def _origin(n: int, instance: int = 0) -> RecordOrigin:
    return RecordOrigin(
        owner_kind="INDI",
        owner_id="person_1",
        owner_xref=f"@I{n}@",
        tag_key="RESI",
        index=n,
        record_hash=f"{n:064x}",
        uid=f"uid-{n}" if n % 2 else None,
        instance=instance,
    )


def _obs(first: str, last: str) -> Observation:
    return Observation(
        source_ref=SourceRef(source_id="source_1", quality="primary"),
        observed_from=first,
        observed_to=last,
    )


def _scenario(
    o_main: list[RecordOrigin],
    o_same: list[RecordOrigin],
    o_next: list[RecordOrigin],
    *,
    with_neighbour: bool = True,
) -> tuple[ProjectData, ResidenceFact, ResidenceFact, ResidenceFact | None]:
    """A project with a splittable residence, a same-place partner to merge
    with and (optionally) a residence at another place to link by a flytt."""
    main = ResidenceFact(
        id="residence_main",
        person_id="person_1",
        place_id="place_1",
        start=Endpoint(earliest="1840", latest="1840", precision="year"),
        end=Endpoint(earliest="1870", latest="1870", precision="year"),
        observations=[_obs("1850", "1855"), _obs("1865", "1870")],
        role_in_household="Dräng",
        notes="Anteckning",
        origins=copy.deepcopy(o_main),
    )
    same = ResidenceFact(
        id="residence_same",
        person_id="person_1",
        place_id="place_1",
        start=Endpoint(earliest="1871", latest="1871", precision="year"),
        end=Endpoint(earliest="1875", latest="1875", precision="year"),
        observations=[_obs("1871", "1875")],
        origins=copy.deepcopy(o_same),
    )
    nxt = (
        ResidenceFact(
            id="residence_next",
            person_id="person_1",
            place_id="place_2",
            start=Endpoint(earliest="1871", latest="1871", precision="year"),
            end=Endpoint(earliest="1880", latest="1880", precision="year"),
            origins=copy.deepcopy(o_next),
        )
        if with_neighbour
        else None
    )
    data = ProjectData(project=ProjectMetadata(title="T"))
    data.places = [
        Place(id="place_1", type="unknown", name="Ljusdal"),
        Place(id="place_2", type="unknown", name="Gävle"),
    ]
    data.residences = [main, same] + ([nxt] if nxt else [])
    return data, main, same, nxt


_GAP = CoverageGap(
    residence_id="residence_main",
    first_year=1856,
    last_year=1864,
    suggestion="",
    splittable=True,
)


def _expected_merge(earlier: list[RecordOrigin], later: list[RecordOrigin]) -> list:
    """Requirement 22.22: earlier origins, then later ones with a new key."""
    expected = list(earlier)
    seen = {origin_key(o) for o in expected}
    for origin in later:
        if origin_key(origin) not in seen:
            seen.add(origin_key(origin))
            expected.append(origin)
    return copy.deepcopy(expected)


def _project_fact(data: ProjectData, rid: str) -> ResidenceFact:
    return next(r for r in data.residences if r.id == rid)


def _check_pure_operations(
    main: ResidenceFact, same: ResidenceFact
) -> None:
    """Every pure edit operation of ``residence_edit_ops``."""
    original = copy.deepcopy(main.origins)
    obs = _obs("1851", "1853")

    # Operations that keep the id keep ``origins`` unchanged.
    for kept in (
        attach_observations(main, [obs]),
        use_as_exact_start(main, main.observations[0]),
        use_as_exact_end(main, main.observations[1]),
        remove_observation(main, 0),
    ):
        assert kept.id == main.id
        assert kept.origins == original

    # A split gives both halves a complete copy, every field included.
    first, second = split_at_gap(copy.deepcopy(main), _GAP, ("residence_a", "residence_b"))
    assert first.origins == original and second.origins == original
    assert first.origins is not second.origins
    if original:
        assert first.origins[0] is not second.origins[0]

    # A merge: earlier origins, then later ones with a new Origin_Key. The
    # order of the arguments does not matter, the timeline decides.
    expected = _expected_merge(main.origins, same.origins)
    for args in ((main, same), (same, main)):
        merged, _ = merge(copy.deepcopy(args[0]), copy.deepcopy(args[1]), "residence_m")
        assert merged.origins == expected
        pool = main.origins + same.origins
        for origin in merged.origins:  # no origin field changes
            assert origin in pool

    # The inputs are left unchanged.
    assert main.origins == original


# ---------------------------------------------------------------------------
# Property 25
# ---------------------------------------------------------------------------


@st.composite
def _origin_lists(draw) -> list[RecordOrigin]:
    """Zero to three origins, an equal one added at times."""
    origins = draw(st.lists(residence_origins, max_size=3))
    if origins and draw(st.booleans()):
        origins.append(copy.deepcopy(origins[draw(st.integers(0, len(origins) - 1))]))
    return origins


# Feature: data-integrity-0-3-0, Property 25: Residence origins survive every residence edit operation
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(o_main=_origin_lists(), o_same=_origin_lists(), o_next=_origin_lists())
def test_dp_property_25_residence_origins_survive_every_edit_operation(
    qapp, o_main: list[RecordOrigin], o_same: list[RecordOrigin], o_next: list[RecordOrigin]
) -> None:
    """**Validates: Requirements 22.22, 22.29**"""
    data, main, same, nxt = _scenario(o_main, o_same, o_next)
    _check_pure_operations(main, same)

    # Residence_Editor: save, role change and flytt link keep the id.
    editor = ResidenceEditor(data, residence=main, person_id="person_1")
    editor._role_edit.setText("Hemmansägare")
    assert editor.build_fact_from_fields().origins == o_main
    assert editor.save_with_warnings()
    saved = _project_fact(data, main.id)
    assert saved.role_in_household == "Hemmansägare"
    assert saved.origins == o_main
    editor._on_create_flytt()
    assert _project_fact(data, main.id).end.event_id is not None
    assert _project_fact(data, main.id).origins == o_main
    assert _project_fact(data, nxt.id).start.event_id is not None
    assert _project_fact(data, nxt.id).origins == o_next
    assert _project_fact(data, same.id).origins == o_same


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------

_ORIGINS_MAIN = [_origin(1), _origin(2, instance=1)]
_ORIGINS_SAME = [_origin(2, instance=1), _origin(3)]
_ORIGINS_NEXT = [_origin(4, instance=2)]


def test_residence_origins_survive_every_edit_operation(
    qapp, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Dialogs are not part of the test: accept every question.
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

    data, main, same, nxt = _scenario(_ORIGINS_MAIN, _ORIGINS_SAME, _ORIGINS_NEXT)
    _check_pure_operations(main, same)

    # Editor save, role change, flytt link, then split and merge in the editor.
    editor = ResidenceEditor(data, residence=main, person_id="person_1")
    editor._role_edit.setText("Inhysing")
    editor.save_with_warnings()
    assert _project_fact(data, main.id).origins == _ORIGINS_MAIN
    editor._on_create_flytt()
    assert _project_fact(data, main.id).origins == _ORIGINS_MAIN
    assert _project_fact(data, nxt.id).origins == _ORIGINS_NEXT
    editor._on_split()
    halves = [r for r in data.residences if r.id not in (same.id, nxt.id)]
    assert len(halves) == 2
    assert all(h.origins == _ORIGINS_MAIN for h in halves)
    # The loaded half merges with the first residence of the same person and
    # place in collection order, which is ``same`` (the other half comes later).
    other_half = next(h for h in halves if h.id != editor.residence.id)
    editor._on_merge()
    ids = {r.id for r in data.residences}
    assert same.id not in ids and halves[0].id not in ids
    merged = editor.residence
    assert merged.origins == [_origin(1), _origin(2, instance=1), _origin(3)]
    assert _project_fact(data, other_half.id).origins == _ORIGINS_MAIN
    assert _project_fact(data, nxt.id).origins == _ORIGINS_NEXT


def test_residence_editor_save_keeps_origins(qapp) -> None:
    data, main, _, _ = _scenario(_ORIGINS_MAIN, [], [])
    editor = ResidenceEditor(data, residence=main, person_id="person_1")
    assert editor.build_fact_from_fields().origins == _ORIGINS_MAIN
    editor._role_edit.setText("Hemmansägare")
    assert editor.save_with_warnings()
    saved = _project_fact(data, main.id)
    assert saved.role_in_household == "Hemmansägare"
    assert saved.origins == _ORIGINS_MAIN
    assert saved.notes == "Anteckning"
    # The Person_Editor dialog saves the fact that the editor builds.
    rebuilt = replace(editor.build_fact_from_fields(), place_id="place_2")
    assert rebuilt.origins == _ORIGINS_MAIN
    # A new residence typed by the user has no origins.
    fresh = ResidenceEditor(data, person_id="person_1")
    assert fresh.build_fact_from_fields().origins == []


def test_residence_split_gives_both_halves_the_origins() -> None:
    main = _scenario(_ORIGINS_MAIN, [], [])[1]
    first, second = split_at_gap(main, _GAP, ("residence_a", "residence_b"))
    assert first.origins == _ORIGINS_MAIN
    assert second.origins == _ORIGINS_MAIN
    assert [o.instance for o in first.origins] == [0, 1]
    assert first.origins is not second.origins
    # The editor path splits the same way and loads the first half.
    assert coverage_gaps(main, _scenario(_ORIGINS_MAIN, [], [])[0])[0].splittable


def test_residence_merge_combines_origins() -> None:
    _, main, same, _ = _scenario(_ORIGINS_MAIN, _ORIGINS_SAME, [])
    merged, _ = merge(main, same, "residence_m")
    # Earlier origins first; the Origin_Key shared by both appears once.
    assert merged.origins == [_origin(1), _origin(2, instance=1), _origin(3)]
    # Two split halves merge back to one origin.
    first, second = split_at_gap(main, _GAP, ("residence_a", "residence_b"))
    again, _ = merge(first, second, "residence_n")
    assert again.origins == _ORIGINS_MAIN
    # The same record at another instance is another origin.
    other = replace(same, origins=[_origin(1, instance=1)])
    merged_other, _ = merge(main, other, "residence_o")
    assert merged_other.origins == [*_ORIGINS_MAIN, _origin(1, instance=1)]


# ---------------------------------------------------------------------------
# Construction guard
# ---------------------------------------------------------------------------

_GUARDED_SCOPE = ("ui", "services")


def _unmarked_constructions(source: str | bytes, rel: str) -> list[tuple[str, str]]:
    """``(rel, function)`` of each ``ResidenceFact(...)`` call without ``origins=``."""
    tree = ast.parse(source)
    found: list[tuple[str, str]] = []

    def visit(node: ast.AST, function: str) -> None:
        for child in ast.iter_child_nodes(node):
            name = function
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = child.name
            if isinstance(child, ast.Call):
                func = child.func
                called = (
                    func.id
                    if isinstance(func, ast.Name)
                    else func.attr
                    if isinstance(func, ast.Attribute)
                    else ""
                )
                has_origins = any(k.arg == "origins" for k in child.keywords)
                if called == "ResidenceFact" and not has_origins:
                    found.append((rel, function))
            visit(child, name)

    visit(tree, "<module>")
    return found


def _scan_application() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for scope in _GUARDED_SCOPE:
        for path in sorted((_PACKAGE / scope).rglob("*.py")):
            rel = path.relative_to(_REPO).as_posix()
            found.extend(_unmarked_constructions(path.read_bytes(), rel))
    return found


def test_guard_residence_construction_preserves_origins() -> None:
    allowed = {(module, function) for module, function, _ in RESIDENCE_CONSTRUCTION_ALLOWLIST}
    for _, _, reason in RESIDENCE_CONSTRUCTION_ALLOWLIST:
        assert reason.strip()
    found = _scan_application()
    violations = sorted(set(found) - allowed)
    assert violations == [], (
        "ResidenceFact(...) without origins= outside the allow-list; copy the "
        "origins of an existing fact (dataclasses.replace) or add a reviewed entry "
        "to residence_construction_allowlist.py:\n"
        + "\n".join(f"{m} in {f}" for m, f in violations)
    )
    # Every entry names a construction that still exists.
    stale = sorted(allowed - set(found))
    assert stale == [], f"stale allow-list entries: {stale}"
    # The scanner reports what it should.
    sample = (
        "def a():\n    return ResidenceFact(id='x')\n"
        "def b(f):\n    return ResidenceFact(id='x', origins=list(f.origins))\n"
        "def c(f):\n    return replace(f, role_in_household='r')\n"
    )
    assert _unmarked_constructions(sample, "m.py") == [("m.py", "a")]
