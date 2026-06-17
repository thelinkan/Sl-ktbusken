"""Demo script for the Relationship Dialog.

Creates a family tree where two persons (Lisa and Erik) are related
in two different ways:
1. Second cousins (tremänning) — share great-grandparents via one line
2. Fourth cousins once removed (femmänning, ett släktled bort) — via another line

Then launches the relationship dialog with "Visa alla relationsvägar" checked.
"""

import sys
from PySide6.QtWidgets import QApplication

from slaktbusken.model.person import Person, Name
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.project import ProjectData, ProjectMetadata


def build_demo_tree() -> ProjectData:
    """Build a family tree with two relationship paths between Lisa and Erik.

    Path 1 — Second cousins (tremänning):
        Great-grandparents: Gustaf & Anna (generation 0)
        ├── Grandparent A: Karl (son of Gustaf & Anna)
        │   └── Parent A: Sven (son of Karl)
        │       └── TARGET: Lisa (daughter of Sven)
        └── Grandparent B: Maria (daughter of Gustaf & Anna)
            └── Parent B: Olof (son of Maria)
                └── TARGET: Erik (son of Olof)

    Path 2 — Fourth cousins once removed (femmänning, ett släktled bort):
        5x-great-grandparents: Per & Karin (generation 0)
        ├── ... 5 generations down to Lisa
        └── ... 4 generations down to Erik's parent, then Erik (so 5 vs 6)

        Actually for femmänning, ett släktled bort: min(gen)=5, removal=1
        So one person is 5 steps from ancestor, other is 6 steps.
        Let's make Lisa 5 steps and Erik 6 steps from ancestor Per & Karin.

        Per & Karin
        ├── Nils (gen 1)
        │   └── Britta (gen 2)
        │       └── Anders (gen 3)
        │           └── Ingrid (gen 4)
        │               └── Lisa's mother Maja (gen 5) → Lisa is gen 5 via Maja
        │                   (Lisa is Maja's child, but Maja connects to this tree)
        └── Johan (gen 1)
            └── Stina (gen 2)
                └── Lars (gen 3)
                    └── Elsa (gen 4)
                        └── Gunnar (gen 5)
                            └── Erik's father Olof (gen 6) → Erik is gen 6

    Wait - let me simplify. For the femmänning path, both need to be
    at generation 5 from the common ancestor. For "once removed", one is
    at gen 5 and the other at gen 6. Let me restructure:

    I'll connect Lisa at generation 5 and Erik at generation 6 from
    a second common ancestor pair (Per & Karin), giving femmänning ett
    släktled bort.
    """
    persons = []
    families = []

    def make_person(pid: str, given: str, surname: str, sex: str) -> Person:
        p = Person(id=pid, sex=sex, names=[Name(type="birth", given=given, surname=surname)])
        persons.append(p)
        return p

    def make_family(fid: str, partners: list[tuple[str, str]], children_links: list[tuple[str, str, str]]) -> Family:
        """Create family with partners and parent-child links.

        children_links: list of (child_id, parent_id, parentage_type)
        """
        partner_objs = [FamilyPartner(person_id=pid, role=role) for pid, role in partners]
        child_ids = list(dict.fromkeys(cl[0] for cl in children_links))  # unique, ordered
        links = [ParentChildLink(child_id=c, parent_id=p, parentage_type=pt) for c, p, pt in children_links]
        f = Family(id=fid, partners=partner_objs, children=child_ids, parent_child_links=links, event_ids=[])
        families.append(f)
        return f

    # ===================================================================
    # PATH 1: Second cousins (tremänning) — 3 generations each
    # Common ancestors: Gustaf & Anna
    # ===================================================================

    gustaf = make_person("p_gustaf", "Gustaf", "Andersson", "M")
    anna = make_person("p_anna", "Anna", "Persdotter", "F")

    # Their children: Karl and Maria
    karl = make_person("p_karl", "Karl", "Gustafsson", "M")
    maria = make_person("p_maria", "Maria", "Gustafsdotter", "F")

    make_family("f_gustaf_anna", [("p_gustaf", "father"), ("p_anna", "mother")], [
        ("p_karl", "p_gustaf", "biological"), ("p_karl", "p_anna", "biological"),
        ("p_maria", "p_gustaf", "biological"), ("p_maria", "p_anna", "biological"),
    ])

    # Karl's family → son Sven
    karl_wife = make_person("p_karl_wife", "Brita", "Larsdotter", "F")
    sven = make_person("p_sven", "Sven", "Karlsson", "M")
    make_family("f_karl", [("p_karl", "father"), ("p_karl_wife", "mother")], [
        ("p_sven", "p_karl", "biological"), ("p_sven", "p_karl_wife", "biological"),
    ])

    # Sven's family → daughter Lisa (TARGET A)
    maja = make_person("p_maja", "Maja", "Nilsdotter", "F")
    lisa = make_person("p_lisa", "Lisa", "Svensdotter", "F")
    make_family("f_sven", [("p_sven", "father"), ("p_maja", "mother")], [
        ("p_lisa", "p_sven", "biological"), ("p_lisa", "p_maja", "biological"),
    ])

    # Maria's family → son Olof
    maria_husband = make_person("p_maria_husb", "Erik", "Jonsson", "M")
    olof = make_person("p_olof", "Olof", "Eriksson", "M")
    make_family("f_maria", [("p_maria_husb", "father"), ("p_maria", "mother")], [
        ("p_olof", "p_maria_husb", "biological"), ("p_olof", "p_maria", "biological"),
    ])

    # Olof's family → son Erik (TARGET B)
    olof_wife = make_person("p_olof_wife", "Kerstin", "Hansdotter", "F")
    erik = make_person("p_erik", "Erik", "Olofsson", "M")
    make_family("f_olof", [("p_olof", "father"), ("p_olof_wife", "mother")], [
        ("p_erik", "p_olof", "biological"), ("p_erik", "p_olof_wife", "biological"),
    ])

    # ===================================================================
    # PATH 2: Fourth cousins once removed (femmänning, ett släktled bort)
    # Common ancestors: Per & Karin (5 generations back)
    # Lisa is 5 steps from Per & Karin
    # Erik is 6 steps from Per & Karin
    # ===================================================================

    per = make_person("p_per", "Per", "Mattsson", "M")
    karin = make_person("p_karin", "Karin", "Olofsdotter", "F")

    # Branch A (down to Lisa's mother Maja): Per→Nils→Britta→Anders→Maja
    nils = make_person("p_nils", "Nils", "Persson", "M")
    nils_wife = make_person("p_nils_wife", "Gertrud", "Svensdotter", "F")
    make_family("f_per_karin", [("p_per", "father"), ("p_karin", "mother")], [
        ("p_nils", "p_per", "biological"), ("p_nils", "p_karin", "biological"),
    ])

    britta = make_person("p_britta", "Britta", "Nilsdotter", "F")
    make_family("f_nils", [("p_nils", "father"), ("p_nils_wife", "mother")], [
        ("p_britta", "p_nils", "biological"), ("p_britta", "p_nils_wife", "biological"),
    ])

    anders = make_person("p_anders", "Anders", "Johansson", "M")
    britta_husb = make_person("p_britta_husb", "Johan", "Eriksson", "M")
    make_family("f_britta", [("p_britta_husb", "father"), ("p_britta", "mother")], [
        ("p_anders", "p_britta_husb", "biological"), ("p_anders", "p_britta", "biological"),
    ])

    anders_wife = make_person("p_anders_wife", "Lovisa", "Karlsdotter", "F")
    # Anders is parent of Maja (who is already Lisa's mother in f_sven)
    make_family("f_anders", [("p_anders", "father"), ("p_anders_wife", "mother")], [
        ("p_maja", "p_anders", "biological"), ("p_maja", "p_anders_wife", "biological"),
    ])
    # So Lisa's path via this line: Per → Nils → Britta → Anders → Maja → Lisa (5 steps)

    # Branch B (down to Erik): Per→Johan→Stina→Lars→Elsa→Gunnar→Olof
    # We need Erik to be 6 steps from Per.
    # Erik is already Olof's son. So we need Olof to be 5 steps from Per.
    # Per → Johan(1) → Stina(2) → Lars(3) → Elsa(4) → Olof(5) → Erik(6) ✓

    # But wait - we also need a second child of Per & Karin for branch B.
    # Let's add Johan as another child of Per & Karin.
    johan = make_person("p_johan", "Johan", "Persson", "M")

    # Update the Per & Karin family to include Johan
    # Actually let's just make a separate family for this branch or add Johan
    # to the existing one. Let me rebuild f_per_karin:
    families[:] = [f for f in families if f.id != "f_per_karin"]
    make_family("f_per_karin", [("p_per", "father"), ("p_karin", "mother")], [
        ("p_nils", "p_per", "biological"), ("p_nils", "p_karin", "biological"),
        ("p_johan", "p_per", "biological"), ("p_johan", "p_karin", "biological"),
    ])

    johan_wife = make_person("p_johan_wife", "Margareta", "Andersdotter", "F")
    stina = make_person("p_stina", "Stina", "Johansdotter", "F")
    make_family("f_johan", [("p_johan", "father"), ("p_johan_wife", "mother")], [
        ("p_stina", "p_johan", "biological"), ("p_stina", "p_johan_wife", "biological"),
    ])

    stina_husb = make_person("p_stina_husb", "Mikael", "Larsson", "M")
    lars = make_person("p_lars", "Lars", "Mikaelsson", "M")
    make_family("f_stina", [("p_stina_husb", "father"), ("p_stina", "mother")], [
        ("p_lars", "p_stina_husb", "biological"), ("p_lars", "p_stina", "biological"),
    ])

    lars_wife = make_person("p_lars_wife", "Helena", "Gustafsdotter", "F")
    elsa = make_person("p_elsa", "Elsa", "Larsdotter", "F")
    make_family("f_lars", [("p_lars", "father"), ("p_lars_wife", "mother")], [
        ("p_elsa", "p_lars", "biological"), ("p_elsa", "p_lars_wife", "biological"),
    ])

    elsa_husb = make_person("p_elsa_husb", "Daniel", "Svensson", "M")
    # Elsa is parent of Olof (who is already Erik's father)
    # But Olof already has parents (Maria's husband Erik Jonsson + Maria) from path 1.
    # We need a different connection. Let's make Elsa parent of Olof's wife Kerstin instead.
    # Then Erik's path: Per → Johan → Stina → Lars → Elsa → Kerstin → Erik (6 steps) ✓
    make_family("f_elsa", [("p_elsa_husb", "father"), ("p_elsa", "mother")], [
        ("p_olof_wife", "p_elsa_husb", "biological"), ("p_olof_wife", "p_elsa", "biological"),
    ])

    # Verify paths:
    # Lisa via path 2: Per(0) → Nils(1) → Britta(2) → Anders(3) → Maja(4) → Lisa(5) ← 5 steps
    # Erik via path 2: Per(0) → Johan(1) → Stina(2) → Lars(3) → Elsa(4) → Kerstin(5) → Erik(6) ← 6 steps
    # min(5,6) = 5 → femmänning, removal = |5-6| = 1 → "ett släktled bort"
    # Result: "femmänning, ett släktled bort" ✓

    metadata = ProjectMetadata(
        title="Demo - Släktskapsberäknare",
        main_person_id="p_lisa",
        created_by="Släktbuske",
        language="sv-SE",
    )

    return ProjectData(
        format="släktbuske-file",
        version="0.1",
        project=metadata,
        persons=persons,
        families=families,
        events=[],
        places=[],
        sources=[],
        media=[],
        repositories=[],
        dna_companies=[],
        dna_profiles=[],
        dna_matches=[],
        dna_segments=[],
        dna_clusters=[],
        dna_triangulations=[],
        research_notes=[],
    )


