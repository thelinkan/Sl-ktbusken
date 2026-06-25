"""JSON serialization and deserialization for ProjectData.

Provides functions to convert ProjectData to/from JSON strings,
with format and version as the first keys in the output.
"""

from __future__ import annotations

import json
from dataclasses import fields as dc_fields
from typing import Any, Optional, get_args, get_origin

from slaktbusken.model.dna import (
    DnaCluster,
    DnaCompany,
    DnaMatch,
    DnaProfile,
    DnaSegment,
    DnaTriangulation,
)
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.media import Annotation, LinkedEntity, MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import ExternalId, Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.research_note import ResearchNote
from slaktbusken.model.source import Repository, RepositoryRef, Source, StructuredReference


def serialize(data: ProjectData) -> str:
    """Serialize ProjectData to a JSON string (UTF-8).

    The output JSON has format and version as the first keys, followed
    by format_version (for quick version checks), project metadata,
    and all entity arrays.

    Args:
        data: The ProjectData instance to serialize.

    Returns:
        A JSON string representation of the project data.
    """
    output: dict[str, Any] = {}
    # format and version first (Requirement 27.1, 27.7).
    output["format"] = data.format
    output["version"] = data.version
    output["format_version"] = data.version

    # Project metadata.
    output["project"] = _serialize_dataclass(data.project)

    # All entity arrays.
    entity_fields = [
        "persons", "families", "events", "places", "sources",
        "media", "repositories", "dna_companies", "dna_profiles",
        "dna_matches", "dna_segments", "dna_clusters",
        "dna_triangulations", "research_notes",
    ]
    for field_name in entity_fields:
        items = getattr(data, field_name, [])
        output[field_name] = [_serialize_dataclass(item) for item in items]

    return json.dumps(output, ensure_ascii=False, indent=2)


def deserialize(json_str: str) -> ProjectData:
    """Deserialize a JSON string into a ProjectData instance.

    Expects the JSON structure produced by serialize(), with
    format, version, project, and entity arrays.

    Args:
        json_str: The JSON string to deserialize.

    Returns:
        A ProjectData instance populated from the JSON data.
    """
    raw = json.loads(json_str)

    project_data = ProjectData(
        format=raw.get("format", "släktbuske-file"),
        version=raw.get("version", "0.1"),
        project=_deserialize_typed(ProjectMetadata, raw.get("project", {})),
    )

    # Deserialize entity arrays with proper nested type reconstruction.
    _deserialize_entities(project_data, raw)

    return project_data


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_dataclass(obj: Any) -> dict[str, Any]:
    """Recursively serialize a dataclass to a dict, omitting None optional fields.

    Only omits None if the field has a default value (i.e., it's truly optional
    in the constructor sense). Required positional args that happen to be
    Optional[X] are always included even when None.

    Args:
        obj: A dataclass instance.

    Returns:
        A dictionary representation suitable for JSON serialization.
    """
    if not hasattr(obj, "__dataclass_fields__"):
        return obj

    result: dict[str, Any] = {}
    for f in dc_fields(obj):
        value = getattr(obj, f.name)
        # Omit None values only for fields that have a default value.
        if value is None and _is_optional_field(f) and _has_default(f):
            continue
        # Omit empty lists for fields that have default_factory=list.
        if value == [] and _has_default_factory_list(f):
            continue
        result[f.name] = _serialize_value(value)
    return result


def _serialize_value(value: Any) -> Any:
    """Serialize a single value, handling nested dataclasses and lists."""
    if hasattr(value, "__dataclass_fields__"):
        return _serialize_dataclass(value)
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    return value


def _is_optional_field(f: Any) -> bool:
    """Check if a dataclass field has an Optional type annotation."""
    origin = get_origin(f.type)
    if origin is not None:
        # Handle Union[X, None] which is Optional[X]
        args = get_args(f.type)
        return type(None) in args

    # Handle string annotations like "Optional[str]"
    type_str = str(f.type) if not isinstance(f.type, str) else f.type
    return "Optional" in type_str or "None" in type_str


def _has_default(f: Any) -> bool:
    """Check if a dataclass field has a default value or default_factory.

    Fields without defaults are required positional arguments and should
    always be serialized, even when their value is None.
    """
    import dataclasses
    return (
        f.default is not dataclasses.MISSING
        or f.default_factory is not dataclasses.MISSING
    )


