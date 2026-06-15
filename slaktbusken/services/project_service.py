"""Project lifecycle service: create, open, save, close.

ProjectService is the main coordination layer for managing a genealogy
project. It delegates persistence to FilePersistence, settings to
settings_io, and translation file setup to translation_io. Entity
additions are validated before being appended to the in-memory data.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

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
from slaktbusken.model.project import ProjectData, ProjectMetadata
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
from slaktbusken.persistence.file_io import FilePersistence
from slaktbusken.persistence.settings_io import (
    ProjectSettings,
    create_default_settings,
    write_settings,
)
from slaktbusken.persistence.translation_io import (
    TranslationData,
    write_all as write_translations,
)

logger = logging.getLogger(__name__)

# Media subfolders to create in a new project.
_MEDIA_SUBFOLDERS = [
    "source-image",
    "photos",
    "death-notice",
    "obituary",
    "funeral-program",
    "grave-photo",
    "map",
    "logo",
    "document",
]


class ValidationError(Exception):
    """Raised when an entity fails validation before being added to the project.

    Attributes:
        errors: List of validation error messages (Swedish where user-facing).
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


class ProjectNotOpenError(Exception):
    """Raised when an operation requires an open project but none is loaded."""


class ProjectService:
    """Manages project lifecycle: create, open, save, close.

    This service is a thin coordination layer that delegates file I/O to
    the persistence modules and validation to the model validators. It
    tracks dirty state so callers know when unsaved changes exist.
    """

    def __init__(self) -> None:
        self._project_data: Optional[ProjectData] = None
        self._project_path: Optional[Path] = None
        self._settings: Optional[ProjectSettings] = None
        self._dirty: bool = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def data(self) -> ProjectData:
        """Access the current project data.

        Returns:
            The loaded ProjectData instance.

        Raises:
            ProjectNotOpenError: If no project is currently open.
        """
        if self._project_data is None:
            raise ProjectNotOpenError("Inget projekt är öppet.")
        return self._project_data

    @property
    def project_path(self) -> Optional[Path]:
        """The path to the currently open .json.gz file, or None."""
        return self._project_path

    @property
    def settings(self) -> Optional[ProjectSettings]:
        """The current project settings, or None if no project is open."""
        return self._settings

    @property
    def is_dirty(self) -> bool:
        """Whether the project has unsaved modifications."""
        return self._dirty

    # ------------------------------------------------------------------
    # Lifecycle methods
    # ------------------------------------------------------------------

    def create_project(self, name: str, location: Path) -> ProjectData:
        """Create a new project folder structure and empty data file.

        Creates:
            - Project folder at ``location / name``
            - App_JSON .json.gz file with empty entity arrays
            - Settings file with defaults
            - Translation subfolder with empty JSON mapping files
            - Media subfolders for each media category

        Args:
            name: The project name (1–100 characters).
            location: The parent directory where the project folder is created.

        Returns:
            The newly created ProjectData instance.

        Raises:
            OSError: If the folder structure cannot be created.
        """
        project_folder = location / name
        project_folder.mkdir(parents=True, exist_ok=True)

        # Create the ProjectData with empty arrays and metadata.
        metadata = ProjectMetadata(
            title=name,
            created_by="Släktbuske",
            language="sv-SE",
        )
        project_data = ProjectData(
            format="släktbuske-file",
            version="0.1",
            project=metadata,
        )

        # Save the .json.gz data file.
        data_file = project_folder / f"{name}.json.gz"
        FilePersistence.save(project_data, data_file)

        # Write default settings.
        settings = create_default_settings()
        settings_file = project_folder / "settings.json"
        write_settings(settings, settings_file)

        # Create translation subfolder with empty mapping files.
        translation_dir = project_folder / "translation"
        translation_dir.mkdir(parents=True, exist_ok=True)
        empty_translations = TranslationData()
        write_translations(empty_translations, translation_dir)

        # Create media subfolders.
        media_dir = project_folder / "media"
        for subfolder in _MEDIA_SUBFOLDERS:
            (media_dir / subfolder).mkdir(parents=True, exist_ok=True)

        # Set internal state.
        self._project_data = project_data
        self._project_path = data_file
        self._settings = settings
        self._dirty = False

        logger.info("Projekt skapat: %s", project_folder)
        return project_data

    def open_project(self, path: Path) -> ProjectData:
        """Open an existing project from a .json.gz file.

        Loads the project data via FilePersistence and resets dirty state.

        Args:
            path: Path to the .json.gz project file.

        Returns:
            The loaded ProjectData instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            CorruptedFileError: If the file is corrupted.
            UnsupportedVersionError: If the file version is too new.
        """
        project_data = FilePersistence.load(path)

        self._project_data = project_data
        self._project_path = path
        self._dirty = False

        # Attempt to load settings from the same folder.
        settings_file = path.parent / "settings.json"
        from slaktbusken.persistence.settings_io import read_settings
        self._settings = read_settings(settings_file)

        logger.info("Projekt öppnat: %s", path)
        return project_data

    def save_project(self) -> None:
        """Validate and atomically save the current project.

        Raises:
            ProjectNotOpenError: If no project is open.
        """
        if self._project_data is None or self._project_path is None:
            raise ProjectNotOpenError("Inget projekt är öppet att spara.")

        FilePersistence.save(self._project_data, self._project_path)
        self._dirty = False
        logger.info("Projekt sparat: %s", self._project_path)

    def close_project(self) -> None:
        """Close the current project.

        Resets all internal state. Callers should check is_dirty before
        closing if they want to prompt for save.
        """
        self._project_data = None
        self._project_path = None
        self._settings = None
        self._dirty = False
        logger.info("Projekt stängt.")

    # ------------------------------------------------------------------
    # Entity management methods
    # ------------------------------------------------------------------

    def add_person(self, person: Person) -> Person:
        """Validate and add a person to the project.

        Args:
            person: The Person instance to add.

        Returns:
            The added Person instance.

        Raises:
            ProjectNotOpenError: If no project is open.
            ValidationError: If the person fails validation.
        """
        data = self.data
        errors = validate_person(person)
        if errors:
            raise ValidationError(errors)
        data.persons.append(person)
        self._dirty = True
        return person

    def add_family(self, family: Family) -> Family:
        """Validate and add a family to the project.

        Args:
            family: The Family instance to add.

        Returns:
            The added Family instance.

        Raises:
            ProjectNotOpenError: If no project is open.
            ValidationError: If the family fails validation.
        """
        data = self.data
        errors = validate_family(family)
        if errors:
            raise ValidationError(errors)
        data.families.append(family)
        self._dirty = True
        return family

    def add_event(self, event: Event) -> Event:
        """Validate and add an event to the project.

        Args:
            event: The Event instance to add.

        Returns:
            The added Event instance.

        Raises:
            ProjectNotOpenError: If no project is open.
            ValidationError: If the event fails validation.
        """
        data = self.data
        errors = validate_event(event)
        if errors:
            raise ValidationError(errors)
        data.events.append(event)
        self._dirty = True
        return event

    def add_place(self, place: Place) -> Place:
        """Validate and add a place to the project.

        Args:
            place: The Place instance to add.

        Returns:
            The added Place instance.

        Raises:
            ProjectNotOpenError: If no project is open.
            ValidationError: If the place fails validation.
        """
        data = self.data
        errors = validate_place(place)
        if errors:
            raise ValidationError(errors)
        data.places.append(place)
        self._dirty = True
        return place

    def add_source(self, source: Source) -> Source:
        """Validate and add a source to the project.

        Args:
            source: The Source instance to add.

        Returns:
            The added Source instance.

        Raises:
            ProjectNotOpenError: If no project is open.
            ValidationError: If the source fails validation.
        """
        data = self.data
        errors = validate_source(source)
        if errors:
            raise ValidationError(errors)
        data.sources.append(source)
        self._dirty = True
        return source

    def add_media(self, media_item: MediaItem) -> MediaItem:
        """Validate and add a media item to the project.

        Args:
            media_item: The MediaItem instance to add.

        Returns:
            The added MediaItem instance.

        Raises:
            ProjectNotOpenError: If no project is open.
            ValidationError: If the media item fails validation.
        """
        data = self.data
        errors = validate_media_item(media_item)
        if errors:
            raise ValidationError(errors)
        data.media.append(media_item)
        self._dirty = True
        return media_item

    def add_repository(self, repository: Repository) -> Repository:
        """Validate and add a repository to the project.

        Args:
            repository: The Repository instance to add.

        Returns:
            The added Repository instance.

        Raises:
            ProjectNotOpenError: If no project is open.
            ValidationError: If the repository fails validation.
        """
        data = self.data
        errors = validate_repository(repository)
        if errors:
            raise ValidationError(errors)
        data.repositories.append(repository)
        self._dirty = True
        return repository

    def add_dna_company(self, company: DnaCompany) -> DnaCompany:
        """Add a DNA company to the project.

        DNA companies have no dedicated validator beyond required fields
        being present (enforced by the dataclass). They are added directly.

        Args:
            company: The DnaCompany instance to add.

        Returns:
            The added DnaCompany instance.

        Raises:
            ProjectNotOpenError: If no project is open.
        """
        data = self.data
        data.dna_companies.append(company)
        self._dirty = True
        return company

    def add_dna_profile(self, profile: DnaProfile) -> DnaProfile:
        """Validate and add a DNA profile to the project.

        Args:
            profile: The DnaProfile instance to add.

        Returns:
            The added DnaProfile instance.

        Raises:
            ProjectNotOpenError: If no project is open.
            ValidationError: If the profile fails validation.
        """
        data = self.data
        errors = validate_dna_profile(profile)
        if errors:
            raise ValidationError(errors)
        data.dna_profiles.append(profile)
        self._dirty = True
        return profile

    def add_dna_match(self, match: DnaMatch) -> DnaMatch:
        """Validate and add a DNA match to the project.

        Args:
            match: The DnaMatch instance to add.

        Returns:
            The added DnaMatch instance.

        Raises:
            ProjectNotOpenError: If no project is open.
            ValidationError: If the match fails validation.
        """
        data = self.data
        errors = validate_dna_match(match)
        if errors:
            raise ValidationError(errors)
        data.dna_matches.append(match)
        self._dirty = True
        return match

    def add_dna_segment(self, segment: DnaSegment) -> DnaSegment:
        """Validate and add a DNA segment to the project.

        Args:
            segment: The DnaSegment instance to add.

        Returns:
            The added DnaSegment instance.

        Raises:
            ProjectNotOpenError: If no project is open.
            ValidationError: If the segment fails validation.
        """
        data = self.data
        errors = validate_dna_segment(segment)
        if errors:
            raise ValidationError(errors)
        data.dna_segments.append(segment)
        self._dirty = True
        return segment

    def add_dna_cluster(self, cluster: DnaCluster) -> DnaCluster:
        """Validate and add a DNA cluster to the project.

        Args:
            cluster: The DnaCluster instance to add.

        Returns:
            The added DnaCluster instance.

        Raises:
            ProjectNotOpenError: If no project is open.
            ValidationError: If the cluster fails validation.
        """
        data = self.data
        errors = validate_dna_cluster(cluster)
        if errors:
            raise ValidationError(errors)
        data.dna_clusters.append(cluster)
        self._dirty = True
        return cluster

    def add_dna_triangulation(self, triangulation: DnaTriangulation) -> DnaTriangulation:
        """Validate and add a DNA triangulation to the project.

        Args:
            triangulation: The DnaTriangulation instance to add.

        Returns:
            The added DnaTriangulation instance.

        Raises:
            ProjectNotOpenError: If no project is open.
            ValidationError: If the triangulation fails validation.
        """
        data = self.data
        errors = validate_dna_triangulation(triangulation)
        if errors:
            raise ValidationError(errors)
        data.dna_triangulations.append(triangulation)
        self._dirty = True
        return triangulation

    def add_research_note(self, note: ResearchNote) -> ResearchNote:
        """Add a research note to the project.

        Research notes have no dedicated validator beyond required fields
        being present (enforced by the dataclass). They are added directly.

        Args:
            note: The ResearchNote instance to add.

        Returns:
            The added ResearchNote instance.

        Raises:
            ProjectNotOpenError: If no project is open.
        """
        data = self.data
        data.research_notes.append(note)
        self._dirty = True
        return note
