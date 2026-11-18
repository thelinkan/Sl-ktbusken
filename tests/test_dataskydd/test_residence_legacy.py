"""Legacy residences and the exact-content claim (Requirement 22.6, 22.16).

A legacy residence has no ``origins``. An incoming ``RESI`` record claims it
only when its content equals what the importer derives from the record, one to
one. The example tests use the 0.4 fixture, which holds duplicated residences.
"""

from __future__ import annotations

import copy
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from slaktbusken.gedcom.importer import GEDCOMImporter, ImportResult
from slaktbusken.gedcom.translation.record_identity import residence_fingerprint
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.record_origin import origin_key
from slaktbusken.model.residence import Endpoint, ResidenceFact
from slaktbusken.persistence.file_io import FilePersistence
from slaktbusken.persistence.translation_io import PersonMapping, write_persons
from slaktbusken.services.import_service import ImportService
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.validation_service import ValidationService

pytestmark = pytest.mark.mandatory_integrity

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "project_v0_4.json.gz"

_HEAD = "0 HEAD\n1 CHAR UTF-8\n"
_FIXTURE_RESI = "1 RESI\n2 DATE FROM 1860 TO 1880\n2 PLAC Backa\n"


def _fixture_gedcom(*records: str) -> str:
    """A file with the fixture's person_2 (``@I2@``) and *records*."""
    return (
        _HEAD
        + "0 @I2@ INDI\n1 NAME Förnamn2 /Testsson/\n1 SEX F\n"
        + "".join(records)
        + "0 TRLR\n"
    )


