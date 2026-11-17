"""Sanity tests for the synthetic project and the strategies (task 1.3)."""

from __future__ import annotations

from pathlib import Path

from hypothesis import given

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.model.validators import validate_placement_end_events
from slaktbusken.persistence.serialization import deserialize, serialize
from slaktbusken.services.validation_service import ValidationService

from tests.test_gedcom_roundtrip.strategies import (
    citation_projects,
    event_projects,
    free_text,
    parentage_projects,
    partner_projects,
    person_projects,
    projects,
    residence_projects,
    source_projects,
)
from tests.test_gedcom_roundtrip.synthetic import QUALITIES, build_synthetic_project
import pytest

pytestmark = pytest.mark.mandatory_integrity


def _messages(data) -> list[str]:
    errors = ValidationService().validate_project(data)
    errors_text = [f"{e.entity_type} {e.entity_id}: {e.message}" for e in errors]
    errors_text += validate_placement_end_events(data.events)
    return errors_text


def test_synthetic_project_validates() -> None:
    assert _messages(build_synthetic_project()) == []


def test_synthetic_project_serializes_and_exports(tmp_path: Path) -> None:
    data = build_synthetic_project()
    text = serialize(data)
    assert serialize(deserialize(text)) == text
    result = GEDCOMExporter().export(data, tmp_path / "synthetic.ged")
    assert (tmp_path / "synthetic.ged").read_text(encoding="utf-8").startswith("0 HEAD")
    assert result is not None


def test_synthetic_project_free_roles_exports(tmp_path: Path) -> None:
    data = build_synthetic_project(free_roles=True)
    roles = {p.role for f in data.families for p in f.partners}
    assert {"make", "maka"} <= roles
    serialize(data)
    GEDCOMExporter().export(data, tmp_path / "free.ged")


def test_synthetic_project_has_the_fixture_shape() -> None:
    data = build_synthetic_project()
    sexes = {p.sex for p in data.persons}
    assert sexes == {"M", "F", "U", "X"}
    pairs = [tuple(data.persons[int(p.person_id.split("_")[1]) - 1].sex
                   for p in f.partners) for f in data.families if len(f.partners) == 2]
    assert ("M", "M") in pairs and ("F", "F") in pairs
    assert any(len(f.partners) == 1 for f in data.families)
    assert any(link.parentage_type == "foster"
               for f in data.families for link in f.parent_child_links)
    assert {"foster_home", "foster_home_ended"} <= {e.type for e in data.events}
    # Two marriages with equal date and place that belong to no family.
    listed = {i for f in data.families for i in f.event_ids}
    orphans = [e for e in data.events if e.type == "marriage" and e.id not in listed]
    keys = [(e.date.value, e.place.place_id) for e in orphans]
    assert len(orphans) == 3 and keys.count(max(set(keys), key=keys.count)) == 2
    # Every quality and every citation context appears.
    qualities, contexts = set(), set()
    from slaktbusken.model.event_citations import event_citations
    for e in data.events:
        for c in event_citations(e):
            qualities.add(c.ref.quality)
            contexts.add(c.context.value)
    for r in data.residences:
        qualities |= {o.source_ref.quality for o in r.observations}
    assert set(QUALITIES) <= qualities
    assert contexts == {"event", "date", "place", "from_place"}
    assert any(c.ref.aspects for e in data.events for c in event_citations(e))
    # One repository shared by two sources.
    repo_users = [s for s in data.sources
                  if any(r.repository_id == data.repositories[0].id
                         for r in s.repository_refs)]
    assert len(repo_users) == 2
    # Residences with endpoints that link to events.
    assert any(r.start.event_id or r.end.event_id for r in data.residences)


def _check_valid(data) -> None:
    assert _messages(data) == []
    text = serialize(data)
    assert serialize(deserialize(text)) == text


# Strategy sanity (no design property): generated projects are valid, so a
# failing property later points at the exporter or importer.
@given(projects())
def test_projects_validate_and_serialize(data) -> None:
    _check_valid(data)


@given(person_projects())
def test_person_projects_validate(data) -> None:
    _check_valid(data)


@given(partner_projects())
def test_partner_projects_validate(data) -> None:
    _check_valid(data)


@given(parentage_projects())
def test_parentage_projects_validate(data) -> None:
    _check_valid(data)


@given(event_projects())
def test_event_projects_validate(data) -> None:
    _check_valid(data)


@given(citation_projects())
def test_citation_projects_validate(data) -> None:
    _check_valid(data)


@given(residence_projects())
def test_residence_projects_validate(data) -> None:
    _check_valid(data)


@given(source_projects())
def test_source_projects_validate(data) -> None:
    _check_valid(data)


@given(partner_projects(free_roles=True))
def test_free_role_projects_serialize_and_export(data) -> None:
    # free_roles projects are not valid by design; they must still serialize.
    serialize(data)


@given(free_text())
def test_free_text_has_no_forbidden_characters(text: str) -> None:
    assert "\r" not in text and "\x00" not in text
    # "\n" is the only line break, so str.splitlines agrees with split("\n").
    assert text.replace("\n", "").splitlines() in ([], [text.replace("\n", "")])
