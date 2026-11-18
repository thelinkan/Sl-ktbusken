"""Unit tests for the SLK tag registry and the tolerant readers (task 2.2)."""

from __future__ import annotations

from slaktbusken.gedcom.parser import GedcomLine
from slaktbusken.gedcom.slk_tags import (
    SLK_TAG_REGISTRY,
    RepositoryData,
    RepositoryRefData,
    SlkProblem,
    read_citation,
    read_endpoint,
    read_legacy_prose,
    read_name_type,
    read_partners,
    read_plinks,
    read_repository,
    read_source_fields,
    unknown_slk_children,
)


def n(tag, value=None, *children, xref=None, level=1):
    return GedcomLine(level, tag, value, xref, 1, list(children))


def test_registry_has_every_design_tag_including_repository_tags():
    expected = {
        "_SLK_VERS", "_SLK_EID", "_SLK_EVTYPE", "_SLK_ROLE", "_SLK_PART",
        "_SLK_PARTNER", "_SLK_SEX", "_SLK_PLINK", "_SLK_QUAL", "_SLK_CTX",
        "_SLK_ASP", "_SLK_FROMPLAC", "_SLK_START", "_SLK_END", "_SLK_EARLIEST",
        "_SLK_LATEST", "_SLK_PREC", "_SLK_EREF", "_SLK_NOTE", "_SLK_HHROLE",
        "_SLK_RNOTES", "_SLK_OBSFROM", "_SLK_OBSTO", "_SLK_STYPE", "_SLK_PROV",
        "_SLK_LEV", "_SLK_KTYP", "_SLK_SREF", "_SLK_FLD", "_SLK_RTYPE",
        "_SLK_XID", "_SLK_RSTYPE", "_SLK_RIMG", "_SLK_RPAGE", "_SLK_RMEDNAME",
    }
    assert set(SLK_TAG_REGISTRY) == expected
    for tag, row in SLK_TAG_REGISTRY.items():
        assert row.tag == tag
        assert row.purpose and row.parents and row.supported_values
        assert row.importer_behaviour and row.standard_fallback
        assert row.cardinality in {"0:1", "0:n", "1:1"}


def test_unknown_slk_children_are_listed_not_reported():
    fam = n("FAM", None, n("_SLK_FUTURE", "x", n("_SLK_ROLE", "y")), n("_SLK_PARTNER", "@I1@"))
    assert [c.tag for c in unknown_slk_children(fam)] == ["_SLK_FUTURE"]
    problems: list[SlkProblem] = []
    read_partners(fam, problems=problems)
    assert all(p.tag != "_SLK_FUTURE" for p in problems)


def test_citation_quality_order_and_defaults():
    assert read_citation(n("SOUR", "@S1@")).quality == "secondary"
    assert read_citation(n("SOUR", "@S1@", n("QUAY", "3"))).quality == "primary"
    assert read_citation(n("SOUR", "@S1@", n("QUAY", "0"))).quality == "tertiary"
    both = n("SOUR", "@S1@", n("QUAY", "3"), n("_SLK_QUAL", "originalkälla"))
    assert read_citation(both).quality == "originalkälla"
    problems: list[SlkProblem] = []
    bad = read_citation(n("SOUR", None, n("QUAY", "9"), n("_SLK_CTX", "x")), problems)
    assert (bad.quality, bad.context) == ("secondary", "event")
    assert {p.code for p in problems} == {"bad_quay", "bad_ctx"}


def test_citation_context_note_aspects_and_observation_period():
    node = n(
        "SOUR", "@S1@",
        n("_SLK_CTX", "from_place"), n("NOTE", "Observation: 1840-1845"),
        n("NOTE", "en not"), n("_SLK_ASP", "a"), n("_SLK_ASP", ""), n("_SLK_ASP", "b"),
        n("PAGE", "s. 4"), n("_SLK_OBSFROM", "1840"), n("_SLK_OBSTO", "1845"),
    )
    data = read_citation(node)
    assert (data.context, data.note, data.aspects, data.page) == (
        "from_place", "en not", ["a", "b"], "s. 4"
    )
    assert (data.observed_from, data.observed_to) == ("1840", "1845")


def test_bad_observation_period_falls_back_to_note_then_unset():
    problems: list[SlkProblem] = []
    node = n("SOUR", "@S1@", n("NOTE", "Observation: 1841-1843"),
             n("_SLK_OBSFROM", "1850"), n("_SLK_OBSTO", "1840"))
    data = read_citation(node, problems)
    assert (data.observed_from, data.observed_to) == ("1841", "1843")
    assert problems
    bare = read_citation(n("SOUR", None, n("_SLK_OBSFROM", "abcd")), problems)
    assert (bare.observed_from, bare.observed_to) == ("", "")