def _has_default_factory_list(f: Any) -> bool:
    """Check if a dataclass field has default_factory=list.

    Used to determine whether an empty list value can be safely omitted
    from serialized output.
    """
    import dataclasses
    return (
        f.default_factory is not dataclasses.MISSING
        and f.default_factory is list
    )


# ---------------------------------------------------------------------------
# Deserialization helpers
# ---------------------------------------------------------------------------

# Registry mapping entity field names to their dataclass types and nested types.
_ENTITY_MAP: dict[str, type] = {
    "persons": Person,
    "families": Family,
    "events": Event,
    "places": Place,
    "sources": Source,
    "repositories": Repository,
    "media": MediaItem,
    "dna_companies": DnaCompany,
    "dna_profiles": DnaProfile,
    "dna_matches": DnaMatch,
    "dna_segments": DnaSegment,
    "dna_clusters": DnaCluster,
    "dna_triangulations": DnaTriangulation,
    "research_notes": ResearchNote,
}

# Mapping of (parent_class, field_name) -> element type for list fields
# containing nested dataclasses.
_NESTED_LIST_TYPES: dict[tuple[type, str], type] = {
    (Person, "names"): Name,
    (Family, "partners"): FamilyPartner,
    (Family, "parent_child_links"): ParentChildLink,
    (Event, "participants"): Participant,
    (Source, "repository_refs"): RepositoryRef,
    (MediaItem, "linked_entities"): LinkedEntity,
    (MediaItem, "annotations"): Annotation,
    (ResearchNote, "linked_entities"): LinkedEntity,
    (Place, "external_ids"): ExternalId,
}

# Mapping of (parent_class, field_name) -> type for optional nested dataclass fields.
_NESTED_OPTIONAL_TYPES: dict[tuple[type, str], type] = {
    (Event, "date"): DateValue,
    (Event, "place"): PlaceRef,
    (Source, "structured_reference"): StructuredReference,
}

# Mapping of nested list fields within nested types.
_DEEP_NESTED_LIST_TYPES: dict[tuple[type, str], type] = {
    (DateValue, "source_refs"): SourceRef,
    (PlaceRef, "source_refs"): SourceRef,
}


def _deserialize_entities(project_data: ProjectData, raw: dict[str, Any]) -> None:
    """Deserialize entity arrays from raw JSON dict into ProjectData.

    Args:
        project_data: The ProjectData instance to populate.
        raw: The full parsed JSON dictionary.
    """
    for field_name, cls in _ENTITY_MAP.items():
        raw_items = raw.get(field_name, [])
        if raw_items:
            deserialized = [_deserialize_typed(cls, item) for item in raw_items]
            setattr(project_data, field_name, deserialized)


def _deserialize_typed(cls: type, data: Any) -> Any:
    """Deserialize a dict into a specific dataclass type with nested handling.

    Args:
        cls: The target dataclass type.
        data: The raw dict (or primitive) to deserialize.

    Returns:
        An instance of cls.
    """
    if not isinstance(data, dict):
        return data

    kwargs: dict[str, Any] = {}
    valid_fields = {f.name: f for f in dc_fields(cls)}

    for field_name, f in valid_fields.items():
        if field_name not in data:
            continue

        value = data[field_name]

        # Check if this is a nested list of dataclasses.
        nested_list_type = _NESTED_LIST_TYPES.get((cls, field_name))
        if nested_list_type is not None and isinstance(value, list):
            kwargs[field_name] = [
                _deserialize_typed(nested_list_type, item) for item in value
            ]
            continue

        # Check if this is a nested optional dataclass.
        nested_opt_type = _NESTED_OPTIONAL_TYPES.get((cls, field_name))
        if nested_opt_type is not None and value is not None:
            kwargs[field_name] = _deserialize_typed(nested_opt_type, value)
            continue

        # Check deep nested list types.
        deep_nested_type = _DEEP_NESTED_LIST_TYPES.get((cls, field_name))
        if deep_nested_type is not None and isinstance(value, list):
            kwargs[field_name] = [
                _deserialize_typed(deep_nested_type, item) for item in value
            ]
            continue

        kwargs[field_name] = value

    # Build instance with only the fields present in data + defaults for rest.
    try:
        return cls(**kwargs)
    except TypeError:
        # Fallback: try providing only fields that don't need extra args.
        required_kwargs = {}
        for f in dc_fields(cls):
            if f.name in kwargs:
                required_kwargs[f.name] = kwargs[f.name]
        return cls(**required_kwargs)
