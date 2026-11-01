"""Example tests for identity alias read/write in persons.json.

**Validates: Requirements 30.2, 30.3**
"""

from __future__ import annotations

import json
from pathlib import Path

from slaktbusken.persistence.translation_io import (
    FamilyMapping,
    IdentityAlias,
    PersonMapping,
    TranslationData,
    dumps_persons,
    read_all,
    read_person_aliases,
    read_persons,
    write_all,
    write_persons,
)

PERSONS = [
    PersonMapping("@I1@", "person_1", "fp1"),
    PersonMapping("@I2@", "person_2", None),
]
FAMILIES = [FamilyMapping("@F1@", "family_001")]
ALIASES = [
    IdentityAlias("@I7@", "fp7", "person_1", "merge_1"),
    IdentityAlias("@I8@", None, "person_2", "merge_2"),
]


def test_file_without_aliases(tmp_path: Path) -> None:
    path = tmp_path / "persons.json"
    write_persons(PERSONS, FAMILIES, path)

    assert "identity_aliases" not in json.loads(path.read_text(encoding="utf-8"))
    assert read_person_aliases(path) == []
    assert read_persons(path) == (PERSONS, FAMILIES)

    # Reading then writing gives equal content.
    before = path.read_bytes()
    persons, families = read_persons(path)
    write_persons(persons, families, path, read_person_aliases(path))
    assert path.read_bytes() == before


def test_missing_file_gives_no_aliases(tmp_path: Path) -> None:
    assert read_person_aliases(tmp_path / "persons.json") == []


def test_aliases_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "persons.json"
    write_persons(PERSONS, FAMILIES, path, ALIASES)

    assert read_person_aliases(path) == ALIASES
    assert read_persons(path) == (PERSONS, FAMILIES)

    before = path.read_bytes()
    persons, families = read_persons(path)
    write_persons(persons, families, path, read_person_aliases(path))
    assert path.read_bytes() == before


def test_write_all_read_all_round_trip(tmp_path: Path) -> None:
    data = TranslationData(
        persons=list(PERSONS), families=list(FAMILIES), person_aliases=list(ALIASES)
    )
    write_all(data, tmp_path)
    loaded = read_all(tmp_path)
    assert loaded.person_aliases == ALIASES
    assert loaded.persons == PERSONS
    assert loaded.families == FAMILIES


def test_dumps_persons_equals_written_bytes(tmp_path: Path) -> None:
    for aliases in (None, [], ALIASES):
        path = tmp_path / "persons.json"
        write_persons(PERSONS, FAMILIES, path, aliases)
        assert path.read_bytes() == dumps_persons(PERSONS, FAMILIES, aliases)