def main() -> None:
    """Launch the relationship dialog with the demo tree."""
    app = QApplication(sys.argv)

    data = build_demo_tree()

    # Quick sanity check with the calculator
    from slaktbusken.relationship.calculator import RelationshipCalculator
    calc = RelationshipCalculator(data)

    print("=== Demo: Lisa Svensdotter ↔ Erik Olofsson ===\n")

    # Show all paths (not just closest)
    paths = calc.find_relationships(
        "p_lisa", "p_erik",
        include_legal=True,
        closest_only=False,
        blood_priority=False,
    )
    print(f"Found {len(paths)} relationship path(s):\n")
    for i, path in enumerate(paths, 1):
        print(f"  {i}. {path.swedish_term}")
        print(f"     Type: {path.relationship_type}")
        print(f"     Generations: A={path.generations_a}, B={path.generations_b}")
        print(f"     Path: {' → '.join(path.path_nodes)}")
        print()

    # Launch the dialog
    from slaktbusken.ui.dialogs.relationship_dialog import RelationshipDialog
    dialog = RelationshipDialog(data=data)

    # Pre-select Lisa and Erik
    for i in range(dialog._combo_a.count()):
        if "Lisa" in dialog._combo_a.itemText(i):
            dialog._combo_a.setCurrentIndex(i)
            break
    for i in range(dialog._combo_b.count()):
        if "Erik Olofsson" in dialog._combo_b.itemText(i):
            dialog._combo_b.setCurrentIndex(i)
            break

    # Check "show all paths"
    dialog._check_all_paths.setChecked(True)

    dialog.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