class FixtureEnv:
    """The 0.4 fixture, a translation folder mapping ``@I2@`` to person_2."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        shutil.copy2(FIXTURE, tmp_path / "project.json.gz")
        self.project: ProjectData = FilePersistence.load(tmp_path / "project.json.gz")
        self.tdir = tmp_path / "translation"
        self.tdir.mkdir()
        write_persons(
            [PersonMapping(gedcom_id="@I2@", app_id="person_2")], [], self.tdir / "persons.json"
        )
        self.path = tmp_path / "t.ged"

    def legacy(self, rid: str) -> ResidenceFact:
        return next(r for r in self.project.residences if r.id == rid)

    def make_claimable(self, *ids: str) -> None:
        """Give the named fixture residences the content that the importer
        derives from ``_FIXTURE_RESI`` (the fixture sets an event link and an
        exact start, which a RESI record never produces)."""
        for rid in ids:
            fact = self.legacy(rid)
            fact.start = Endpoint(earliest=None, latest="1860", precision="year")
            fact.end = Endpoint(earliest="1880", latest=None, precision="year")

    def run(self, text: str) -> ImportResult:
        self.path.write_text(text, encoding="utf-8")
        return GEDCOMImporter(self.project, self.tdir).import_file(self.path)


@pytest.fixture
def fenv(tmp_path: Path) -> FixtureEnv:
    return FixtureEnv(tmp_path)


def _log(result: ImportResult) -> str:
    return "\n".join(str(w) for w in result.warnings)


def _without_origins(fact: ResidenceFact) -> ResidenceFact:
    return replace(fact, origins=[])


# ---------------------------------------------------------------------------
# Examples on the 0.4 fixture
# ---------------------------------------------------------------------------


def test_legacy_residence_exact_match_is_claimed_once(fenv: FixtureEnv) -> None:
    fenv.project.residences.remove(fenv.legacy("residence_4"))
    fenv.make_claimable("residence_3")
    before = copy.deepcopy(fenv.legacy("residence_3"))
    text = _fixture_gedcom(_FIXTURE_RESI)

    first = fenv.run(text)
    assert first.residences_claimed == 1
    assert first.residences_added == 0
    claimed = fenv.legacy("residence_3")
    assert len(claimed.origins) == 1
    assert claimed.origins[0].tag_key == "RESI"
    assert claimed.origins[0].owner_id == "person_2"
    assert _without_origins(claimed) == before
    origins = copy.deepcopy(claimed.origins)

    second = fenv.run(text)
    assert second.residences_claimed == 0
    assert second.residences_added == 0
    assert fenv.legacy("residence_3").origins == origins


def test_legacy_residence_with_different_content_is_not_claimed(fenv: FixtureEnv) -> None:
    # Fixture content: exact start 1860 and an Endpoint link to event_4.
    before = {r.id: copy.deepcopy(r) for r in fenv.project.residences}
    result = fenv.run(_fixture_gedcom(_FIXTURE_RESI))
    assert result.residences_claimed == 0
    assert result.residences_added == 1
    for rid, fact in before.items():
        assert fenv.legacy(rid) == fact
        assert fenv.legacy(rid).origins == []
    new = [r for r in fenv.project.residences if r.id not in before]
    assert len(new) == 1 and len(new[0].origins) == 1


def test_legacy_residence_same_date_and_place_but_different_role_is_not_claimed(
    fenv: FixtureEnv,
) -> None:
    fenv.make_claimable("residence_3", "residence_4")
    fenv.legacy("residence_3").role_in_household = "Hemmansägare"
    fenv.legacy("residence_4").role_in_household = "Dräng"
    before = {r.id: copy.deepcopy(r) for r in fenv.project.residences}
    result = fenv.run(_fixture_gedcom(_FIXTURE_RESI))
    assert result.residences_claimed == 0
    assert result.residences_added == 1
    for rid, fact in before.items():
        assert fenv.legacy(rid) == fact


def test_legacy_duplicates_are_kept_and_reported(fenv: FixtureEnv) -> None:
    fenv.make_claimable("residence_3", "residence_4")
    count = len(fenv.project.residences)
    result = fenv.run(_fixture_gedcom(_FIXTURE_RESI))
    assert result.residences_claimed == 1
    assert result.residences_added == 0
    assert len(fenv.project.residences) == count
    pair = [fenv.legacy("residence_3"), fenv.legacy("residence_4")]
    assert sorted(len(r.origins) for r in pair) == [0, 1]
    # The unclaimed duplicate is unchanged, so both still have equal content.
    assert replace(pair[0], id="", origins=[]) == replace(pair[1], id="", origins=[])
    log = _log(result)
    assert "1 identiska boenden för" in log
    assert "Testsson" in log
    assert "lämnades orörda. De kan vara dubbletter från tidigare importer." in log


def test_legacy_claim_reported_in_import_log(fenv: FixtureEnv) -> None:
    fenv.make_claimable("residence_3", "residence_4")
    text = _fixture_gedcom(_FIXTURE_RESI, _FIXTURE_RESI)
    result = fenv.run(text)
    assert result.residences_claimed == 2
    assert (
        "2 befintliga boenden kopplades till GEDCOM-posterna och fick ursprungsmärkning."
        in _log(result)
    )
    again = fenv.run(text)
    assert "kopplades till GEDCOM-posterna" not in _log(again)


def test_legacy_claim_marks_project_changed(fenv: FixtureEnv) -> None:
    fenv.make_claimable("residence_3")
    fenv.project.residences.remove(fenv.legacy("residence_4"))
    text = _fixture_gedcom(_FIXTURE_RESI)
    # Bring the translation files up to date on a scratch copy, so that the
    # claim is the only change that the service run below can detect.
    scratch = copy.deepcopy(fenv.project)
    fenv.path.write_text(text, encoding="utf-8")
    GEDCOMImporter(scratch, fenv.tdir).import_file(fenv.path)
    assert scratch.residences[2].origins

    ps = ProjectService()
    ps._project_data = fenv.project
    service = ImportService(ValidationService())
    assert not ps.is_dirty
    result = service.run(fenv.project, fenv.path, fenv.tmp, ps)
    assert result.residences_claimed == 1
    assert ps.is_dirty
    assert fenv.legacy("residence_3").origins

    ps._dirty_value = False
    again = service.run(ps.data, fenv.path, fenv.tmp, ps)
    assert again.residences_claimed == 0
    assert not ps.is_dirty


# ---------------------------------------------------------------------------
# Property 26
# ---------------------------------------------------------------------------

_DATE = "FROM 1 JAN 1850 TO 1 JAN 1860"
_VARIANTS = (
    f"1 RESI\n2 DATE {_DATE}\n2 PLAC Ljusdal\n",
    f"1 RESI\n2 DATE {_DATE}\n2 PLAC Gävle\n",
    "1 RESI\n2 DATE FROM 1 JAN 1870 TO 1 JAN 1880\n2 PLAC Ljusdal\n",
)
_MUTATIONS = ("none", "role", "notes", "event")


def _mutate(fact: ResidenceFact, mutation: str) -> ResidenceFact:
    if mutation == "role":
        return replace(fact, role_in_household="Dräng")
    if mutation == "notes":
        return replace(fact, notes="Egen anteckning")
    if mutation == "event":
        return replace(fact, end=replace(fact.end, event_id="event_user"))
    return fact


def _person_file(*records: str) -> str:
    return (
        _HEAD
        + "0 @I1@ INDI\n1 NAME Johan /Andersson/\n1 SEX M\n"
        + "".join(records)
        + "0 TRLR\n"
    )


# Feature: data-integrity-0-3-0, Property 26: A legacy residence is claimed only on exact content, one to one
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(
    legacy=st.lists(
        st.tuples(st.integers(0, 2), st.sampled_from(_MUTATIONS)), max_size=5
    ),
    incoming=st.lists(st.integers(0, 2), min_size=1, max_size=5),
)
def test_dp_property_26_legacy_residence_claimed_only_on_exact_content_one_to_one(
    legacy: list[tuple[int, str]], incoming: list[int]
) -> None:
    """**Validates: Requirements 22.6, 22.8, 22.16, 22.25, 22.30**"""
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        tdir = tmp / "translation"
        tdir.mkdir()
        path = tmp / "t.ged"
        project = ProjectData(project=ProjectMetadata(title="T"))

        def run(text: str) -> ImportResult:
            path.write_text(text, encoding="utf-8")
            return GEDCOMImporter(project, tdir).import_file(path)

        # One residence per variant, made by the importer, are the templates.
        run(_person_file(*_VARIANTS))
        templates = [replace(r, origins=[]) for r in project.residences]
        assert len(templates) == len(_VARIANTS)
        fingerprints = [residence_fingerprint(t) for t in templates]

        project.residences.clear()
        legacy_facts: list[ResidenceFact] = []
        for n, (variant, mutation) in enumerate(legacy):
            fact = _mutate(copy.deepcopy(templates[variant]), mutation)
            fact.id = f"legacy_{n}"
            legacy_facts.append(fact)
        project.residences.extend(copy.deepcopy(f) for f in legacy_facts)

        result = run(_person_file(*(_VARIANTS[i] for i in incoming)))

        by_id = {r.id: r for r in project.residences}
        claimed = [f for f in legacy_facts if by_id[f.id].origins]
        incoming_fingerprints = {fingerprints[i] for i in incoming}

        # Nothing is removed, merged or reordered.
        assert [r.id for r in project.residences[: len(legacy_facts)]] == [
            f.id for f in legacy_facts
        ]
        for fact in legacy_facts:
            after = by_id[fact.id]
            # A claim changes only ``origins``.
            assert replace(after, origins=[]) == fact
            if after.origins:
                # Exact content only, with one origin that has a RESI tag key.
                assert residence_fingerprint(fact) in incoming_fingerprints
                assert len(after.origins) == 1
                assert after.origins[0].tag_key == "RESI"
                assert after.origins[0].owner_kind == "INDI"
        # Different content is never claimed (role, notes or Endpoint link).
        for fact, (_, mutation) in zip(legacy_facts, legacy):
            if mutation != "none":
                assert not by_id[fact.id].origins
        # One to one: per record content, claims = min(records, equal legacy).
        expected = 0
        for v, fingerprint in enumerate(fingerprints):
            records = sum(1 for i in incoming if i == v)
            equal = sum(
                1
                for fact in legacy_facts
                if residence_fingerprint(fact) == fingerprint
            )
            expected += min(records, equal)
        assert len(claimed) == expected == result.residences_claimed
        assert len(claimed) <= len(incoming)
        # Every record that claims nothing creates one residence.
        assert result.residences_added == len(incoming) - expected
        assert len(project.residences) == len(legacy) + len(incoming) - expected
        # No legacy residence is grouped: every Origin_Key is held once.
        keys = [origin_key(o) for r in project.residences for o in r.origins]
        assert len(keys) == len(set(keys))
        # A second import of the same file changes nothing.
        before = [copy.deepcopy(r) for r in project.residences]
        again = run(_person_file(*(_VARIANTS[i] for i in incoming)))
        assert again.residences_added == 0 and again.residences_claimed == 0
        assert project.residences == before
