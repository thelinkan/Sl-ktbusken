"""Demo script to visually inspect the Repository Editor.

Run with:  python scripts/demo_repository_editor.py
"""

import sys

from PySide6.QtWidgets import QApplication

from slaktbusken.model.source import Repository, RepositoryRef, Source, StructuredReference
from slaktbusken.model.project import ProjectData, ProjectMetadata


def build_sample_data() -> ProjectData:
    """Create sample project data with repositories and sources for demo."""
    repositories = [
        Repository(
            id="repo_1",
            name="ArkivDigital",
            type="digital_archive",
            address="",
            phone=[],
            email=["info@arkivdigital.se"],
            web=["https://www.arkivdigital.se"],
            notes="Svensk digital arkivtjänst med kyrkböcker och annat material.",
            external_ids=["AD-001"],
        ),
        Repository(
            id="repo_2",
            name="Riksarkivet",
            type="archive",
            address="Fyrverkarbacken 13, 115 21 Stockholm",
            phone=["010-476 70 00"],
            email=["riksarkivet@riksarkivet.se"],
            web=["https://www.riksarkivet.se", "https://sok.riksarkivet.se"],
            notes="Sveriges nationella arkivmyndighet.",
            external_ids=[],
        ),
        Repository(
            id="repo_3",
            name="Landsarkivet i Härnösand",
            type="archive",
            address="Nybrogatan 17, 871 30 Härnösand",
            phone=["010-476 78 50"],
            email=[],
            web=["https://www.riksarkivet.se/harnosand"],
            notes="Regionalt arkiv för Norrland.",
            external_ids=[],
        ),
        Repository(
            id="repo_4",
            name="Ljusdals bibliotek",
            type="library",
            address="Bjuråkersvägen 15, 827 30 Ljusdal",
            phone=["0651-180 00"],
            email=["bibliotek@ljusdal.se"],
            web=[],
            notes="Lokalt bibliotek med hembygdslitteratur.",
            external_ids=[],
        ),
        Repository(
            id="repo_5",
            name="Hälsinglands museum",
            type="museum",
            address="Stadsparken, 824 41 Hudiksvall",
            phone=["0650-190 00"],
            email=["info@halsinglandsmuseum.se"],
            web=["https://www.halsinglandsmuseum.se"],
            notes="Kulturhistoriskt museum för Hälsingland.",
            external_ids=["HSM-REG-42"],
        ),
        Repository(
            id="repo_6",
            name="Ljusdals kyrkokontor",
            type="church_office",
            address="Kyrkogatan 1, 827 30 Ljusdal",
            phone=["0651-175 00"],
            email=["ljusdal.pastorat@svenskakyrkan.se"],
            web=[],
            notes="",
            external_ids=[],
        ),
    ]

    # Sources referencing some repos (to test deletion warnings)
    sources = [
        Source(
            id="source_1",
            provider="ArkivDigital",
            source_type="church_book",
            title="Ljusdal AI:23d",
            repository_refs=[RepositoryRef(repository_id="repo_1")],
        ),
        Source(
            id="source_2",
            provider="ArkivDigital",
            source_type="church_book",
            title="Ljusdal CI:7",
            repository_refs=[RepositoryRef(repository_id="repo_1")],
        ),
        Source(
            id="source_3",
            provider="Riksarkivet",
            source_type="database",
            title="Sveriges dödbok",
            repository_refs=[RepositoryRef(repository_id="repo_2")],
        ),
    ]

    return ProjectData(
        project=ProjectMetadata(title="Demo-projekt"),
        repositories=repositories,
        sources=sources,
    )


def main() -> None:
    """Launch the Repository Editor with sample data."""
    app = QApplication(sys.argv)
    project_data = build_sample_data()

    from slaktbusken.ui.editors.repository_editor import RepositoryEditor

    editor = RepositoryEditor(project_data=project_data)
    editor.setWindowTitle("Demo — Arkivredigerare")
    editor.resize(950, 650)
    editor.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
