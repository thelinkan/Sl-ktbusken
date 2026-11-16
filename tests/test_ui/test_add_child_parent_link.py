"""Offscreen tests for the "Nytt barn" context-menu flow and its parent link.

Covers the bugfix where right-clicking a person and choosing "Nytt barn"
created a child with no ``ParentChildLink`` to the clicked person, so the
parent and child could not see each other in the diagrams.

Flow under test:
- ``Application._handle_context_add_relative("child", person_id)`` resolves an
  "other parent" chooser (``AddChildParentDialog``) when the clicked person
  already has partner families, then opens the person editor for the child.
- ``Application.handle_placeholder_click`` performs the actual linking.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow

import slaktbusken.app as app_module
from slaktbusken.app import Application
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.diagram_lookup import find_parent_families
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.dialogs import add_child_parent_dialog as acp
from slaktbusken.ui.dialogs.add_child_parent_dialog import NEW_FAMILY_SENTINEL


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _person(pid: str, given: str) -> Person:
    return Person(id=pid, sex="U", names=[Name(type="birth", given=given, surname="Test")])


def _make_app(qapp, data: ProjectData):
    """Build an Application-like namespace that drives the real methods."""
    svc = ProjectService()
    svc._project_data = data
    svc._project_path = Path("project.json.gz")

    panel = SimpleNamespace(
        active_person_id="",
        set_project_folder=lambda *_a, **_k: None,
        set_project_data=lambda *_a, **_k: None,
        set_person_box_config=lambda *_a, **_k: None,
    )
    person_list = SimpleNamespace(refresh=lambda *_a, **_k: None)
    main = QMainWindow()
    main.diagram_panel = panel
    main.person_list_panel = person_list
    main.show_progress = lambda *_a, **_k: None
    main.hide_progress = lambda *_a, **_k: None

    settings = SimpleNamespace(
        _settings=SimpleNamespace(person_box_config=None)
    )

    fake = SimpleNamespace(
        project_service=svc,
        main_window=main,
        app_settings_service=settings,
        editor_registry=None,
        _update_status=lambda: None,
    )
    # Bind the real methods we exercise.
    fake.handle_placeholder_click = (
        lambda role, family_id, target_person_id="": Application.handle_placeholder_click(
            fake, role, family_id, target_person_id
        )
    )
    # handle_placeholder_click delegates to this method on ``self``.
    fake._add_relative_in_session = (
        lambda role, family_id, target_person_id, session: Application._add_relative_in_session(
            fake, role, family_id, target_person_id, session
        )
    )
    fake._handle_context_add_relative = (
        lambda role, pid: Application._handle_context_add_relative(fake, role, pid)
    )
    fake._handle_context_add_child = (
        lambda pid: Application._handle_context_add_child(fake, pid)
    )
    return fake, main


def _patch_editor(monkeypatch, saved_builder):
    """Patch PersonEditor + QDialog.exec so the child editor "saves".

    ``saved_builder`` receives the stub editor's ``new_person`` and must return
    the Person to expose as ``saved_person`` (or None to simulate a failed save).
    QDialog.exec returns Accepted only for the person-editor dialog.
    """
    import slaktbusken.ui.editors.person_editor as pe_mod
    from PySide6.QtCore import Signal
    from PySide6.QtWidgets import QWidget

    class _FakeEditor(QWidget):
        editor_title = "Personredigerare: ny person"
        save_requested = Signal()
        cancel_requested = Signal()

        def __init__(self, project_data=None, person=None, parent=None, **_kw):
            super().__init__(parent)
            self._new_person = person
            self.saved_person = None

        def _finalize(self):
            self.saved_person = saved_builder(self._new_person)

    created: list[_FakeEditor] = []

    orig_editor = pe_mod.PersonEditor

    def _factory(*args, **kwargs):
        ed = _FakeEditor(*args, **kwargs)
        created.append(ed)
        return ed

    monkeypatch.setattr(pe_mod, "PersonEditor", _factory)

    # The person-editor dialog is a plain QDialog built inside app.py. Make its
    # exec accept and finalize the (most recently created) fake editor.
    def _fake_exec(self):
        if created:
            created[-1]._finalize()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", _fake_exec, raising=True)
    return created


def _patch_chooser(monkeypatch, chosen):
    """Patch AddChildParentDialog so exec accepts with the given chosen value.

    ``chosen`` may be a concrete family id, the NEW_FAMILY_SENTINEL, or the
    sentinel object ``_CANCEL`` to simulate a cancelled chooser.
    """
    captured: dict[str, object] = {}

    class _FakeChooser:
        def __init__(self, partner_families, persons_by_id, clicked_person_id, parent=None):
            # Reuse the real option builder so labels are exercised.
            self.option_labels = [
                label
                for _fid, label in acp.build_child_parent_options(
                    partner_families, persons_by_id, clicked_person_id
                )
            ]
            self.chosen_family_id = None
            captured["labels"] = self.option_labels
            captured["instance"] = self

        def exec(self):
            if chosen is _CANCEL:
                return QDialog.DialogCode.Rejected
            self.chosen_family_id = chosen
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(acp, "AddChildParentDialog", _FakeChooser)
    return captured


class _Cancel:
    pass


_CANCEL = _Cancel()


# ---------------------------------------------------------------------------
# Chooser with two partner families
# ---------------------------------------------------------------------------


def test_two_partner_families_lists_both_and_links_chosen(qapp, monkeypatch):
    clicked = _person("p_clicked", "Klick")
    partner_a = _person("p_a", "Alfa")
    partner_b = _person("p_b", "Beta")
    fam1 = Family(
        id="fam_1",
        partners=[
            FamilyPartner(person_id="p_clicked", role="partner"),
            FamilyPartner(person_id="p_a", role="partner"),
        ],
        children=[],
    )
    fam2 = Family(
        id="fam_2",
        partners=[
            FamilyPartner(person_id="p_clicked", role="partner"),
            FamilyPartner(person_id="p_b", role="partner"),
        ],
        children=[],
    )
    data = ProjectData()
    data.persons = [clicked, partner_a, partner_b]
    data.families = [fam1, fam2]

    captured = _patch_chooser(monkeypatch, chosen="fam_2")
    new_child = _person("p_child", "Barn")
    _patch_editor(monkeypatch, lambda _np: new_child)

    fake, main = _make_app(qapp, data)
    try:
        fake._handle_context_add_relative("child", "p_clicked")
    finally:
        main.close()

    # Chooser listed both partners plus the "other/none" option.
    assert captured["labels"] == ["Alfa Test", "Beta Test", acp.OTHER_PARENT_LABEL]

    # Child added to the CHOSEN family (fam_2), not fam_1.
    fam2_after = next(f for f in data.families if f.id == "fam_2")
    assert "p_child" in fam2_after.children
    # ParentChildLinks from BOTH partners of that family.
    link_parents = {
        link.parent_id
        for link in fam2_after.parent_child_links
        if link.child_id == "p_child"
    }
    assert link_parents == {"p_clicked", "p_b"}
    # fam_1 untouched.
    fam1_after = next(f for f in data.families if f.id == "fam_1")
    assert "p_child" not in fam1_after.children


# ---------------------------------------------------------------------------
# "Annan/ingen andra förälder" and no-partner single-parent family
# ---------------------------------------------------------------------------


def test_other_none_creates_single_parent_family_with_link(qapp, monkeypatch):
    clicked = _person("p_clicked", "Klick")
    partner_a = _person("p_a", "Alfa")
    fam1 = Family(
        id="fam_1",
        partners=[
            FamilyPartner(person_id="p_clicked", role="partner"),
            FamilyPartner(person_id="p_a", role="partner"),
        ],
        children=[],
    )
    data = ProjectData()
    data.persons = [clicked, partner_a]
    data.families = [fam1]

    _patch_chooser(monkeypatch, chosen=NEW_FAMILY_SENTINEL)
    new_child = _person("p_child", "Barn")
    _patch_editor(monkeypatch, lambda _np: new_child)

    fake, main = _make_app(qapp, data)
    try:
        fake._handle_context_add_relative("child", "p_clicked")
    finally:
        main.close()

    # A brand-new family (not fam_1) with only the clicked person as parent.
    new_families = [f for f in data.families if f.id != "fam_1"]
    assert len(new_families) == 1
    nf = new_families[0]
    assert [p.person_id for p in nf.partners] == ["p_clicked"]
    assert nf.children == ["p_child"]
    assert any(
        link.child_id == "p_child" and link.parent_id == "p_clicked"
        for link in nf.parent_child_links
    )

    # find_parent_families shows the parent for the child.
    parent_fams = find_parent_families(data, "p_child")
    assert nf.id in {f.id for f in parent_fams}


def test_no_partner_family_creates_single_parent_family_with_link(qapp, monkeypatch):
    clicked = _person("p_clicked", "Klick")
    data = ProjectData()
    data.persons = [clicked]
    data.families = []

    # The chooser must NOT be shown when there is no partner family; patch it to
    # raise if constructed so the test fails loudly if that invariant breaks.
    def _no_chooser(*_a, **_k):
        raise AssertionError("Chooser should not be shown without a partner family")

    monkeypatch.setattr(acp, "AddChildParentDialog", _no_chooser)

    new_child = _person("p_child", "Barn")
    _patch_editor(monkeypatch, lambda _np: new_child)

    fake, main = _make_app(qapp, data)
    try:
        fake._handle_context_add_relative("child", "p_clicked")
    finally:
        main.close()

    assert len(data.families) == 1
    nf = data.families[0]
    assert [p.person_id for p in nf.partners] == ["p_clicked"]
    assert nf.children == ["p_child"]
    assert any(
        link.child_id == "p_child" and link.parent_id == "p_clicked"
        for link in nf.parent_child_links
    )
    # Parent->child both visible.
    assert nf.id in {f.id for f in find_parent_families(data, "p_child")}


# ---------------------------------------------------------------------------
# Cancelling the chooser
# ---------------------------------------------------------------------------


def test_cancel_chooser_creates_nothing_and_skips_editor(qapp, monkeypatch):
    clicked = _person("p_clicked", "Klick")
    partner_a = _person("p_a", "Alfa")
    fam1 = Family(
        id="fam_1",
        partners=[
            FamilyPartner(person_id="p_clicked", role="partner"),
            FamilyPartner(person_id="p_a", role="partner"),
        ],
        children=[],
    )
    data = ProjectData()
    data.persons = [clicked, partner_a]
    data.families = [fam1]

    _patch_chooser(monkeypatch, chosen=_CANCEL)

    editor_opened = {"count": 0}

    import slaktbusken.ui.editors.person_editor as pe_mod

    def _editor_tripwire(*_a, **_k):
        editor_opened["count"] += 1
        raise AssertionError("Editor must not open when chooser is cancelled")

    monkeypatch.setattr(pe_mod, "PersonEditor", _editor_tripwire)

    fake, main = _make_app(qapp, data)
    try:
        fake._handle_context_add_relative("child", "p_clicked")
    finally:
        main.close()

    # No new person, no new family, editor never opened.
    assert data.persons == [clicked, partner_a]
    assert data.families == [fam1]
    assert "p_child" not in [p.id for p in data.persons]
    assert editor_opened["count"] == 0


# ---------------------------------------------------------------------------
# In-graph "Lägg till barn" (explicit family_id) unchanged
# ---------------------------------------------------------------------------


def test_in_graph_add_child_with_family_id_unchanged(qapp, monkeypatch):
    p_dad = _person("p_dad", "Far")
    p_mom = _person("p_mom", "Mor")
    fam = Family(
        id="fam_1",
        partners=[
            FamilyPartner(person_id="p_dad", role="father"),
            FamilyPartner(person_id="p_mom", role="mother"),
        ],
        children=[],
    )
    data = ProjectData()
    data.persons = [p_dad, p_mom]
    data.families = [fam]

    # Chooser must not be involved on the direct family_id path.
    def _no_chooser(*_a, **_k):
        raise AssertionError("Chooser not used on direct family_id path")

    monkeypatch.setattr(acp, "AddChildParentDialog", _no_chooser)

    new_child = _person("p_child", "Barn")
    _patch_editor(monkeypatch, lambda _np: new_child)

    fake, main = _make_app(qapp, data)
    try:
        # Simulate the in-graph placeholder click with an explicit family_id.
        fake.handle_placeholder_click("child", "fam_1", target_person_id="")
    finally:
        main.close()

    fam_after = next(f for f in data.families if f.id == "fam_1")
    assert fam_after.children == ["p_child"]
    link_parents = {
        link.parent_id
        for link in fam_after.parent_child_links
        if link.child_id == "p_child"
    }
    assert link_parents == {"p_dad", "p_mom"}
    # No extra family created.
    assert len(data.families) == 1


# ---------------------------------------------------------------------------
# Chooser option-builder unit tests
# ---------------------------------------------------------------------------


def test_option_builder_labels_other_partner_and_unknown(qapp):
    clicked = _person("p_clicked", "Klick")
    partner_a = _person("p_a", "Alfa")
    persons_by_id = {"p_clicked": clicked, "p_a": partner_a}

    fam_with_partner = Family(
        id="fam_1",
        partners=[
            FamilyPartner(person_id="p_clicked", role="partner"),
            FamilyPartner(person_id="p_a", role="partner"),
        ],
        children=[],
    )
    # A family whose ONLY partner is the clicked person -> "(okänd partner)".
    fam_solo = Family(
        id="fam_solo",
        partners=[FamilyPartner(person_id="p_clicked", role="partner")],
        children=[],
    )

    options = acp.build_child_parent_options(
        [fam_with_partner, fam_solo], persons_by_id, "p_clicked"
    )
    assert options == [
        ("fam_1", "Alfa Test"),
        ("fam_solo", acp.UNKNOWN_PARTNER_LABEL),
        (NEW_FAMILY_SENTINEL, acp.OTHER_PARENT_LABEL),
    ]


def test_option_builder_no_partner_family_only_other_option(qapp):
    options = acp.build_child_parent_options([], {}, "p_clicked")
    assert options == [(NEW_FAMILY_SENTINEL, acp.OTHER_PARENT_LABEL)]
