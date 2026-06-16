"""Demo script to visually inspect the Source Editor.

Run with:  python scripts/demo_source_editor.py
"""

import sys

from PySide6.QtWidgets import QApplication

from slaktbusken.model.source import Repository, RepositoryRef, Source, StructuredReference
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.project import ProjectData, ProjectMetadata


def build_sample_data() -> ProjectData:
    """Create sample project data with sources, repos, and media for demo."""
    repositories = [
        Repository(id="repo_1", name="ArkivDigital", type="digital_archive"),
        Repository(id="repo_2", name="Riksarkivet", type="archive", address="Fyrverkarbacken 13, Stockholm"),
        Repository(id="repo_3", name="Landsarkivet i Härnösand", type="archive"),
    ]

    sources = [
        Source(
            id="source_1",
            provider="ArkivDigital",
            source_type="church_book",
            title="Ljusdal AI:23d (1883-1887)",
            reference_text="Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915",
            provider_ref="v136004.b88",
            structured_reference=StructuredReference(fields={
                "parish": "Ljusdal",
                "county_code": "X",
                "series": "AI",
                "volume": "23d",
                "years": "1883-1887",
                "image": "23",
                "page": "915",
            }),
            repository_refs=[RepositoryRef(repository_id="repo_1")],
        ),
        Source(
            id="source_2",
            provider="ArkivDigital",
            source_type="church_book",
            title="Ljusdal CI:7 (1850-1861)",
            reference_text="Ljusdal (X) CI:7 (1850-1861) Bild: 44",
            structured_reference=StructuredReference(fields={
                "parish": "Ljusdal",
                "county_code": "X",
                "series": "CI",
                "volume": "7",
                "years": "1850-1861",
                "image": "44",
            }),
            repository_refs=[RepositoryRef(repository_id="repo_1")],
        ),
        Source(
            id="source_3",
            provider="Riksarkivet",
            source_type="database",
            title="Sveriges dödbok 1901-2013",
            structured_reference=StructuredReference(fields={
                "database_name": "Sveriges dödbok",
                "record_id": "DDB-1920-1102-LJU-001",
            }),
            repository_refs=[RepositoryRef(repository_id="repo_2")],
        ),
        Source(
            id="source_4",
            provider="",
            source_type="death_notice",
            title="Dödsannons Andersson 1920",
            structured_reference=StructuredReference(fields={
                "newspaper": "Ljusdals-Posten",
                "publication_date": "1920-11-05",
                "page": "4",
            }),
        ),
        Source(
            id="source_5",
            provider="",
            source_type="newspaper",
            title="Bröllopsnotis 1875",
            structured_reference=StructuredReference(fields={
                "newspaper": "Hudiksvalls Tidning",
                "date": "1875-06-25",
                "page": "3",
                "article_title": "Vigsel i Ljusdal",
            }),
        ),
        Source(
            id="source_6",
            provider="",
            source_type="photograph",
            title="Porträttfoto ca 1890",
            reference_text="Fotograf okänd, ca 1890",
        ),
    ]

    media = [
        MediaItem(
            id="media_1",
            type="source_image",
            file="source-image/ljusdal_ai23d_b23.jpg",
            title="Ljusdal AI:23d bild 23",
            linked_entities=[LinkedEntity(entity_type="source", entity_id="source_1", role="source_scan")],
        ),
        MediaItem(
            id="media_2",
            type="death_notice",
            file="death-notice/andersson_1920.jpg",
            title="Dödsannons Andersson",
            linked_entities=[LinkedEntity(entity_type="source", entity_id="source_4", role="source_scan")],
        ),
        MediaItem(
            id="media_3",
            type="photo",
            file="photos/portrait_1890.jpg",
            title="Porträtt ca 1890",
            linked_entities=[],
        ),
    ]

    return ProjectData(
        project=ProjectMetadata(title="Demo-projekt"),
        sources=sources,
        repositories=repositories,
        media=media,
    )


def main() -> None:
    """Launch the Source Editor with sample data."""
    app = QApplication(sys.argv)
    project_data = build_sample_data()

    from slaktbusken.ui.editors.source_editor import SourceEditor

    editor = SourceEditor(project_data=project_data)
    editor.setWindowTitle("Demo — Källredigerare")
    editor.resize(1100, 750)
    editor.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
