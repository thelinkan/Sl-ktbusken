"""Exporter tests for events: tags, roles, tokens, Individual_Fallback, xrefs.

Validates: Requirements 1.4, 8.1, 8.2, 8.3, 8.4, 8.5, 8.8, 13.5
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.slk_tags import SLK_TAG_REGISTRY
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata

ROOT = Path(__file__).resolve().parents[2]
MERGE_TEST = ROOT / "tests" / "fixtures" / "gedcom_roundtrip" / "MergeTest.json"


def _person(n: int, sex: str = "M") -> Person:
    return Person(
        id=f"person_{n}",
        names=[Name(type="birth", given=f"Namn{n}", surname="Test")],
        sex=sex,
    )


def _project(events, persons=None, families=None) -> ProjectData:
    return ProjectData(
        format="släktbuske-file",
        version="0.2",
        project=ProjectMetadata(title="Test"),
        persons=persons or [_person(1), _person(2, "F"), _person(3)],
        families=families or [],
        events=events,
        places=[
            Place(id="place_1", name="Ljusdal", type="socken"),
            Place(id="place_2", name="Delsbo", type="socken"),
        ],
        sources=[],
    )


def _export(data: ProjectData, tmp_path: Path):
    result = GEDCOMExporter().export(data, tmp_path / "t.ged")
    text = (tmp_path / "t.ged").read_text(encoding="utf-8")
    return text.splitlines(), result


def _marriage(eid: str, ids=(1, 2), date="1900-05-01") -> Event:
    return Event(
        id=eid,
        type="marriage",
        participants=[Participant(f"person_{i}", "spouse") for i in ids],
        date=DateValue(value=date, precision="day"),
    )


def _indi_block(lines: list[str], xref: str) -> list[str]:
    start = lines.index(f"0 {xref} INDI")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("0 ")),
        len(lines),
    )
    return lines[start:end]


def test_missing_tags_and_eid() -> None:
    events = [
        Event(
            id=f"event_{i}",
            type=t,
            participants=[Participant("person_1", "subject")],
        )
        for i, t in enumerate(["confirmation", "will", "blessing", "first_communion"], 1)
    ]
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        lines, _ = _export(_project(events), Path(d))
    block = _indi_block(lines, "@I1@")
    for tag in ("CONF", "WILL", "BLES", "FCOM"):
        assert f"1 {tag}" in block
    for i in range(1, 5):
        assert f"2 _SLK_EID event_{i}" in block
    assert not any("_SLK_ROLE" in line for line in block)


def test_custom_and_other_types_use_even(tmp_path: Path) -> None:
    events = [
        Event("event_1", "custom_individual_event",
              [Participant("person_1", "subject")], custom_type_name="Mönstring"),
        Event("event_2", "name_change", [Participant("person_1", "subject")]),
    ]
    lines, _ = _export(_project(events), tmp_path)
    block = _indi_block(lines, "@I1@")
    i = block.index("2 TYPE Mönstring")
    assert block[i - 1] == "1 EVEN"
    assert not any(line.startswith("2 _SLK_EVTYPE Mönstring") for line in block)
    j = block.index("2 TYPE name_change")
    assert block[j - 1] == "1 EVEN"
    assert "2 _SLK_EVTYPE name_change" in block


def test_role_written_unless_subject_or_placement(tmp_path: Path) -> None:
    events = [
        Event("event_1", "baptism", [
            Participant("person_1", "subject"), Participant("person_2", "gudförälder")]),
        Event("event_2", "foster_home", [Participant("person_1", "fosterbarn")]),
    ]
    lines, _ = _export(_project(events), tmp_path)
    assert "2 _SLK_ROLE gudförälder" in _indi_block(lines, "@I2@")
    assert not any("_SLK_ROLE" in line for line in _indi_block(lines, "@I1@"))
    assert "2 _SLK_EID event_2" in _indi_block(lines, "@I1@")


def test_flytt_from_place(tmp_path: Path) -> None:
    ev = Event(
        "event_1", "flytt", [Participant("person_1", "subject")],
        place=PlaceRef("place_1"), from_place=PlaceRef("place_2"),
    )
    lines, _ = _export(_project([ev]), tmp_path)
    block = _indi_block(lines, "@I1@")
    assert "2 NOTE Från: Delsbo" in block
    assert "2 _SLK_FROMPLAC Delsbo" in block
    assert "2 _SLK_EID event_1" in block


def test_fallback_for_orphan_without_matching_family(tmp_path: Path) -> None:
    ev1 = _marriage("event_1")
    ev2 = _marriage("event_2")  # same date and participants, own token
    lines, result = _export(_project([ev1, ev2]), tmp_path)
    assert not any(line.endswith(" FAM") for line in lines)
    for xref in ("@I1@", "@I2@"):
        block = _indi_block(lines, xref)
        assert block.count("2 _SLK_EVTYPE marriage") == 2
        assert "2 _SLK_EID event_1" in block and "2 _SLK_EID event_2" in block
        assert "2 TYPE Vigsel" in block
        assert "2 _SLK_ROLE spouse" in block
    assert not any("_SLK_EID" in line for line in _indi_block(lines, "@I3@"))
    fallback = [w for w in result.warnings if "Vigsel" in w]
    assert len(fallback) == 2
    assert "1900-05-01" not in fallback[0] and "1 MAY 1900" in fallback[0]
    assert "Namn1 Test" in fallback[0] and "Namn2 Test" in fallback[0]


def test_fallback_for_several_matching_families(tmp_path: Path) -> None:
    fams = [
        Family(id=f"family_{n}", partners=[
            FamilyPartner("person_1", "husband"), FamilyPartner("person_2", "wife")], children=[])
        for n in (1, 2)
    ]
    lines, result = _export(_project([_marriage("event_1")], families=fams), tmp_path)
    assert sum(line.endswith(" FAM") for line in lines) == 2
    assert "2 _SLK_EVTYPE marriage" in _indi_block(lines, "@I1@")
    assert not any(line == "1 MARR" for line in lines)
    assert len(result.warnings) >= 1


def test_matching_family_is_not_fallback(tmp_path: Path) -> None:
    fam = Family(id="family_1", partners=[
        FamilyPartner("person_1", "husband"), FamilyPartner("person_2", "wife")], children=[])
    lines, result = _export(_project([_marriage("event_1")], families=[fam]), tmp_path)
    assert "1 MARR" in lines and "2 _SLK_EID event_1" in lines
    assert not any("_SLK_EVTYPE" in line for line in lines)
    assert not any("Vigsel" in w for w in result.warnings)


def test_only_registered_slk_tags(tmp_path: Path) -> None:
    ev = Event("event_1", "flytt", [Participant("person_1", "subject")],
               place=PlaceRef("place_1"), from_place=PlaceRef("place_2"))
    lines, _ = _export(_project([ev, _marriage("event_2")]), tmp_path)
    used = {line.split()[1] for line in lines if " _SLK_" in line[:12]}
    assert used and used <= set(SLK_TAG_REGISTRY)


def test_non_numeric_ids_get_sequential_xrefs(tmp_path: Path) -> None:
    persons = [
        Person(id="uuid-a", names=[Name(type="birth", given="A", surname="X")], sex="M"),
        _person(1),
        Person(id="uuid-b", names=[Name(type="birth", given="B", surname="X")], sex="F"),
    ]
    lines, _ = _export(_project([], persons=persons), tmp_path)
    indis = [line for line in lines if line.endswith(" INDI")]
    # person_1 keeps @I1@; non-numeric ids skip it and number in project order.
    assert indis == ["0 @I2@ INDI", "0 @I1@ INDI", "0 @I3@ INDI"]


def test_export_is_independent_of_hash_seed(tmp_path: Path) -> None:
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from slaktbusken.gedcom.exporter import GEDCOMExporter\n"
        "from slaktbusken.persistence.serialization import deserialize\n"
        "data = deserialize(Path(sys.argv[1]).read_text(encoding='utf-8'))\n"
        "GEDCOMExporter().export(data, Path(sys.argv[2]))\n"
    )
    outputs = []
    for seed in ("1", "2"):
        out = tmp_path / f"out{seed}.ged"
        env = {**os.environ, "PYTHONHASHSEED": seed, "QT_QPA_PLATFORM": "offscreen"}
        subprocess.run(
            [sys.executable, "-c", script, str(MERGE_TEST), str(out)],
            check=True, cwd=ROOT, env=env,
        )
        outputs.append(out.read_bytes())
    assert outputs[0] == outputs[1]
