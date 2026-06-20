"""Validation service for cross-entity referential integrity checks.

ValidationService provides project-wide validation that goes beyond
per-entity structural checks. It verifies that all ID references
between entities (person_id, place_id, source_id, media_id, etc.)
point to entities that actually exist within the project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from slaktbusken.model.dna import (
    DnaCluster,
    DnaCompany,
    DnaMatch,
    DnaProfile,
    DnaSegment,
    DnaTriangulation,
)
from slaktbusken.model.event import Event
from slaktbusken.model.family import Family
from slaktbusken.model.media import MediaItem
from slaktbusken.model.person import Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_note import ResearchNote
from slaktbusken.model.source import Repository, Source
from slaktbusken.model.validators import (
    validate_dna_cluster,
    validate_dna_match,
    validate_dna_profile,
    validate_dna_segment,
    validate_dna_triangulation,
    validate_event,
    validate_family,
    validate_media_item,
    validate_person,
    validate_place,
    validate_repository,
    validate_source,
)


@dataclass
class ValidationError:
    """A single validation error with context about the offending entity.

    Attributes:
        entity_type: The type of entity that has the error (e.g. 'Person', 'Family').
        entity_id: The ID of the entity with the error.
        message: A human-readable description of the validation failure.
    """

    entity_type: str
    entity_id: str
    message: str


@dataclass
class _IdSets:
    """Pre-computed ID lookup sets for referential integrity checks."""

    person_ids: set[str] = field(default_factory=set)
    family_ids: set[str] = field(default_factory=set)
    event_ids: set[str] = field(default_factory=set)
    place_ids: set[str] = field(default_factory=set)
    source_ids: set[str] = field(default_factory=set)
    media_ids: set[str] = field(default_factory=set)
    repository_ids: set[str] = field(default_factory=set)
    dna_company_ids: set[str] = field(default_factory=set)
    dna_profile_ids: set[str] = field(default_factory=set)
    dna_match_ids: set[str] = field(default_factory=set)
    dna_segment_ids: set[str] = field(default_factory=set)
    dna_cluster_ids: set[str] = field(default_factory=set)


class ValidationService:
    """Cross-entity referential integrity checks, pre-save validation.

    This service performs two levels of validation:

    1. Per-entity structural validation (delegated to model validators).
    2. Cross-entity referential integrity — ensuring that all foreign-key-like
       ID references point to entities that exist in the project.
    """

    def validate_entity(self, entity: Any, project_data: ProjectData) -> list[ValidationError]:
        """Validate a single entity in the context of the full project.

        Runs both structural validation and referential integrity checks
        for the given entity against the current project state.

        Args:
            entity: The entity instance to validate.
            project_data: The full project data providing context for reference checks.

        Returns:
            A list of ValidationError instances. Empty if the entity is valid.
        """
        id_sets = self._build_id_sets(project_data)
        return self._validate_single(entity, id_sets, project_data)

    def validate_project(self, project_data: ProjectData) -> list[ValidationError]:
        """Run all validators across the entire project before save.

        Performs structural validation on every entity and checks all
        cross-entity referential integrity constraints.

        Args:
            project_data: The full project data to validate.

        Returns:
            A list of ValidationError instances. Empty if the project is valid.
        """
        errors: list[ValidationError] = []
        id_sets = self._build_id_sets(project_data)

        for person in project_data.persons:
            errors.extend(self._validate_single(person, id_sets, project_data))

        for family in project_data.families:
            errors.extend(self._validate_single(family, id_sets, project_data))

        for event in project_data.events:
            errors.extend(self._validate_single(event, id_sets, project_data))

        for place in project_data.places:
            errors.extend(self._validate_single(place, id_sets, project_data))

        for source in project_data.sources:
            errors.extend(self._validate_single(source, id_sets, project_data))

        for media_item in project_data.media:
            errors.extend(self._validate_single(media_item, id_sets, project_data))

        for repository in project_data.repositories:
            errors.extend(self._validate_single(repository, id_sets, project_data))

        for profile in project_data.dna_profiles:
            errors.extend(self._validate_single(profile, id_sets, project_data))

        for match in project_data.dna_matches:
            errors.extend(self._validate_single(match, id_sets, project_data))

        for segment in project_data.dna_segments:
            errors.extend(self._validate_single(segment, id_sets, project_data))

        for cluster in project_data.dna_clusters:
            errors.extend(self._validate_single(cluster, id_sets, project_data))

        for triangulation in project_data.dna_triangulations:
            errors.extend(self._validate_single(triangulation, id_sets, project_data))

        return errors

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_id_sets(self, project_data: ProjectData) -> _IdSets:
        """Build lookup sets of all entity IDs in the project."""
        return _IdSets(
            person_ids={p.id for p in project_data.persons},
            family_ids={f.id for f in project_data.families},
            event_ids={e.id for e in project_data.events},
            place_ids={p.id for p in project_data.places},
            source_ids={s.id for s in project_data.sources},
            media_ids={m.id for m in project_data.media},
            repository_ids={r.id for r in project_data.repositories},
            dna_company_ids={c.id for c in project_data.dna_companies},
            dna_profile_ids={p.id for p in project_data.dna_profiles},
            dna_match_ids={m.id for m in project_data.dna_matches},
            dna_segment_ids={s.id for s in project_data.dna_segments},
            dna_cluster_ids={c.id for c in project_data.dna_clusters},
        )

    def _validate_single(
        self, entity: Any, id_sets: _IdSets, project_data: ProjectData
    ) -> list[ValidationError]:
        """Validate a single entity: structural + referential integrity."""
        if isinstance(entity, Person):
            return self._validate_person(entity, id_sets)
        elif isinstance(entity, Family):
            return self._validate_family(entity, id_sets)
        elif isinstance(entity, Event):
            return self._validate_event(entity, id_sets)
        elif isinstance(entity, Place):
            return self._validate_place(entity, id_sets, project_data)
        elif isinstance(entity, Source):
            return self._validate_source(entity, id_sets)
        elif isinstance(entity, MediaItem):
            return self._validate_media_item(entity, id_sets)
        elif isinstance(entity, Repository):
            return self._validate_repository(entity)
        elif isinstance(entity, DnaProfile):
            return self._validate_dna_profile(entity, id_sets)
        elif isinstance(entity, DnaMatch):
            return self._validate_dna_match(entity, id_sets)
        elif isinstance(entity, DnaSegment):
            return self._validate_dna_segment(entity, id_sets)
        elif isinstance(entity, DnaCluster):
            return self._validate_dna_cluster(entity, id_sets)
        elif isinstance(entity, DnaTriangulation):
            return self._validate_dna_triangulation(entity, id_sets)
        return []

    def _validate_person(self, person: Person, id_sets: _IdSets) -> list[ValidationError]:
        """Validate a person: structural + media/event references."""
        errors: list[ValidationError] = []

        # Structural validation
        structural = validate_person(person, valid_event_ids=id_sets.event_ids)
        for msg in structural:
            errors.append(ValidationError("Person", person.id, msg))

        # profile_media_id reference
        if person.profile_media_id is not None:
            if person.profile_media_id not in id_sets.media_ids:
                errors.append(ValidationError(
                    "Person", person.id,
                    f"profile_media_id '{person.profile_media_id}' refererar inte till ett giltigt mediaobjekt."
                ))

        return errors

    def _validate_family(self, family: Family, id_sets: _IdSets) -> list[ValidationError]:
        """Validate a family: structural + person/event references."""
        errors: list[ValidationError] = []

        # Structural validation with person_id cross-check
        structural = validate_family(family, valid_person_ids=id_sets.person_ids)
        for msg in structural:
            errors.append(ValidationError("Family", family.id, msg))

        # event_ids reference existing events
        for event_id in family.event_ids:
            if event_id not in id_sets.event_ids:
                errors.append(ValidationError(
                    "Family", family.id,
                    f"event_id '{event_id}' refererar inte till en giltig händelse."
                ))

        return errors

    def _validate_event(self, event: Event, id_sets: _IdSets) -> list[ValidationError]:
        """Validate an event: structural + person/place/source/media references."""
        errors: list[ValidationError] = []

        # Structural validation
        structural = validate_event(event)
        for msg in structural:
            errors.append(ValidationError("Event", event.id, msg))

        # Participant person_id references
        for idx, participant in enumerate(event.participants):
            if participant.person_id not in id_sets.person_ids:
                errors.append(ValidationError(
                    "Event", event.id,
                    f"participants[{idx}] person_id '{participant.person_id}' refererar inte till en giltig person."
                ))

        # Place reference
        if event.place is not None:
            if event.place.place_id not in id_sets.place_ids:
                errors.append(ValidationError(
                    "Event", event.id,
                    f"place.place_id '{event.place.place_id}' refererar inte till en giltig plats."
                ))
            # Source refs within place
            for sr_idx, sr in enumerate(event.place.source_refs):
                if sr.source_id not in id_sets.source_ids:
                    errors.append(ValidationError(
                        "Event", event.id,
                        f"place.source_refs[{sr_idx}] source_id '{sr.source_id}' refererar inte till en giltig källa."
                    ))

        # Date source refs
        if event.date is not None:
            for sr_idx, sr in enumerate(event.date.source_refs):
                if sr.source_id not in id_sets.source_ids:
                    errors.append(ValidationError(
                        "Event", event.id,
                        f"date.source_refs[{sr_idx}] source_id '{sr.source_id}' refererar inte till en giltig källa."
                    ))

        # media_ids references
        for media_id in event.media_ids:
            if media_id not in id_sets.media_ids:
                errors.append(ValidationError(
                    "Event", event.id,
                    f"media_id '{media_id}' refererar inte till ett giltigt mediaobjekt."
                ))

        return errors

    def _validate_place(
        self, place: Place, id_sets: _IdSets, project_data: ProjectData
    ) -> list[ValidationError]:
        """Validate a place: structural + parent_place_id reference."""
        errors: list[ValidationError] = []

        # Build a place lookup for hierarchy validation
        place_lookup = {p.id: p for p in project_data.places}
        structural = validate_place(place, place_lookup=place_lookup)
        for msg in structural:
            errors.append(ValidationError("Place", place.id, msg))

        # parent_place_id reference (if not already caught by structural)
        if place.parent_place_id is not None:
            if place.parent_place_id not in id_sets.place_ids:
                errors.append(ValidationError(
                    "Place", place.id,
                    f"parent_place_id '{place.parent_place_id}' refererar inte till en giltig plats."
                ))

        return errors

    def _validate_source(self, source: Source, id_sets: _IdSets) -> list[ValidationError]:
        """Validate a source: structural + media/repository references."""
        errors: list[ValidationError] = []

        # Structural validation
        structural = validate_source(source)
        for msg in structural:
            errors.append(ValidationError("Source", source.id, msg))

        # media_ids references
        for media_id in source.media_ids:
            if media_id not in id_sets.media_ids:
                errors.append(ValidationError(
                    "Source", source.id,
                    f"media_id '{media_id}' refererar inte till ett giltigt mediaobjekt."
                ))

        # repository_refs references
        for idx, repo_ref in enumerate(source.repository_refs):
            if repo_ref.repository_id not in id_sets.repository_ids:
                errors.append(ValidationError(
                    "Source", source.id,
                    f"repository_refs[{idx}] repository_id '{repo_ref.repository_id}' refererar inte till ett giltigt arkiv."
                ))

        return errors

    def _validate_media_item(self, media_item: MediaItem, id_sets: _IdSets) -> list[ValidationError]:
        """Validate a media item: structural + person references."""
        errors: list[ValidationError] = []

        # Structural validation
        structural = validate_media_item(media_item)
        for msg in structural:
            errors.append(ValidationError("MediaItem", media_item.id, msg))

        # mentioned_person_ids references
        for person_id in media_item.mentioned_person_ids:
            if person_id not in id_sets.person_ids:
                errors.append(ValidationError(
                    "MediaItem", media_item.id,
                    f"mentioned_person_id '{person_id}' refererar inte till en giltig person."
                ))

        return errors

    def _validate_repository(self, repository: Repository) -> list[ValidationError]:
        """Validate a repository: structural only (no foreign keys)."""
        errors: list[ValidationError] = []

        structural = validate_repository(repository)
        for msg in structural:
            errors.append(ValidationError("Repository", repository.id, msg))

        return errors

    def _validate_dna_profile(self, profile: DnaProfile, id_sets: _IdSets) -> list[ValidationError]:
        """Validate a DNA profile: structural + person/company references."""
        errors: list[ValidationError] = []

        # Structural validation with cross-entity checks
        structural = validate_dna_profile(
            profile,
            valid_person_ids=id_sets.person_ids,
            valid_company_ids=id_sets.dna_company_ids,
        )
        for msg in structural:
            errors.append(ValidationError("DnaProfile", profile.id, msg))

        # admin_person_id reference
        if profile.admin_person_id is not None:
            if profile.admin_person_id not in id_sets.person_ids:
                errors.append(ValidationError(
                    "DnaProfile", profile.id,
                    f"admin_person_id '{profile.admin_person_id}' refererar inte till en giltig person."
                ))

        return errors

    def _validate_dna_match(self, match: DnaMatch, id_sets: _IdSets) -> list[ValidationError]:
        """Validate a DNA match: structural + profile references."""
        errors: list[ValidationError] = []

        # Structural validation
        structural = validate_dna_match(match)
        for msg in structural:
            errors.append(ValidationError("DnaMatch", match.id, msg))

        # profile1_id and profile2_id references
        if match.profile1_id not in id_sets.dna_profile_ids:
            errors.append(ValidationError(
                "DnaMatch", match.id,
                f"profile1_id '{match.profile1_id}' refererar inte till en giltig DNA-profil."
            ))
        if match.profile2_id not in id_sets.dna_profile_ids:
            errors.append(ValidationError(
                "DnaMatch", match.id,
                f"profile2_id '{match.profile2_id}' refererar inte till en giltig DNA-profil."
            ))

        return errors

    def _validate_dna_segment(self, segment: DnaSegment, id_sets: _IdSets) -> list[ValidationError]:
        """Validate a DNA segment: structural + match reference."""
        errors: list[ValidationError] = []

        # Structural validation
        structural = validate_dna_segment(segment)
        for msg in structural:
            errors.append(ValidationError("DnaSegment", segment.id, msg))

        # match_id reference
        if segment.match_id not in id_sets.dna_match_ids:
            errors.append(ValidationError(
                "DnaSegment", segment.id,
                f"match_id '{segment.match_id}' refererar inte till en giltig DNA-matchning."
            ))

        return errors

    def _validate_dna_cluster(self, cluster: DnaCluster, id_sets: _IdSets) -> list[ValidationError]:
        """Validate a DNA cluster: structural + person/company/match references."""
        errors: list[ValidationError] = []

        # Structural validation
        structural = validate_dna_cluster(cluster)
        for msg in structural:
            errors.append(ValidationError("DnaCluster", cluster.id, msg))

        # company_ids references
        for company_id in cluster.company_ids:
            if company_id not in id_sets.dna_company_ids:
                errors.append(ValidationError(
                    "DnaCluster", cluster.id,
                    f"company_id '{company_id}' refererar inte till ett giltigt DNA-företag."
                ))

        # person_ids references
        for person_id in cluster.person_ids:
            if person_id not in id_sets.person_ids:
                errors.append(ValidationError(
                    "DnaCluster", cluster.id,
                    f"person_id '{person_id}' refererar inte till en giltig person."
                ))

        # dna_match_ids references
        for match_id in cluster.dna_match_ids:
            if match_id not in id_sets.dna_match_ids:
                errors.append(ValidationError(
                    "DnaCluster", cluster.id,
                    f"dna_match_id '{match_id}' refererar inte till en giltig DNA-matchning."
                ))

        return errors

    def _validate_dna_triangulation(
        self, triangulation: DnaTriangulation, id_sets: _IdSets
    ) -> list[ValidationError]:
        """Validate a DNA triangulation: structural + company/profile/cluster references."""
        errors: list[ValidationError] = []

        # Structural validation
        structural = validate_dna_triangulation(triangulation)
        for msg in structural:
            errors.append(ValidationError("DnaTriangulation", triangulation.id, msg))

        # company_id reference
        if triangulation.company_id not in id_sets.dna_company_ids:
            errors.append(ValidationError(
                "DnaTriangulation", triangulation.id,
                f"company_id '{triangulation.company_id}' refererar inte till ett giltigt DNA-företag."
            ))

        # profile_ids references
        for profile_id in triangulation.profile_ids:
            if profile_id not in id_sets.dna_profile_ids:
                errors.append(ValidationError(
                    "DnaTriangulation", triangulation.id,
                    f"profile_id '{profile_id}' refererar inte till en giltig DNA-profil."
                ))

        # cluster_id reference (optional)
        if triangulation.cluster_id is not None:
            if triangulation.cluster_id not in id_sets.dna_cluster_ids:
                errors.append(ValidationError(
                    "DnaTriangulation", triangulation.id,
                    f"cluster_id '{triangulation.cluster_id}' refererar inte till ett giltigt DNA-kluster."
                ))

        return errors
