"""Project lifecycle service: create, open, save, close.

ProjectService is the main coordination layer for managing a genealogy
project. It delegates persistence to FilePersistence, settings to
settings_io, and translation file setup to translation_io. Entity
additions are validated before being appended to the in-memory data.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Callable, Optional

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
from slaktbusken.model.research_case import (
    ResearchAction,
    ResearchCase,
    ResearchHypothesis,
    normalize_completed_date,
)
from slaktbusken.model.research_note import ResearchNote
from slaktbusken.model.source import Repository, Source
from slaktbusken.model.validators import (
    validate_dna_cluster,
    validate_dna_match,
    validate_research_action,
    validate_research_case,
    validate_research_hypothesis,
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
    UiState,
    create_default_settings,
    write_settings,
)
from slaktbusken.persistence.translation_io import (
    TranslationData,
    write_all as write_translations,
)
from slaktbusken.services.research_service import (
    ResearchCaseDiff,
    ResearchCaseWorkingCopy,
    ResearchIdGenerator,
    RewireResult,
    apply_working_copy,
    delete_case_cascade,
    diff_working_copy,
    open_working_copy,
    reconcile_id_high_water_marks,
    rewire_entity_merge,
)
from slaktbusken.services.foster_sync import (
    migrate_orphan_links,
    sync_parentage_links,
)
from slaktbusken.services.standard_providers import initialize_standard_providers

logger = logging.getLogger(__name__)

#: Stand-in id used while validating research data that has not been issued an id yet.
_PENDING_ID = "\x00pending"


def _with_placeholder_ids(hypothesis: ResearchHypothesis) -> ResearchHypothesis:
    """Return a copy of *hypothesis* in which blank ids are replaced by placeholders.

    Used only to validate before ids are issued; the original is not changed.
    """
    comments = [
        replace(c, id=c.id or f"{_PENDING_ID}{i}")
        for i, c in enumerate(hypothesis.comments)
    ]
    return replace(hypothesis, id=hypothesis.id or _PENDING_ID, comments=comments)


_MSG_RESEARCH_CASE_TITLE_REQUIRED = "Forskningsärendet måste ha en rubrik."
_MSG_RESEARCH_DUPLICATE_ID = "Id:t {id} används redan av annan forskningsdata."
_MSG_RESEARCH_EMPTY_ID = "Forskningsdata saknar id."
_MSG_RESEARCH_WRONG_CASE = "Hypotesen eller åtgärden {id} tillhör inte forskningsärendet."

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
        # Observers of research changes. They belong to the service, not to a
        # project, so they survive opening and closing projects.
        self._research_listeners: list[Callable[[], None]] = []

    # ------------------------------------------------------------------
    # Research change notification
    # ------------------------------------------------------------------

    def add_research_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a callback to run after research data changes.

        Rebuilding a ``ResearchIndex`` does not repaint a widget that is already
        on screen, so views that show research-derived content are told when
        research data changed and rebuild themselves.

        Args:
            listener: Called with no arguments after every research change.

        Returns:
            A function that removes the listener again; calling it twice is
            harmless.
        """
        self._research_listeners.append(listener)

        def remove() -> None:
            if listener in self._research_listeners:
                self._research_listeners.remove(listener)

        return remove

    def notify_research_changed(self) -> None:
        """Tell every registered listener that research data changed.

        Call this after any committed create, update or delete of a research
        case, hypothesis, comment or action, and after a merge or a deletion
        that rewires or leaves behind research references. A listener that
        raises is logged and does not stop the others or the caller.
        """
        for listener in list(self._research_listeners):
            try:
                listener()
            except Exception:  # noqa: BLE001 - one broken view must not block the rest
                logger.exception("Lyssnare på forskningsändring misslyckades.")

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
            - Settings file (carries forward current settings, or defaults)
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
            version="0.3",
            project=metadata,
        )

        # Initialize standard Leverantörer and Källtyper for new projects.
        initialize_standard_providers(project_data)

        # Save the .json.gz data file.
        data_file = project_folder / f"{name}.json.gz"
        FilePersistence.save(project_data, data_file)

        # Carry forward current settings to the new project (so user
        # preferences persist across project switches). Fall back to
        # defaults if no project is currently open.
        if self._settings is not None:
            import copy
            settings = copy.deepcopy(self._settings)
            # Reset UI state since window layout may differ per project
            settings.ui_state = UiState()
        else:
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

        # Establish the placement-event source-of-truth invariant on load:
        # back-fill a dateless placement start event for every pre-feature
        # orphan foster/adoptive Parent_Set (task 3.2), then reconcile the
        # derived links from the events. The migrate-then-sync order ensures no
        # orphan foster/adoptive link is dropped (Design Decision 1 /
        # Requirement 13.3). `migrate_orphan_links` runs the sync internally.
        created = migrate_orphan_links(project_data)
        # A freshly loaded project is clean. Only flag it dirty when the
        # migration actually created back-fill events — those are genuine new
        # entities the user will want to persist. A no-op migration (the common
        # case for post-feature projects) leaves the load's clean state intact.
        if created:
            self._dirty = True

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
        # Reconcile derived foster/adoptive links from placement events. Sync is
        # idempotent and cheap, so it runs unconditionally for every event
        # rather than gating on placement types — a non-placement event simply
        # leaves the links unchanged (Requirement 2.3).
        sync_parentage_links(data)
        self._dirty = True
        return event

    def update_event(self, event: Event) -> Event:
        """Validate and replace an existing event in place by id.

        Finds the event with the same id in ``project.events`` and replaces it
        with ``event``, preserving its position, then reconciles derived
        foster/adoptive links so editing a placement event's child or parents
        re-derives its links (Requirement 2.3).

        Args:
            event: The updated Event instance (matched by ``id``).

        Returns:
            The updated Event instance.

        Raises:
            ProjectNotOpenError: If no project is open.
            ValidationError: If the event fails validation.
            KeyError: If no event with the same id exists.
        """
        data = self.data
        errors = validate_event(event)
        if errors:
            raise ValidationError(errors)
        for index, existing in enumerate(data.events):
            if existing.id == event.id:
                data.events[index] = event
                break
        else:
            raise KeyError(f"Ingen händelse med id {event.id!r} att uppdatera.")
        sync_parentage_links(data)
        self._dirty = True
        return event

    def delete_event(self, event_id: str) -> None:
        """Remove an event by id and reconcile derived links.

        Removing a placement start event removes its derived foster/adoptive
        links; the subsequent sync handles that cleanup (Requirement 2.3).
        Deleting an unknown id is a no-op beyond the sync.

        Args:
            event_id: The id of the event to remove.

        Raises:
            ProjectNotOpenError: If no project is open.
        """
        data = self.data
        data.events = [event for event in data.events if event.id != event_id]
        sync_parentage_links(data)
        self._dirty = True

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

    # ------------------------------------------------------------------
    # Research cases, hypotheses and actions
    # ------------------------------------------------------------------

    def new_research_id(self, entity_type: str) -> str:
        """Issue a research id that is never reused, even after a delete and reopen.

        Args:
            entity_type: ``"research_case"``, ``"research_hypothesis"``,
                ``"research_action"`` or ``"hypothesis_comment"``.

        Returns:
            A new id. The id high-water mark advances immediately, so an id
            handed to an editor's working copy is not issued twice.

        Raises:
            ProjectNotOpenError: If no project is open.
            ValueError: If *entity_type* is not a research entity type.
        """
        return ResearchIdGenerator(self.data).generate(entity_type)

    def _research_children_errors(
        self,
        hypotheses: list[ResearchHypothesis],
        actions: list[ResearchAction],
        case_ids: set[str],
        owner_case_id: Optional[str],
        other_hypothesis_ids: set[str],
        other_comment_ids: set[str],
        other_action_ids: set[str],
    ) -> list[str]:
        """Return the hard errors for a set of hypotheses and actions.

        Entity and source existence is not checked: a reference that was kept
        on purpose after its target was deleted must not block an edit.
        """
        errors: list[str] = []
        seen_h: set[str] = set()
        seen_c: set[str] = set()
        seen_a: set[str] = set()

        for hypothesis in hypotheses:
            if not hypothesis.id:
                errors.append(_MSG_RESEARCH_EMPTY_ID)
            elif hypothesis.id in seen_h or hypothesis.id in other_hypothesis_ids:
                errors.append(_MSG_RESEARCH_DUPLICATE_ID.format(id=hypothesis.id))
            seen_h.add(hypothesis.id)
            if owner_case_id is not None and hypothesis.research_case_id != owner_case_id:
                errors.append(_MSG_RESEARCH_WRONG_CASE.format(id=hypothesis.id))
            errors.extend(validate_research_hypothesis(hypothesis, case_ids, None))
            for comment in hypothesis.comments:
                if not comment.id:
                    errors.append(_MSG_RESEARCH_EMPTY_ID)
                elif comment.id in seen_c or comment.id in other_comment_ids:
                    errors.append(_MSG_RESEARCH_DUPLICATE_ID.format(id=comment.id))
                seen_c.add(comment.id)

        for action in actions:
            if not action.id:
                errors.append(_MSG_RESEARCH_EMPTY_ID)
            elif action.id in seen_a or action.id in other_action_ids:
                errors.append(_MSG_RESEARCH_DUPLICATE_ID.format(id=action.id))
            seen_a.add(action.id)
            if owner_case_id is not None and action.research_case_id != owner_case_id:
                errors.append(_MSG_RESEARCH_WRONG_CASE.format(id=action.id))
            errors.extend(validate_research_action(action, case_ids, None))

        return errors

    def _commit_research_change(self) -> None:
        """Mark the project changed and tell research listeners."""
        reconcile_id_high_water_marks(self.data)
        self._dirty = True
        self.notify_research_changed()

    def add_research_case(self, case: ResearchCase) -> ResearchCase:
        """Validate and add a research case; assigns an id when it has none.

        Raises:
            ProjectNotOpenError: If no project is open.
            ValidationError: If the case is invalid or its id is taken. The
                project is unchanged.
        """
        data = self.data
        errors = validate_research_case(case, None)
        if not case.title.strip():
            errors.append(_MSG_RESEARCH_CASE_TITLE_REQUIRED)
        if case.id and any(c.id == case.id for c in data.research_cases):
            errors.append(_MSG_RESEARCH_DUPLICATE_ID.format(id=case.id))
        if errors:
            raise ValidationError(errors)
        if not case.id:
            case.id = self.new_research_id("research_case")
        data.research_cases.append(case)
        self._commit_research_change()
        return case

    def update_research_case(self, case: ResearchCase) -> ResearchCase:
        """Validate a case and replace the stored one with the same id.

        Raises:
            KeyError: If no case has that id.
            ValidationError: If the case is invalid. The project is unchanged.
        """
        data = self.data
        index = next(
            (i for i, c in enumerate(data.research_cases) if c.id == case.id), None
        )
        if index is None:
            raise KeyError(f"Inget forskningsärende med id {case.id!r} att uppdatera.")
        errors = validate_research_case(case, None)
        if not case.title.strip():
            errors.append(_MSG_RESEARCH_CASE_TITLE_REQUIRED)
        if errors:
            raise ValidationError(errors)
        data.research_cases[index] = case
        self._commit_research_change()
        return case

    def delete_research_case(self, case_id: str) -> bool:
        """Delete a case with its own hypotheses, comments and actions.

        Returns:
            True if a case was deleted, False if there was none (a no-op).
        """
        data = self.data
        if not any(c.id == case_id for c in data.research_cases):
            return False
        delete_case_cascade(data, case_id)
        self._commit_research_change()
        return True

    def add_research_hypothesis(self, hypothesis: ResearchHypothesis) -> ResearchHypothesis:
        """Validate and add a hypothesis to an existing case.

        Assigns ids to the hypothesis and to comments that have none.

        Raises:
            ValidationError: If it is invalid or its case does not exist.
        """
        data = self.data
        case_ids = {c.id for c in data.research_cases}
        other_comments = {
            c.id for h in data.research_hypotheses for c in h.comments
        }
        # A missing id is assigned only after validation passes, so a rejected
        # hypothesis does not advance the id high-water mark. Validate with a
        # placeholder id and blank comment ids in the meantime.
        missing_id = not hypothesis.id
        errors = self._research_children_errors(
            [hypothesis if not missing_id else _with_placeholder_ids(hypothesis)],
            [],
            case_ids,
            None,
            {h.id for h in data.research_hypotheses},
            other_comments,
            set(),
        )
        if errors:
            raise ValidationError(errors)
        if not hypothesis.id:
            hypothesis.id = self.new_research_id("research_hypothesis")
        for comment in hypothesis.comments:
            if not comment.id:
                comment.id = self.new_research_id("hypothesis_comment")
        data.research_hypotheses.append(hypothesis)
        self._commit_research_change()
        return hypothesis

    def update_research_hypothesis(
        self, hypothesis: ResearchHypothesis
    ) -> ResearchHypothesis:
        """Validate a hypothesis and replace the stored one with the same id.

        Raises:
            KeyError: If no hypothesis has that id.
            ValidationError: If it is invalid. The project is unchanged.
        """
        data = self.data
        index = next(
            (i for i, h in enumerate(data.research_hypotheses) if h.id == hypothesis.id),
            None,
        )
        if index is None:
            raise KeyError(f"Ingen hypotes med id {hypothesis.id!r} att uppdatera.")
        others = [h for i, h in enumerate(data.research_hypotheses) if i != index]
        errors = self._research_children_errors(
            [hypothesis],
            [],
            {c.id for c in data.research_cases},
            None,
            {h.id for h in others},
            {c.id for h in others for c in h.comments},
            set(),
        )
        if errors:
            raise ValidationError(errors)
        for comment in hypothesis.comments:
            if not comment.id:
                comment.id = self.new_research_id("hypothesis_comment")
        data.research_hypotheses[index] = hypothesis
        self._commit_research_change()
        return hypothesis

    def delete_research_hypothesis(self, hypothesis_id: str) -> bool:
        """Delete a hypothesis and its comments; False if there was none."""
        data = self.data
        remaining = [h for h in data.research_hypotheses if h.id != hypothesis_id]
        if len(remaining) == len(data.research_hypotheses):
            return False
        data.research_hypotheses = remaining
        self._commit_research_change()
        return True

    def add_research_action(self, action: ResearchAction) -> ResearchAction:
        """Validate and add an action to an existing case; assigns a missing id.

        A blank ``completed_date`` is normalized to ``None`` (pending).

        Raises:
            ValidationError: If it is invalid or its case does not exist.
        """
        data = self.data
        action.completed_date = normalize_completed_date(action.completed_date)
        checked = action if action.id else replace(action, id=_PENDING_ID)
        errors = self._research_children_errors(
            [],
            [checked],
            {c.id for c in data.research_cases},
            None,
            set(),
            set(),
            {a.id for a in data.research_actions},
        )
        if errors:
            raise ValidationError(errors)
        if not action.id:
            action.id = self.new_research_id("research_action")
        data.research_actions.append(action)
        self._commit_research_change()
        return action

    def update_research_action(self, action: ResearchAction) -> ResearchAction:
        """Validate an action and replace the stored one with the same id.

        Raises:
            KeyError: If no action has that id.
            ValidationError: If it is invalid. The project is unchanged.
        """
        data = self.data
        index = next(
            (i for i, a in enumerate(data.research_actions) if a.id == action.id), None
        )
        if index is None:
            raise KeyError(f"Ingen forskningsåtgärd med id {action.id!r} att uppdatera.")
        action.completed_date = normalize_completed_date(action.completed_date)
        errors = self._research_children_errors(
            [],
            [action],
            {c.id for c in data.research_cases},
            None,
            set(),
            set(),
            {a.id for i, a in enumerate(data.research_actions) if i != index},
        )
        if errors:
            raise ValidationError(errors)
        data.research_actions[index] = action
        self._commit_research_change()
        return action

    def delete_research_action(self, action_id: str) -> bool:
        """Delete an action; False if there was none."""
        data = self.data
        remaining = [a for a in data.research_actions if a.id != action_id]
        if len(remaining) == len(data.research_actions):
            return False
        data.research_actions = remaining
        self._commit_research_change()
        return True

    def commit_research_case_working_copy(
        self, working_copy: ResearchCaseWorkingCopy
    ) -> ResearchCaseDiff:
        """Validate a case editor's working copy and write it all at once.

        Blank action completion dates are normalized to ``None`` first. If
        anything is invalid nothing at all is written. If the copy equals what
        the project already holds, the project is not marked changed and no
        listener is told.

        Returns:
            What was created, updated and deleted.

        Raises:
            ValidationError: With every error found; the project is unchanged.
        """
        data = self.data
        case = working_copy.case
        for action in working_copy.actions:
            action.completed_date = normalize_completed_date(action.completed_date)

        errors = validate_research_case(case, None)
        if not case.title.strip():
            errors.append(_MSG_RESEARCH_CASE_TITLE_REQUIRED)
        if not case.id:
            errors.append(_MSG_RESEARCH_EMPTY_ID)
        elif case.id in {c.id for c in data.research_cases} - {case.id}:
            errors.append(_MSG_RESEARCH_DUPLICATE_ID.format(id=case.id))

        other_h = [h for h in data.research_hypotheses if h.research_case_id != case.id]
        errors.extend(
            self._research_children_errors(
                working_copy.hypotheses,
                working_copy.actions,
                {c.id for c in data.research_cases} | {case.id},
                case.id,
                {h.id for h in other_h},
                {c.id for h in other_h for c in h.comments},
                {a.id for a in data.research_actions if a.research_case_id != case.id},
            )
        )
        if errors:
            raise ValidationError(errors)

        diff = diff_working_copy(data, working_copy)
        if diff.is_empty:
            return diff
        apply_working_copy(data, working_copy)
        self._commit_research_change()
        return diff

    def link_research_case_entity(
        self, case_id: str, entity_type: str, entity_id: str, role: str = ""
    ) -> bool:
        """Link an entity to an existing case ("koppla befintligt").

        Does nothing, and notifies no one, if the entity is already linked.

        Returns:
            True if a link was added.

        Raises:
            KeyError: If there is no case with that id.
        """
        from slaktbusken.services.research_editing import add_link

        working_copy = open_working_copy(self.data, case_id)
        if not add_link(working_copy.case, entity_type, entity_id, role):
            return False
        self.commit_research_case_working_copy(working_copy)
        return True

    def unlink_research_case_entity(
        self, case_id: str, entity_type: str, entity_id: str
    ) -> bool:
        """Remove the association between a case and an entity ("ta bort kopplingen").

        Only the links to that entity are removed. The case, its hypotheses and
        actions are kept, and no other entity is promoted to primary.

        Returns:
            True if anything was removed.

        Raises:
            KeyError: If there is no case with that id.
        """
        from slaktbusken.services.research_editing import is_linked, remove_link

        working_copy = open_working_copy(self.data, case_id)
        if not is_linked(working_copy.case, entity_type, entity_id):
            return False
        remove_link(working_copy.case, entity_type, entity_id)
        self.commit_research_case_working_copy(working_copy)
        return True

    def merge_research_references(
        self, entity_type: str, old_id: str, survivor_id: str
    ) -> RewireResult:
        """Repoint research references from a merged-away entity to the survivor.

        Call this from any merge of persons, places, sources, events, media or
        DNA matches. Marks the project changed and notifies only if a
        reference actually moved.
        """
        result = rewire_entity_merge(self.data, entity_type, old_id, survivor_id)
        if result.links_rewired or result.links_collapsed or result.source_refs_rewired:
            self._commit_research_change()
        return result
