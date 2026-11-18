from __future__ import annotations

"""Regression tests for task 5.4: the post-import placement sync never rewrites
an imported family that is not itself placement-derived."""

from tests.test_gedcom.test_importer_families_slk import HEAD, _import, _indi, _name


def _fam(data, *names):
    return [f for f in data.families
            if {_name(data, p.person_id) for p in f.partners} == set(names)]


def _links(data, fam):
    return {(_name(data, l.child_id), _name(data, l.parent_id) if l.parent_id else None,
             l.parentage_type) for l in fam.parent_child_links}


def test_biological_sibling_survives_foster_child(tmp_path):
    text = (HEAD + _indi("@I1@", "Fa", "M") + _indi("@I2@", "Mo", "F")
            + _indi("@I3@", "Bio", "U") + _indi("@I4@", "Fost", "U")
            + "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n1 CHIL @I4@\n0 TRLR\n"
            ).replace("1 NAME Fost /X/\n", "1 NAME Fost /X/\n1 FAMC @F1@\n2 PEDI foster\n")
    data, _ = _import(text, tmp_path)
    all_links = set()
    for fam in _fam(data, "Fa X", "Mo X"):
        all_links |= _links(data, fam)
    assert ("Bio X", "Fa X", "biological") in all_links
    assert ("Fost X", "Mo X", "foster") in all_links
    imported = next(f for f in _fam(data, "Fa X", "Mo X") if not f.event_ids)
    assert any(_name(data, c) == "Bio X" for c in imported.children)


def test_imported_family_keeps_roles_and_order_with_foster_child(tmp_path):
    text = (HEAD + _indi("@I1@", "Fa", "M") + _indi("@I2@", "Mo", "F")
            + _indi("@I3@", "Fost", "U")
            + "0 @F1@ FAM\n1 HUSB @I2@\n1 WIFE @I1@\n"
            + "1 _SLK_PARTNER @I2@\n2 _SLK_ROLE wife\n"
            + "1 _SLK_PARTNER @I1@\n2 _SLK_ROLE husband\n1 CHIL @I3@\n0 TRLR\n"
            ).replace("1 NAME Fost /X/\n", "1 NAME Fost /X/\n1 FAMC @F1@\n2 PEDI foster\n")
    data, _ = _import(text, tmp_path)
    for fam in _fam(data, "Fa X", "Mo X"):
        assert [(_name(data, p.person_id), p.role) for p in fam.partners] == [
            ("Mo X", "wife"), ("Fa X", "husband")]
    assert any(e.type == "foster_home" for e in data.events)


def test_parentless_donor_link_on_family_with_foster_child_is_kept(tmp_path):
    text = (HEAD + _indi("@I1@", "Fa", "M") + _indi("@I2@", "Mo", "F")
            + _indi("@I3@", "Don", "U") + _indi("@I4@", "Fost", "U")
            + "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n1 CHIL @I4@\n0 TRLR\n"
            ).replace("1 NAME Don /X/\n",
                      "1 NAME Don /X/\n1 FAMC @F1@\n2 _SLK_PLINK\n3 TYPE unknown_donor\n"
            ).replace("1 NAME Fost /X/\n", "1 NAME Fost /X/\n1 FAMC @F1@\n2 PEDI foster\n")
    data, _ = _import(text, tmp_path)
    types = {t for fam in data.families for (_c, _p, t) in _links(data, fam)}
    assert "foster" in types
    assert any(_c == "Don X" and _p is None
               for fam in data.families for (_c, _p, _t) in _links(data, fam))


def test_foster_only_family_still_yields_foster_links_and_event(tmp_path):
    text = (HEAD + _indi("@I1@", "Fa", "M") + _indi("@I2@", "Mo", "F")
            + _indi("@I3@", "Fost", "U")
            + "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n0 TRLR\n"
            ).replace("1 NAME Fost /X/\n", "1 NAME Fost /X/\n1 FAMC @F1@\n2 PEDI foster\n")
    data, _ = _import(text, tmp_path)
    links = {l for fam in data.families for l in _links(data, fam)}
    assert links == {("Fost X", "Fa X", "foster"), ("Fost X", "Mo X", "foster")}
    assert sum(e.type == "foster_home" for e in data.events) == 1
