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
