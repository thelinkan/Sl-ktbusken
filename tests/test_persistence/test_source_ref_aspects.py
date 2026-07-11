"""Property-based test for SourceRef aspects serialization round-trip.

# Feature: source-management, Property 16: Aspect persistence round-trip
# Validates: Requirements 9.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.event import DateValue, Event, Participant, SourceRef
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.serialization import deserialize, serialize

# The valid aspects that can be assigned to a SourceRef
VALID_ASPECTS = ["date", "place", "parents", "witnesses", "cause_of_death", "spouse"]


@given(aspects=st.lists(st.sampled_from(VALID_ASPECTS), unique=True))
@settings(max_examples=100)
def test_source_ref_aspects_round_trip(aspects: list[str]) -> None:
    """**Validates: Requirements 9.3**

    For any SourceRef with an arbitrary subset of valid aspects selected,
    serializing and then deserializing the SourceRef SHALL produce an
    identical aspects list.
    """
    source_ref = SourceRef(source_id="source_1", quality="primary", aspects=aspects)
    date_value = DateValue(value="1900-01-01", precision="day", source_refs=[source_ref])
    event = Event(
        id="event_1",
        type="birth",
        participants=[Participant(person_id="person_1", role="child")],
        date=date_value,
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
        events=[event],
    )

    json_str = serialize(project_data)
    restored = deserialize(json_str)

    restored_aspects = restored.events[0].date.source_refs[0].aspects
    assert restored_aspects == aspects


def test_source_ref_without_aspects_field_backward_compat() -> None:
    """A SourceRef serialized WITHOUT an aspects field (old data) deserializes with aspects=[].

    **Validates: Requirements 9.3**

    This simulates loading a project file created before the aspects field
    was added. The JSON will not contain an "aspects" key for the SourceRef,
    and deserialization should produce an empty list as the default.
    """
    # Manually construct JSON without the "aspects" key in the SourceRef
    json_str = """{
  "format": "släktbuske-file",
  "version": "0.1",
  "format_version": "0.1",
  "project": {
    "title": "Test",
    "main_person_id": "person_1",
    "created_by": "Test",
    "language": "sv-SE"
  },
  "persons": [],
  "families": [],
  "events": [
    {
      "id": "event_1",
      "type": "birth",
      "participants": [{"person_id": "person_1", "role": "child"}],
      "date": {
        "value": "1900-01-01",
        "precision": "day",
        "source_refs": [
          {"source_id": "source_1", "quality": "primary", "note": ""}
        ]
      }
    }
  ],
  "places": [],
  "sources": [],
  "media": [],
  "repositories": [],
  "dna_companies": [],
  "dna_profiles": [],
  "dna_matches": [],
  "dna_segments": [],
  "dna_clusters": [],
  "dna_triangulations": [],
  "research_notes": []
}"""

    restored = deserialize(json_str)
    restored_source_ref = restored.events[0].date.source_refs[0]

    assert restored_source_ref.aspects == []
