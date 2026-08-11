"""Unit tests for residence checks wiring into the Person_Check_Engine.

Verifies that:
- The three LogicCheckConfig flags default to True (Requirement 5.9).
- The PersonCheckEngine calls check_residence and produces findings.
- Findings are ordered by first uncovered year ascending with open-endpoint
  findings sorted last (Requirement 5.9).
- Each flag gates its category independently.
- The deserialization of settings includes the three new flags.
"""

from slaktbusken.model.event import DateValue, Event, Participant, SourceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.source import Source, StructuredReference
from slaktbusken.persistence.settings_io import (
    LogicCheckConfig,
    PersonCheckConfig,
    _deserialize_settings,
)
from slaktbusken.services.checks.residence_checks import check_residence
from slaktbusken.services.person_check_engine import (
    CheckContext,
    CheckFinding,
    PersonCheckEngine,
)


# --- Helpers ---


def _person(person_id="person_1"):
    return Person(id=person_id, sex="M", names=[Name(type="birth", given="Anders", surname="Andersson")])


def _observation(observed_from="", observed_to="", source_id="source_1"):
    return Observation(
        source_ref=SourceRef(source_id=source_id, quality="secondary"),
        observed_from=observed_from,
        observed_to=observed_to,
    )


def _fact(
    observations,
    residence_id="residence_1",
    person_id="person_1",
    place_id="place_1",
    start=None,
    end=None,
):
    return ResidenceFact(
        id=residence_id,
        person_id=person_id,
        place_id=place_id,
        start=start or Endpoint(),
        end=end or Endpoint(),
        observations=list(observations),
    )


def _make_project_with_gap():
    """A project with one person having a coverage gap (1871-1875)."""
    person = _person()
    place = Place(id="place_1", type="farm", name="Ljusdal Gård")
    source = Source(
        id="source_1",
        provider="AD",
        source_type="church_book",
        title="Ljusdal AI:17",
        structured_reference=StructuredReference(
            fields={"parish": "Ljusdal", "series": "AI", "volume": "17", "years": "1866-1870"}
        ),
    )
    fact = _fact(
        [
            _observation("1866", "1870", source_id="source_1"),
            _observation("1876", "1880", source_id="source_2"),
        ],
        start=Endpoint(earliest="1866", latest="1866"),
        end=Endpoint(earliest="1880", latest="1880"),
    )
    return ProjectData(
        persons=[person],
        places=[place],
        sources=[source],
        residences=[fact],
    )


def _make_project_with_open_endpoints():
    """A project with one person having open endpoints."""
    person = _person()
    place = Place(id="place_1", type="farm", name="Ljusdal Gård")
    fact = _fact(
        [],
        start=Endpoint(earliest=None, latest="1840"),
        end=Endpoint(earliest="1885", latest=None),
    )
    return ProjectData(
        persons=[person],
        places=[place],
        residences=[fact],
    )


def _make_project_with_timeline_gap():
    """A project with two facts for the same person with a timeline gap."""
    person = _person()
    place1 = Place(id="place_1", type="farm", name="Ljusdal")
    place2 = Place(id="place_2", type="farm", name="Delsbo")
    fact1 = _fact(
        [],
        residence_id="r1",
        start=Endpoint(earliest="1840"),
        end=Endpoint(latest="1850"),
    )
    fact2 = _fact(
        [],
        residence_id="r2",
        place_id="place_2",
        start=Endpoint(earliest="1860"),
        end=Endpoint(latest="1870"),
    )
    return ProjectData(
        persons=[person],
        places=[place1, place2],
        residences=[fact1, fact2],
    )


# --- LogicCheckConfig flag defaults ---


def test_residence_coverage_gaps_flag_defaults_to_true():
    config = LogicCheckConfig()
    assert config.residence_coverage_gaps is True


def test_residence_open_endpoints_flag_defaults_to_true():
    config = LogicCheckConfig()
    assert config.residence_open_endpoints is True


def test_residence_timeline_gaps_flag_defaults_to_true():
    config = LogicCheckConfig()
    assert config.residence_timeline_gaps is True


# --- Settings deserialization includes the new flags ---


def test_deserialization_reads_residence_flags_from_json():
    raw = {
        "person_check_config": {
            "logic_checks": {
                "residence_coverage_gaps": False,
                "residence_open_endpoints": False,
                "residence_timeline_gaps": False,
            }
        }
    }
    settings = _deserialize_settings(raw)
    logic = settings.person_check_config.logic_checks
    assert logic.residence_coverage_gaps is False
    assert logic.residence_open_endpoints is False
    assert logic.residence_timeline_gaps is False


def test_deserialization_defaults_residence_flags_when_absent():
    raw = {"person_check_config": {"logic_checks": {}}}
    settings = _deserialize_settings(raw)
    logic = settings.person_check_config.logic_checks
    assert logic.residence_coverage_gaps is True
    assert logic.residence_open_endpoints is True
    assert logic.residence_timeline_gaps is True


# --- check_residence function directly ---


def test_check_residence_returns_gap_findings():
    data = _make_project_with_gap()
    person = data.persons[0]
    config = PersonCheckConfig()
    context = CheckContext(project_data=data)

    findings = check_residence(person, [], [], config, context)

    assert len(findings) >= 1
    assert any("saknar källa" in f.message for f in findings)


def test_check_residence_returns_open_endpoint_findings():
    data = _make_project_with_open_endpoints()
    person = data.persons[0]
    config = PersonCheckConfig()
    context = CheckContext(project_data=data)

    findings = check_residence(person, [], [], config, context)

    assert len(findings) >= 1
    assert any("början" in f.message or "slutet" in f.message for f in findings)