def test_endpoint_values_and_fallbacks():
    good = read_endpoint(n("_SLK_START", None, n("_SLK_EARLIEST", "1830"),
                           n("_SLK_LATEST", "1838-05"), n("_SLK_PREC", "year"),
                           n("_SLK_NOTE", "x"), n("_SLK_EREF", "event_1")))
    assert (good.earliest, good.latest, good.precision, good.note) == (
        "1830", "1838-05", "year", "x"
    )
    problems: list[SlkProblem] = []
    derived = read_endpoint(n("_SLK_END", None, n("_SLK_EARLIEST", "1830-02-30"),
                              n("_SLK_LATEST", "1840-01"), n("_SLK_PREC", "zzz")),
                            problems)
    assert (derived.earliest, derived.latest, derived.precision) == (None, "1840-01", "month")
    assert {p.code for p in problems} == {"bad_date", "bad_precision"}
    problems.clear()
    assert read_endpoint(n("_SLK_END", None, n("_SLK_LATEST", "x")), problems) is None
    assert any(p.code == "endpoint_unusable" for p in problems)
    assert read_endpoint(n("_SLK_END"), problems) is None
    assert read_endpoint(None) is None


def test_partners_used_only_when_they_match_husb_and_wife():
    fam = n("FAM", None, n("HUSB", "@I1@"), n("WIFE", "@I2@"),
            n("_SLK_PARTNER", "@I2@", n("_SLK_ROLE", "mother")),
            n("_SLK_PARTNER", "@I1@"))
    assert read_partners(fam) == [("@I2@", "mother"), ("@I1@", "husband")]
    assert read_partners(n("FAM", None, n("HUSB", "@I1@"))) is None
    problems: list[SlkProblem] = []
    mismatch = n("FAM", None, n("HUSB", "@I1@"), n("_SLK_PARTNER", "@I9@"))
    assert read_partners(mismatch, problems=problems) is None
    assert problems[0].code == "partners_mismatch"
    unknown = n("FAM", None, n("HUSB", "@I1@"), n("_SLK_PARTNER", "@I1@"))
    assert read_partners(unknown, known_xrefs={"@I2@"}, problems=problems) is None


def test_partner_role_make_maka_is_kept_exactly():
    problems: list[SlkProblem] = []
    fam = n("FAM", None, n("HUSB", "@I1@"), n("WIFE", "@I2@"),
            n("_SLK_PARTNER", "@I2@", n("_SLK_ROLE", "make/maka")),
            n("_SLK_PARTNER", "@I1@", n("_SLK_ROLE", "make/maka")))
    assert read_partners(fam, problems=problems) == [
        ("@I2@", "make/maka"), ("@I1@", "make/maka"),
    ]
    assert problems == []


def test_event_participants_reader():
    from slaktbusken.gedcom.slk_tags import read_event_participants

    problems: list[SlkProblem] = []
    ev = n("MARR", None,
           n("_SLK_PART", "@I1@", n("_SLK_ROLE", "make/maka")),
           n("_SLK_PART", "@I1@"), n("_SLK_PART", "@I9@"), n("_SLK_PART", "@I2@"))
    assert read_event_participants(ev, {"@I1@", "@I2@"}, problems) == [
        ("@I1@", "make/maka"), ("@I2@", "spouse"),
    ]
    assert [p.code for p in problems] == ["duplicate_participant", "unknown_participant"]
    assert read_event_participants(n("MARR"), None) is None
    assert read_event_participants(n("MARR", None, n("_SLK_PART", "@I9@")), {"@I1@"}) is None


def test_plinks_and_name_types():
    problems: list[SlkProblem] = []
    famc = n("FAMC", "@F1@",
             n("_SLK_PLINK", "@I1@", n("TYPE", "foster")),
             n("_SLK_PLINK", "", n("TYPE", "unknown_donor")),
             n("_SLK_PLINK", "@I7@", n("TYPE", "nonsense")))
    links = read_plinks(famc, known_xrefs={"@I1@"}, problems=problems)
    assert [(p.parent_xref, p.parentage_type) for p in links] == [
        ("@I1@", "foster"), (None, "unknown_donor"), (None, None)
    ]
    assert {p.code for p in problems} == {"unknown_parent", "bad_parentage_type"}

    def typ(value):
        return read_name_type(n("NAME", "A /B/", n("TYPE", value)))

    assert [typ(v) for v in ("birth", "MAIDEN", "married", "aka", "adopted", "other", "immigrant")] == [
        "birth", "birth", "married", "alias", "adopted", "other", "other"
    ]
    assert read_name_type(n("NAME", "A /B/")) is None
    assert read_name_type(n("NAME", "A /B/", n("TYPE", ""))) is None


