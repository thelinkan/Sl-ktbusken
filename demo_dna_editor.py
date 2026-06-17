"""Demo script for the DNA Editor widget.

Launches the DnaEditor with sample project data containing persons,
media, DNA companies, profiles, matches, segments, clusters, and
triangulations so all tabs can be explored interactively.
"""

import sys

from PySide6.QtWidgets import QApplication

from slaktbusken.model.dna import (
    DnaCluster,
    DnaCompany,
    DnaMatch,
    DnaProfile,
    DnaSegment,
    DnaTriangulation,
)
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.editors.dna_editor import DnaEditor


def create_sample_data() -> ProjectData:
    """Create sample project data for the demo."""
    data = ProjectData(
        project=ProjectMetadata(title="Demo-projekt"),
        persons=[
            Person(
                id="person_1",
                sex="M",
                names=[Name(type="birth", given="Erik", surname="Andersson")],
            ),
            Person(
                id="person_2",
                sex="F",
                names=[Name(type="birth", given="Anna", surname="Svensson")],
            ),
            Person(
                id="person_3",
                sex="M",
                names=[Name(type="birth", given="Lars", surname="Johansson")],
            ),
            Person(
                id="person_4",
                sex="F",
                names=[Name(type="birth", given="Maria", surname="Nilsson")],
            ),
        ],
        media=[
            MediaItem(
                id="media_logo_1",
                type="logo",
                file="logos/ancestry.png",
                title="Ancestry Logo",
                linked_entities=[
                    LinkedEntity(
                        entity_type="source",
                        entity_id="src_1",
                        role="logo",
                    )
                ],
            ),
        ],
        dna_companies=[
            DnaCompany(
                id="company_1",
                name="AncestryDNA",
                logo_media_id="media_logo_1",
                description="Världens största DNA-databas för släktforskning.",
            ),
            DnaCompany(
                id="company_2",
                name="MyHeritage DNA",
                description="Internationell DNA-tjänst med fokus på etnisk bakgrund.",
            ),
        ],
        dna_profiles=[
            DnaProfile(
                id="profile_1",
                person_id="person_1",
                company_id="company_1",
                test_type="autosomal",
                kit_name="Erik A. kit",
                kit_id="ANC-123456",
                admin_person_id="person_1",
                admin_status="self",
                notes="Testat 2022-03.",
            ),
            DnaProfile(
                id="profile_2",
                person_id="person_2",
                company_id="company_1",
                test_type="autosomal",
                kit_name="Anna S. kit",
                kit_id="ANC-789012",
                admin_person_id="person_2",
                admin_status="self",
                notes="Testat 2023-01.",
            ),
            DnaProfile(
                id="profile_3",
                person_id="person_3",
                company_id="company_2",
                test_type="y-dna",
                kit_name="Lars J. Y-DNA",
                kit_id="MH-555111",
                admin_person_id="person_1",
                admin_status="managed_by_user",
                notes="Y-DNA test via MyHeritage.",
            ),
        ],
        dna_matches=[
            DnaMatch(
                id="match_1",
                profile1_id="profile_1",
                profile2_id="profile_2",
                shared_cm=1750.5,
                shared_percentage=24.3,
                segment_count=42,
                largest_segment_cm=112.0,
                match_source="internal",
                notes="Syskon-matchning.",
            ),
            DnaMatch(
                id="match_2",
                profile1_id="profile_1",
                profile2_id="profile_3",
                shared_cm=850.2,
                shared_percentage=11.8,
                segment_count=28,
                largest_segment_cm=75.3,
                match_source="internal",
                notes="Kusin-matchning.",
            ),
        ],
        dna_segments=[
            DnaSegment(
                id="seg_1",
                match_id="match_1",
                chromosome="1",
                start_position=10000000,
                end_position=45000000,
                cm=35.2,
                snp_count=4200,
            ),
            DnaSegment(
                id="seg_2",
                match_id="match_1",
                chromosome="7",
                start_position=5000000,
                end_position=30000000,
                cm=28.1,
                snp_count=3100,
            ),
            DnaSegment(
                id="seg_3",
                match_id="match_2",
                chromosome="7",
                start_position=8000000,
                end_position=28000000,
                cm=22.5,
                snp_count=2800,
            ),
        ],
        dna_clusters=[
            DnaCluster(
                id="cluster_1",
                name="Andersson-grenen",
                notes="Kluster med matchningar från Andersson-sidan.",
                company_ids=["company_1"],
                person_ids=["person_1", "person_2"],
                dna_match_ids=["match_1"],
                color="#4488CC",
            ),
        ],
        dna_triangulations=[
            DnaTriangulation(
                id="tri_1",
                company_id="company_1",
                chromosome="7",
                overlap_start=8000000,
                overlap_end=28000000,
                segment_ids=["seg_2", "seg_3"],
                profile_ids=["profile_1", "profile_2", "profile_3"],
                cluster_id="cluster_1",
                notes="Triangulering på kromosom 7 — delade segment mellan tre profiler.",
            ),
        ],
    )
    return data


def main() -> None:
    """Launch the DNA editor demo."""
    app = QApplication(sys.argv)
    app.setApplicationName("Släktbusken – DNA Editor Demo")

    data = create_sample_data()
    editor = DnaEditor(project_data=data)
    editor.setWindowTitle("DNA-redigerare (Demo)")
    editor.resize(1200, 800)
    editor.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