def test_check_residence_returns_timeline_gap_findings():
    data = _make_project_with_timeline_gap()
    person = data.persons[0]
    config = PersonCheckConfig()
    context = CheckContext(project_data=data)

    findings = check_residence(person, [], [], config, context)

    assert len(findings) >= 1
    assert any("täcker inte" in f.message for f in findings)


def test_check_residence_returns_empty_when_no_data():
    data = ProjectData(persons=[_person()])
    person = data.persons[0]
    config = PersonCheckConfig()
    context = CheckContext(project_data=data)

    findings = check_residence(person, [], [], config, context)

    assert findings == []


def test_check_residence_returns_empty_when_all_flags_disabled():
    data = _make_project_with_gap()
    person = data.persons[0]
    config = PersonCheckConfig(
        logic_checks=LogicCheckConfig(
            residence_coverage_gaps=False,
            residence_open_endpoints=False,
            residence_timeline_gaps=False,
        )
    )
    context = CheckContext(project_data=data)

    findings = check_residence(person, [], [], config, context)

    assert findings == []


def test_check_residence_returns_empty_when_context_has_no_project_data():
    person = _person()
    config = PersonCheckConfig()
    context = CheckContext()  # project_data is None

    findings = check_residence(person, [], [], config, context)

    assert findings == []


# --- Flag gating ---


def test_only_coverage_gaps_flag_gates_gap_findings():
    data = _make_project_with_gap()
    person = data.persons[0]
    config = PersonCheckConfig(
        logic_checks=LogicCheckConfig(
            residence_coverage_gaps=True,
            residence_open_endpoints=False,
            residence_timeline_gaps=False,
        )
    )
    context = CheckContext(project_data=data)

    findings = check_residence(person, [], [], config, context)

    assert len(findings) >= 1
    assert all("saknar källa" in f.message for f in findings)


def test_only_open_endpoints_flag_gates_open_findings():
    data = _make_project_with_open_endpoints()
    person = data.persons[0]
    config = PersonCheckConfig(
        logic_checks=LogicCheckConfig(
            residence_coverage_gaps=False,
            residence_open_endpoints=True,
            residence_timeline_gaps=False,
        )
    )
    context = CheckContext(project_data=data)

    findings = check_residence(person, [], [], config, context)

    assert len(findings) >= 1
    assert all("början" in f.message or "slutet" in f.message for f in findings)


def test_only_timeline_gaps_flag_gates_timeline_findings():
    data = _make_project_with_timeline_gap()
    person = data.persons[0]
    config = PersonCheckConfig(
        logic_checks=LogicCheckConfig(
            residence_coverage_gaps=False,
            residence_open_endpoints=False,
            residence_timeline_gaps=True,
        )
    )
    context = CheckContext(project_data=data)

    findings = check_residence(person, [], [], config, context)

    assert len(findings) >= 1
    assert all("täcker inte" in f.message for f in findings)


# --- Ordering: first uncovered year ascending, open-endpoints last ---


def test_findings_ordered_by_first_year_with_open_endpoints_last():
    """Coverage gaps and timeline gaps ordered by year; open-endpoint findings last."""
    person = _person()
    place = Place(id="place_1", type="farm", name="Ljusdal")
    source = Source(
        id="source_1",
        provider="AD",
        source_type="church_book",
        title="Ljusdal AI:17",
        structured_reference=StructuredReference(
            fields={"parish": "Ljusdal", "series": "AI", "volume": "17", "years": "1866-1870"}
        ),
    )
    # Fact with a coverage gap AND an open endpoint
    fact = ResidenceFact(
        id="r1",
        person_id="person_1",
        place_id="place_1",
        start=Endpoint(earliest=None, latest="1866"),  # open start
        end=Endpoint(earliest="1880", latest="1880"),
        observations=[
            _observation("1866", "1870", source_id="source_1"),
            _observation("1876", "1880", source_id="source_2"),
        ],
    )
    data = ProjectData(
        persons=[person],
        places=[place],
        sources=[source],
        residences=[fact],
    )
    config = PersonCheckConfig()
    context = CheckContext(project_data=data)

    findings = check_residence(person, [], [], config, context)

    # Should have at least one gap finding (year 1871) and one open-endpoint finding
    gap_findings = [f for f in findings if "saknar källa" in f.message]
    open_findings = [f for f in findings if "början" in f.message or "slutet" in f.message]

    assert len(gap_findings) >= 1
    assert len(open_findings) >= 1

    # Open-endpoint findings should be at the end
    first_open_idx = next(
        i for i, f in enumerate(findings)
        if "början" in f.message or "slutet" in f.message
    )
    last_gap_idx = max(
        i for i, f in enumerate(findings)
        if "saknar källa" in f.message or "täcker inte" in f.message
    )
    assert first_open_idx > last_gap_idx


# --- PersonCheckEngine integration ---


def test_engine_produces_residence_findings():
    """The PersonCheckEngine integrates check_residence and produces findings."""
    data = _make_project_with_gap()
    config = PersonCheckConfig()

    engine = PersonCheckEngine(data, config)
    findings = engine.run_checks()

    residence_findings = [f for f in findings if "saknar källa" in f.message]
    assert len(residence_findings) >= 1


def test_engine_skips_residence_checks_when_all_flags_disabled():
    """The PersonCheckEngine returns no residence findings when flags are off."""
    data = _make_project_with_gap()
    config = PersonCheckConfig(
        logic_checks=LogicCheckConfig(
            residence_coverage_gaps=False,
            residence_open_endpoints=False,
            residence_timeline_gaps=False,
        )
    )

    engine = PersonCheckEngine(data, config)
    findings = engine.run_checks()

    residence_findings = [f for f in findings if "saknar källa" in f.message]
    assert residence_findings == []
