"""Meta-tests for the compat helper and golden 0.3 fixture tests (Requirements 7.14, 32.1)."""

from __future__ import annotations

import copy
import gzip
import importlib.util
import json
from pathlib import Path

import pytest

from slaktbusken.persistence.file_io import FilePersistence
from slaktbusken.persistence.serialization import serialize
from tests.helpers.compat import (
    PLACEHOLDER,
    assert_equal_except_version_fields,
    normalise_version_fields,
)

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "compat"


def _load_fixture_script():
    spec = importlib.util.spec_from_file_location(
        "make_compat_fixtures", ROOT / "scripts" / "make_compat_fixtures.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SCRIPT = _load_fixture_script()
GOLDEN_NAMES = sorted(_SCRIPT.FIXTURES)


def _before() -> dict:
    return {
        "format": "x",
        "version": "0.3",
        "format_version": "0.3",
        "persons": [{"id": "p1", "version": "a"}],
        "project": {"title": "T"},
    }


def _after() -> dict:
    doc = copy.deepcopy(_before())
    doc["version"] = "0.4"
    doc["format_version"] = "0.4"
    return doc


# ---------------------------------------------------------------- meta-tests


def test_only_version_fields_differ_passes():
    assert_equal_except_version_fields(_before(), _after())


def test_normalise_replaces_only_top_level_values():
    out = normalise_version_fields(_before())
    assert out["version"] == PLACEHOLDER
    assert out["format_version"] == PLACEHOLDER
    assert out["persons"][0]["version"] == "a"


def test_accepts_json_text_and_gzip_bytes():
    text = json.dumps(_before())
    packed = gzip.compress(json.dumps(_after()).encode("utf-8"))
    assert_equal_except_version_fields(text, packed)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(format="y"),
        lambda d: d.update(project={"title": "U"}),
        lambda d: d.update(extra=1),
        lambda d: d.pop("project"),
        lambda d: d["persons"].append({"id": "p2"}),
    ],
)
def test_other_top_level_difference_fails(mutate):
    after = _after()
    mutate(after)
    with pytest.raises(AssertionError):
        assert_equal_except_version_fields(_before(), after)


@pytest.mark.parametrize("key", ["version", "format_version"])
def test_nested_version_key_difference_fails(key):
    before = _before()
    after = _after()
    before["persons"][0][key] = "1"
    after["persons"][0][key] = "2"
    with pytest.raises(AssertionError):
        assert_equal_except_version_fields(before, after)


@pytest.mark.parametrize("key", ["version", "format_version"])
@pytest.mark.parametrize("side", ["before", "after"])
def test_missing_version_fails(key, side):
    before, after = _before(), _after()
    (before if side == "before" else after).pop(key)
    with pytest.raises(AssertionError):
        assert_equal_except_version_fields(before, after)


def test_missing_version_on_one_side_only_does_not_pass_as_equal():
    before, after = _before(), _after()
    del after["version"]
    with pytest.raises(AssertionError):
        assert_equal_except_version_fields(before, after)


@pytest.mark.parametrize("key", ["merge_candidates", "merge_history"])
def test_extra_empty_merge_list_fails(key):
    after = _after()
    after[key] = []
    with pytest.raises(AssertionError, match=key):
        assert_equal_except_version_fields(_before(), after)


def test_inputs_unchanged():
    before, after = _before(), _after()
    before_copy, after_copy = copy.deepcopy(before), copy.deepcopy(after)
    assert_equal_except_version_fields(before, after)
    normalise_version_fields(before)
    assert before == before_copy
    assert after == after_copy


def test_inputs_unchanged_when_failing():
    before, after = _before(), _after()
    after["format"] = "y"
    before_copy, after_copy = copy.deepcopy(before), copy.deepcopy(after)
    with pytest.raises(AssertionError):
        assert_equal_except_version_fields(before, after)
    assert before == before_copy
    assert after == after_copy


def test_before_at_0_4_fails():
    before = _before()
    before["version"] = before["format_version"] = "0.4"
    with pytest.raises(AssertionError):
        assert_equal_except_version_fields(before, _after())


def test_after_at_0_3_fails():
    with pytest.raises(AssertionError):
        assert_equal_except_version_fields(_before(), _before())


def test_list_order_matters():
    before, after = _before(), _after()
    before["persons"] = [{"id": "a"}, {"id": "b"}]
    after["persons"] = [{"id": "b"}, {"id": "a"}]
    with pytest.raises(AssertionError):
        assert_equal_except_version_fields(before, after)


def test_message_lists_at_most_ten_differences():
    before, after = _before(), _after()
    before["many"] = {f"k{i:02d}": i for i in range(25)}
    after["many"] = {f"k{i:02d}": i + 1 for i in range(25)}
    with pytest.raises(AssertionError) as info:
        assert_equal_except_version_fields(before, after)
    assert str(info.value).count("many.k") == 10


# ------------------------------------------------------------- golden tests


def test_golden_files_cover_script():
    assert GOLDEN_NAMES == sorted(p.name for p in FIXTURE_DIR.glob("v0_3_*.json"))


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_golden_load_migrate_save_matches(name, tmp_path):
    golden_text = (FIXTURE_DIR / name).read_text(encoding="utf-8")
    project_file = tmp_path / "golden.json.gz"
    project_file.write_bytes(gzip.compress(golden_text.encode("utf-8")))

    data = FilePersistence.load(project_file)
    FilePersistence.save(data, project_file)

    assert_equal_except_version_fields(golden_text, project_file.read_bytes())


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_golden_matches_project_built_in_code(name):
    golden_text = (FIXTURE_DIR / name).read_text(encoding="utf-8")
    built = _SCRIPT.FIXTURES[name]()
    assert_equal_except_version_fields(golden_text, serialize(built))
