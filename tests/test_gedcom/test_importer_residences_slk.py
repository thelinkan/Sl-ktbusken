"""Importer side of residences: structured tags and legacy prose (task 9.2)."""

from __future__ import annotations

from pathlib import Path

from tests.test_gedcom.test_importer_events_slk import HEAD, _import

OLD_HEAD = HEAD.replace("1 _SLK_VERS 1\n", "")
SOURCE = "0 @S1@ SOUR\n1 TITL Kyrkbok\n"


def _resi(*lines: str) -> str:
    return (
        "0 @I1@ INDI\n1 NAME Anna /X/\n1 RESI\n2 PLAC Ljusdal\n"
        + "".join(f"{line}\n" for line in lines)
    )


def _one(data):
    (res,) = data.residences
    return res


def test_structured_endpoints_override_date_and_prose(tmp_path: Path):
    text = HEAD + _resi(
        "2 DATE FROM 1900 TO 1910",
        "2 _SLK_START", "3 _SLK_EARLIEST 1899-05", "3 _SLK_LATEST 1900-01-02",
        "3 _SLK_PREC month", "3 _SLK_NOTE start-not",
        "2 _SLK_END", "3 _SLK_LATEST 1911",
        "2 _SLK_HHROLE dräng", "2 _SLK_RNOTES rad ett",
        "3 CONT rad två",
    ) + "0 TRLR\n"
    data, _ = _import(text, tmp_path)
    res = _one(data)
    assert (res.start.earliest, res.start.latest, res.start.precision) == (
        "1899-05", "1900-01-02", "month")
    assert res.start.note == "start-not"
    assert (res.end.earliest, res.end.latest) == (None, "1911")
    assert res.role_in_household == "dräng"
    assert res.notes == "rad ett\nrad två"


def test_without_slk_tags_date_is_used(tmp_path: Path):
    text = HEAD + _resi("2 DATE FROM 1900 TO 1910") + "0 TRLR\n"
    data, _ = _import(text, tmp_path)
    res = _one(data)
    assert (res.start.latest, res.end.earliest) == ("1900", "1910")


def test_observation_period_page_quality_note_aspects(tmp_path: Path):
    text = HEAD + SOURCE + _resi(
        "2 SOUR @S1@", "3 QUAY 3", "3 PAGE s. 4", "3 _SLK_OBSFROM 1910",
        "3 _SLK_OBSTO 1923", "3 _SLK_NOTE anm", "3 _SLK_ASP a",
        "3 NOTE Observation: 1910-1923",
    ) + "0 TRLR\n"
    data, _ = _import(text, tmp_path)
    (obs,) = _one(data).observations
    assert (obs.observed_from, obs.observed_to, obs.page_note) == ("1910", "1923", "s. 4")
    assert (obs.source_ref.quality, obs.source_ref.note, obs.source_ref.aspects) == (
        "primary", "anm", ["a"])


def test_legacy_prose_read_for_file_without_marker(tmp_path: Path):
    text = OLD_HEAD + SOURCE + _resi(
        "2 DATE FROM 5 AUG 1912 TO 1923",
        "2 NOTE Tidigast början: 1912-08-05",
        "2 NOTE Senast slut: 1923-12-31",
        "2 NOTE Roll: piga",
        "2 SOUR @S1@", "3 NOTE Observation: 1910-1923",
        "2 SOUR @S1@", "3 NOTE Observation: 1915",
    ) + "0 TRLR\n"
    data, result = _import(text, tmp_path)
    res = _one(data)
    assert res.start.earliest == "1912-08-05"
    assert res.end.latest == "1923-12-31"
    assert res.role_in_household == "piga"
    assert [(o.observed_from, o.observed_to) for o in res.observations] == [
        ("1910", "1923"), ("1915", "1915")]
    assert not [w for w in result.warnings if "Ogiltig" in str(w)]


def test_legacy_prose_ignored_with_marker(tmp_path: Path):
    text = HEAD + SOURCE + _resi(
        "2 NOTE Tidigast början: 1912-08-05", "2 NOTE Roll: piga",
        "2 SOUR @S1@", "3 NOTE Observation: 1910-1923",
    ) + "0 TRLR\n"
    data, _ = _import(text, tmp_path)
    res = _one(data)
    assert res.start.earliest is None
    assert res.role_in_household == ""
    assert (res.observations[0].observed_from, res.observations[0].observed_to) == ("", "")


def test_invalid_legacy_prose_warns_and_is_ignored(tmp_path: Path):
    text = OLD_HEAD + SOURCE + _resi(
        "2 NOTE Tidigast början: igår", "2 NOTE tidigast början: 1900-01-01",
        "2 SOUR @S1@", "3 NOTE Observation: 1930-1920",
    ) + "0 TRLR\n"
    data, result = _import(text, tmp_path)
    res = _one(data)
    assert res.start.earliest is None
    assert (res.observations[0].observed_from, res.observations[0].observed_to) == ("", "")
    assert len([w for w in result.warnings if "Ogiltig" in str(w)]) == 2


def test_legacy_reimport_is_idempotent(tmp_path: Path):
    text = OLD_HEAD + _resi(
        "2 DATE FROM 1912 TO 1923", "2 NOTE Tidigast början: 1912-08-05"
    ) + "0 TRLR\n"
    data, _ = _import(text, tmp_path)
    data2, result = _import(text, tmp_path, data)
    assert len(data2.residences) == 1
    assert result.residences_added == 0


def test_legacy_claim_ignores_event_links(tmp_path: Path):
    from slaktbusken.gedcom.translation.record_identity import residence_fingerprint

    text = OLD_HEAD + _resi("2 DATE FROM 1912 TO 1923") + "0 TRLR\n"
    data, _ = _import(text, tmp_path)
    res = _one(data)
    a = residence_fingerprint(res, ignore_links=True)
    res.start.event_id = "event_9"
    assert residence_fingerprint(res, ignore_links=True) == a
    assert residence_fingerprint(res) != a


def test_exporttest_fixture_restores_legacy_prose(tmp_path: Path):
    path = Path(__file__).parent.parent / "fixtures" / "gedcom_roundtrip" / "exporttest.ged"
    data, _ = _import(path.read_text(encoding="utf-8"), tmp_path)
    assert any(r.start.earliest == "1912-08-05" for r in data.residences)
    periods = [
        (o.observed_from, o.observed_to)
        for r in data.residences for o in r.observations
    ]
    assert ("1910", "1923") in periods
