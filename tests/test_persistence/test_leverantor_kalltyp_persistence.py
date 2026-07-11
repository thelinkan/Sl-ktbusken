"""Verification tests for Leverantör/Källtyp persistence round-trip.

Confirms that leverantorer and kalltyper lists serialize and deserialize
correctly, including backward compatibility with old project files that
lack these fields.

# Feature: source-management
# Validates: Requirements 3.7, 9.3
"""

from __future__ import annotations

from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.source import Kalltyp, Leverantor
from slaktbusken.persistence.serialization import deserialize, serialize


def test_leverantor_kalltyp_round_trip() -> None:
    """Leverantorer and kalltyper survive a serialize/deserialize cycle."""
    lev = Leverantor(id="lev_1", name="Arkiv Digital", comment="Online archive")
    kt = Kalltyp(
        id="kt_1",
        leverantor_id="lev_1",
        name="Husförhörslängd",
        comment="Church records",
        root_url="https://example.com",
    )

    project_data = ProjectData(
        format="släktbuske-file",
        version="0.1",
        project=ProjectMetadata(
            title="Test",
            main_person_id="person_1",
            created_by="Test",
            language="sv-SE",
        ),
        leverantorer=[lev],
        kalltyper=[kt],
    )

    json_str = serialize(project_data)
    restored = deserialize(json_str)

    # Verify leverantorer
    assert len(restored.leverantorer) == 1
    assert restored.leverantorer[0].id == "lev_1"
    assert restored.leverantorer[0].name == "Arkiv Digital"
    assert restored.leverantorer[0].comment == "Online archive"

    # Verify kalltyper
    assert len(restored.kalltyper) == 1
    assert restored.kalltyper[0].id == "kt_1"
    assert restored.kalltyper[0].leverantor_id == "lev_1"
    assert restored.kalltyper[0].name == "Husförhörslängd"
    assert restored.kalltyper[0].comment == "Church records"
    assert restored.kalltyper[0].root_url == "https://example.com"


def test_backward_compat_missing_leverantorer_kalltyper() -> None:
    """Old project files without leverantorer/kalltyper deserialize with empty lists."""
    json_str = """{
  "format": "släktbuske-file",
  "version": "0.1",
  "project": {
    "title": "Old Project",
    "main_person_id": "person_1",
    "created_by": "Test",
    "language": "sv-SE"
  },
  "persons": [],
  "families": [],
  "events": [],
  "places": [],
  "sources": [],
  "media": [],
  "repositories": []
}"""

    restored = deserialize(json_str)

    assert restored.leverantorer == []
    assert restored.kalltyper == []