def test_source_fields():
    problems: list[SlkProblem] = []
    sour = n("SOUR", None, n("_SLK_STYPE", "church_book"), n("_SLK_PROV", "AD"),
             n("_SLK_LEV", "Arkiv Digital"), n("_SLK_KTYP", "Husförhör"),
             n("_SLK_SREF", None,
                n("_SLK_FLD", 'parish "Ed"'), n("_SLK_FLD", "image 140"),
                n("_SLK_FLD", "page null"), n("_SLK_FLD", "volume {bad"),
                n("_SLK_FLD", "bogus 1"), n("_SLK_FLD", "image true")),
             level=0)
    extras = read_source_fields(sour, problems)
    assert extras.source_type == "church_book" and extras.provider == "AD"
    assert (extras.leverantor_name, extras.kalltyp_name) == ("Arkiv Digital", "Husförhör")
    assert extras.reference_fields == {"parish": "Ed", "image": 140, "page": None}
    assert len(problems) == 3
    bad = read_source_fields(n("SOUR", None, n("_SLK_STYPE", "zzz")), problems)
    assert bad.source_type is None
    assert read_source_fields(n("SOUR", None, n("_SLK_SREF", None, n("_SLK_FLD", "x")))).reference_fields is None


def test_repository_record_and_reference():
    rec = read_repository(n("REPO", None, n("_SLK_RTYPE", "arkiv"),
                            n("_SLK_XID", "a"), n("_SLK_XID", ""), n("_SLK_XID", "b"),
                            xref="@R1@", level=0))
    assert isinstance(rec, RepositoryData)
    assert (rec.type, rec.external_ids) == ("arkiv", ["a", "b"])
    problems: list[SlkProblem] = []
    ref = read_repository(n("REPO", "@R1@", n("_SLK_RSTYPE", "bok"), n("_SLK_RIMG", "12"),
                            n("_SLK_RPAGE", "x1"), n("_SLK_RMEDNAME", "film")), problems)
    assert isinstance(ref, RepositoryRefData)
    assert (ref.source_type, ref.image_number, ref.page_number, ref.media_name) == (
        "bok", 12, None, "film"
    )
    assert [p.code for p in problems] == ["bad_number"]


def test_legacy_prose_exact_formats_only():
    problems: list[SlkProblem] = []
    resi = n("RESI", None,
             n("NOTE", "Tidigast början: 1830-05"), n("NOTE", "Senast slut: 1850"),
             n("NOTE", "Roll: piga"), n("NOTE", "tidigast början: 1800"),
             n("NOTE", "Roll: x\nnästa"), n("NOTE", "Fri text"),
             n("SOUR", "@S1@", n("NOTE", "Observation: 1840-1845")),
             n("SOUR", "@S2@", n("NOTE", "Observation:")))
    got = read_legacy_prose(resi, problems)
    assert (got.start_earliest, got.end_latest, got.role_in_household) == ("1830-05", "1850", "piga")
    assert [(o.source_xref, o.observed_from, o.observed_to) for o in got.observations] == [
        ("@S1@", "1840", "1845")
    ]
    assert len(got.interpreted) == 4
    # "Roll: x\nnästa" is valid text, but a second role is a duplicate.
    assert [p.code for p in problems] == ["duplicate_prose"]


def test_legacy_prose_invalid_values_warn_and_stay_notes():
    problems: list[SlkProblem] = []
    resi = n("RESI", None, n("NOTE", "Tidigast början: 1830-13"),
             n("NOTE", "Senast slut: igår"),
             n("SOUR", "@S1@", n("NOTE", "Observation: 1850-1840")),
             n("SOUR", "@S2@", n("NOTE", "Observation: 184")))
    got = read_legacy_prose(resi, problems)
    assert got.interpreted == [] and got.start_earliest is None
    assert [p.code for p in problems] == [
        "bad_prose_date", "bad_prose_date", "bad_prose_period", "bad_prose_period"
    ]


def test_readers_are_total_on_odd_nodes():
    odd = GedcomLine(1, "X", None, None, 0, [])
    for reader in (read_citation, read_endpoint, read_name_type, read_plinks,
                   read_source_fields, read_repository, read_legacy_prose, read_partners):
        reader(None)
        reader(odd)
