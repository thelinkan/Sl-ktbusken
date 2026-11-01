"""Inventory completeness tests (Mandatory group a: reference preservation).

Requirements 1.8, 35.1, 35.2.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, is_dataclass

import pytest

import slaktbusken.model as model_pkg
from slaktbusken.services.person_reference_index import (
    find_unlisted_person_reference_fields,
)

pytestmark = pytest.mark.mandatory_integrity


def _model_dataclasses() -> list[type]:
    """Every dataclass defined in a ``slaktbusken.model`` module."""
    classes: dict[str, type] = {}
    for info in pkgutil.iter_modules(model_pkg.__path__):
        module = importlib.import_module(f"{model_pkg.__name__}.{info.name}")
        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and is_dataclass(obj)
                and obj.__module__ == module.__name__
            ):
                classes[f"{obj.__module__}.{obj.__qualname__}"] = obj
    return list(classes.values())


def test_inventory_lists_every_person_reference_field():
    classes = _model_dataclasses()
    assert classes, "no model dataclasses found; the reflection is broken"
    unlisted = find_unlisted_person_reference_fields(classes)
    assert unlisted == [], (
        "Person-reference fields missing from the Person_Reference_Inventory "
        f"and the allow-list: {unlisted}"
    )


def test_inventory_check_fails_for_unlisted_field():
    @dataclass
    class SyntheticReference:
        person_id: str = ""
        other_person_ids: list = None  # type: ignore[assignment]

    unlisted = find_unlisted_person_reference_fields([SyntheticReference])
    assert "SyntheticReference.person_id" in unlisted
    assert "SyntheticReference.other_person_ids" in unlisted


# --- Task 13.18: a row without a handler refuses the merge -------------------


def _handler_check_service(tmp_path):
    from slaktbusken.model.person import Name, Person
    from slaktbusken.persistence import translation_io
    from slaktbusken.persistence.translation_io import PersonMapping
    from slaktbusken.services.project_service import ProjectService

    svc = ProjectService()
    svc.create_project("Test", tmp_path)
    for pid in ("person_1", "person_2"):
        svc.data.persons.append(Person(id=pid, sex="F", names=[Name("birth", "Anna", "Berg")]))
    translation_io.write_persons(
        [PersonMapping("@I2@", "person_2", "fp2")], [],
        svc.project_path.parent / "translation" / "persons.json",
    )
    svc._dirty = True
    svc.save_project()
    return svc


def _handler_check_state(svc):
    import copy
    import copy
    import hashlib

    root = svc.project_path.parent
    files = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }
    return (
        copy.deepcopy(svc.data), files, svc.is_dirty, svc.is_saved_state(),
        svc.revision, svc.content_revision,
    )


def test_merge_refused_when_handler_missing(tmp_path, monkeypatch):
    from slaktbusken.persistence import translation_io
    from slaktbusken.services import person_reference_index as pri
    from slaktbusken.services.merge_engine import MergeEngine
    from slaktbusken.services.merge_planner import MergeDecisions, build_plan

    svc = _handler_check_service(tmp_path)
    translation = translation_io.read_all(svc.project_path.parent / "translation")
    decisions = MergeDecisions(
        "person_1", "person_2", survivor_id="person_1", survivor_confirmed=True
    )
    plan = build_plan(svc.data, translation, decisions, svc.content_revision)
    assert plan.can_execute

    temp_row = pri._loc(
        "synthetic.temporary_row", "SyntheticOwner", "friend_person_id", "R", "none",
        "Temporary row used by the handler check test.",
    )
    assert temp_row.requires_handler
    assert temp_row.key not in pri.HANDLER_REGISTRY
    monkeypatch.setattr(
        pri, "PERSON_REFERENCE_INVENTORY", pri.PERSON_REFERENCE_INVENTORY + (temp_row,)
    )
    before = _handler_check_state(svc)

    outcome = MergeEngine(svc, None).execute(plan)

    assert not outcome.success
    assert "synthetic.temporary_row" in outcome.message
    assert "SyntheticOwner.friend_person_id" in outcome.message
    assert _handler_check_state(svc) == before
    assert [p.id for p in svc.data.persons] == ["person_1", "person_2"]
