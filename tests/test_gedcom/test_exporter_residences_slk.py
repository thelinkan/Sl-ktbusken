"""Exporter side of residences: _SLK tags, PAGE, observation period (task 9.1).

Requirements 7.1-7.4, 2.6. The pre-existing RESI lines stay byte-identical
and the slk1 hash of a RESI equals the legacy hash of its old-exporter form.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.parser import parse_gedcom
from slaktbusken.gedcom.slk_tags import SLK_TAG_REGISTRY
from slaktbusken.gedcom.translation.record_identity import record_hash
from slaktbusken.model.event import SourceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.source import Source
from tests.test_gedcom_roundtrip import fixtures


def _export(residence: ResidenceFact, tmp_path: Path) -> list[str]:
    data = ProjectData(
        format="släktbuske-file",
        version="0.2",
        project=ProjectMetadata(title="T"),
        persons=[Person(id="person_1", sex="M",
                        names=[Name(type="birth", given="Anders", surname="S")])],
        families=[],
        events=[],
        places=[Place(id="place_1", name="Ljusdal", type="socken")],
        sources=[Source(id="source_1", provider="p", source_type="t", title="K")],
        residences=[residence],
    )
    GEDCOMExporter().export(data, tmp_path / "t.ged")
    return (tmp_path / "t.ged").read_text(encoding="utf-8").splitlines()


def _resi(lines: list[str]) -> list[str]:
    start = lines.index("1 RESI")
    end = next((i for i in range(start + 1, len(lines))
                if int(lines[i].split(" ", 1)[0]) <= 1), len(lines))
    return lines[start:end]


def _full() -> ResidenceFact:
    return ResidenceFact(
        id="r1", person_id="person_1", place_id="place_1",
        start=Endpoint("1830", "1838", "year", None, "start note"),
        end=Endpoint("1848", "1850", "year"),
        role_in_household="piga", notes="Rad ett\nrad två",
        observations=[Observation(
            SourceRef("source_1", "secondary", note="n", aspects=["x"]),
            observed_from="1840", observed_to="1845", page_note="s. 12",
        )],
    )


def test_slk_tags_are_written_with_their_children(tmp_path: Path) -> None:
    resi = _resi(_export(_full(), tmp_path))
    assert resi[resi.index("2 _SLK_START"):][:5] == [
        "2 _SLK_START", "3 _SLK_EARLIEST 1830", "3 _SLK_LATEST 1838",
        "3 _SLK_PREC year", "3 _SLK_NOTE start note",
    ]
    assert "2 _SLK_END" in resi and "3 _SLK_EARLIEST 1848" in resi
    assert "2 _SLK_HHROLE piga" in resi
    assert "2 _SLK_RNOTES Rad ett" in resi and "3 CONT rad två" in resi
    i = resi.index("2 SOUR @S1@")
    assert resi[i + 1] == "3 NOTE Observation: 1840-1845"
    sour = resi[i:]
    assert sour.count("3 QUAY 2") == 1
    assert sour.count("3 _SLK_NOTE n") == 1
    assert sour.count("3 _SLK_ASP x") == 1
    assert "3 PAGE s. 12" in sour
    assert "3 _SLK_OBSFROM 1840" in sour and "3 _SLK_OBSTO 1845" in sour
    assert not any("_SLK_EREF" in line for line in resi)


def test_exact_and_one_sided_endpoints_are_written(tmp_path: Path) -> None:
    res = ResidenceFact(id="r", person_id="person_1", place_id="place_1",
                        start=Endpoint("1840", "1840"), end=Endpoint(None, "1850"))
    resi = _resi(_export(res, tmp_path))
    assert resi[resi.index("2 _SLK_START"):][:3] == [
        "2 _SLK_START", "3 _SLK_EARLIEST 1840", "3 _SLK_LATEST 1840"]
    assert resi[resi.index("2 _SLK_END"):][:2] == ["2 _SLK_END", "3 _SLK_LATEST 1850"]


def test_empty_values_write_no_slk_tags(tmp_path: Path) -> None:
    res = ResidenceFact(id="r", person_id="person_1", place_id="place_1")
    assert not any("_SLK_" in line for line in _resi(_export(res, tmp_path)))


def test_multiline_notes_use_cont_and_prose_note_stays(tmp_path: Path) -> None:
    resi = _resi(_export(_full(), tmp_path))
    assert "2 NOTE Rad ett" in resi and "3 CONT rad två" in resi
    assert "2 NOTE Roll: piga" in resi
    # no physical line is left without a level number
    assert all(line.split(" ", 1)[0].isdigit() for line in resi)


def test_existing_lines_unchanged_for_single_line_residence(tmp_path: Path) -> None:
    res = ResidenceFact(
        id="r", person_id="person_1", place_id="place_1",
        start=Endpoint("1838", "1840"), end=Endpoint("1846", "1848"),
        role_in_household="husbonde", notes="Familjen flyttade.",
    )
    resi = _resi(_export(res, tmp_path))
    old = ["1 RESI", "2 DATE FROM 1840 TO 1846", "2 PLAC Ljusdal",
           "2 NOTE Tidigast början: 1838", "2 NOTE Senast slut: 1848",
           "2 NOTE Roll: husbonde", "2 NOTE Familjen flyttade."]
    assert [x for x in resi if not x.startswith(("2 _SLK_", "3 _SLK_"))] == old


def test_slk1_hash_equals_legacy_hash_of_old_form(tmp_path: Path) -> None:
    res = _full()
    res.notes = "Enradsnotering"
    new = _resi(_export(res, tmp_path))
    old = [x for x in new if not x.startswith(("2 _SLK_", "3 _SLK_"))]
    old = [x for x in old if not x.startswith(("3 PAGE", "3 QUAY"))]
    # old exporter also lacked the citation's _SLK_NOTE/_SLK_ASP (filtered above)
    def hash_of(lines: list[str], profile: str) -> str:
        text = "0 HEAD\n" + "\n".join(f"0 @I1@ INDI\n{x}" if x == "1 RESI" else x
                                       for x in lines) + "\n0 TRLR\n"
        record = next(c for r in parse_gedcom(text).records
                      for c in r.children if c.tag == "RESI")
        return record_hash(record, {"@S1@": "source_1"}, profile)
    assert hash_of(new, "slk1") == hash_of(old, "legacy")


def test_mergetest_residences_hash_stable_and_registered(tmp_path: Path) -> None:
    data = fixtures.load_mergetest()
    ged = tmp_path / "m.ged"
    GEDCOMExporter().export(data, ged)
    text = ged.read_text(encoding="utf-8")
    assert "_SLK_START" in text
    used = {w for line in text.splitlines() for w in line.split() if w.startswith("_SLK_")}
    assert used <= set(SLK_TAG_REGISTRY)


def test_mergetest_second_import_creates_no_residence(tmp_path: Path) -> None:
    from slaktbusken.services.import_service import ImportService
    from slaktbusken.services.project_service import ProjectService
    from slaktbusken.services.report_service import ReportService
    from slaktbusken.services.validation_service import ValidationService
    from slaktbusken.persistence.serialization import serialize

    ged = tmp_path / "out.ged"
    GEDCOMExporter().export(fixtures.load_mergetest(), ged)
    data = ProjectData(project=ProjectMetadata(title="T"))
    ps = ProjectService()
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    def run():
        ps._project_data = data
        return ImportService(ValidationService(), ReportService()).run(
            data, ged, project_dir, ps)

    run()
    before = len(data.residences)
    assert before > 0
    snap = json.dumps(json.loads(serialize(copy.deepcopy(data)))["residences"],
                      sort_keys=True)
    run()
    assert len(data.residences) == before
    assert json.dumps(json.loads(serialize(copy.deepcopy(data)))["residences"],
                      sort_keys=True) == snap
