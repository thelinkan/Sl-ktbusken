# Implementation Plan

## Overview

This plan implements the Släktbusken genealogy desktop application in Python with PySide6. Tasks are ordered to build foundational layers first (model, persistence, services) before UI components, ensuring each layer's dependencies are satisfied before dependent tasks begin.

## Tasks

- [x] 1. Project Scaffolding and Build Configuration
  - [x] 1.1 Create the Python package structure with `slaktbusken/__init__.py`, `slaktbusken/__main__.py`, and all sub-package `__init__.py` files for model/, persistence/, services/, gedcom/, gedcom/translation/, relationship/, ui/, ui/generated/, ui/forms/, ui/resources/, ui/views/, ui/widgets/, ui/editors/, ui/dialogs/, and scripts/
  - [x] 1.2 Create `pyproject.toml` with project metadata, Python >=3.11 requirement, PySide6>=6.6.0 dependency, and dev dependencies (pytest>=7.4.0, pytest-qt>=4.2.0, hypothesis>=6.90.0, pytest-cov>=4.1.0)
  - [x] 1.3 Create the test directory structure mirroring source modules: tests/, tests/conftest.py, tests/test_model/, tests/test_persistence/, tests/test_services/, tests/test_gedcom/, tests/test_relationship/, tests/test_ui/ with corresponding `__init__.py` files
  - [x] 1.4 Create `slaktbusken/scripts/compile_ui.py` build script that compiles .ui files via pyside6-uic and .qrc files via pyside6-rcc
  - **Requirements:** 26.1, 26.2, 26.3, 26.4

- [x] 2. Core Data Model - Base Entities
  - [x] 2.1 Implement `slaktbusken/model/id_generator.py` with the IDGenerator class supporting type-prefixed IDs, monotonically increasing numeric suffixes, tracking of used IDs, and non-reuse of deleted entity IDs
  - [x] 2.2 Implement `slaktbusken/model/person.py` with Person and Name dataclasses (id, sex, names list, profile_media_id, notes; Name with type, given, surname)
  - [x] 2.3 Implement `slaktbusken/model/family.py` with Family, FamilyPartner, ParentChildLink dataclasses (id, partners list with person_id and role, children list preserving order, parent_child_links list with child_id/parent_id/parentage_type, event_ids)
  - [x] 2.4 Implement `slaktbusken/model/event.py` with Event, DateValue, PlaceRef, Participant, SourceRef dataclasses including support for custom event types and cause_of_death field
  - [x] 2.5 Implement `slaktbusken/model/place.py` with Place dataclass (id, type, name, parent_place_id, latitude, longitude, notes)
  - [x] 2.6 Implement `slaktbusken/model/source.py` with Source, StructuredReference, RepositoryRef, Repository dataclasses including source_type-specific structured references
  - [x] 2.7 Implement `slaktbusken/model/media.py` with MediaItem and LinkedEntity dataclasses including type-specific optional fields (publication, transcription, mentioned_person_ids)
  - [x] 2.8 Implement `slaktbusken/model/dna.py` with DnaCompany, DnaProfile, DnaMatch, DnaSegment, DnaCluster, DnaTriangulation dataclasses
  - [x] 2.9 Implement `slaktbusken/model/research_note.py` with ResearchNote dataclass
  - [x] 2.10 Implement `slaktbusken/model/project.py` with ProjectMetadata and ProjectData (root container) dataclasses containing all top-level entity lists
  - **Requirements:** 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.12, 23.1, 23.2, 24.1, 24.2, 24.3

- [x] 3. Data Model Validators
  - [x] 3.1 Implement `slaktbusken/model/validators.py` with validation functions for Person (requires at least one name, sex in {M,F,X,U}, given/surname max 100 chars, optional title and occupation max 100 chars each, optional event_id on Name must reference an existing event if provided)
  - [x] 3.2 Add validation for Family (partner roles valid, children reference existing persons, no duplicate children, person_id references exist, parent_child_links reference valid children and partners, parentage_type in {biological, legal, adoptive, foster, step, unknown_donor}, parent_id may be None only when parentage_type is unknown_donor)
  - [x] 3.3 Add validation for Event (requires type, at least one participant, valid date format ISO 8601, valid precision, custom events require type_name)
  - [x] 3.4 Add validation for Place (valid type, name 1-200 chars, valid parent hierarchy rules, latitude -90 to 90, longitude -180 to 180)
  - [x] 3.5 Add validation for Source (valid source_type, structured_reference fields match type), Repository (valid type), and MediaItem (valid type, relative forward-slash path)
  - [x] 3.6 Add validation for DNA entities: DnaProfile (valid test_type, references exist), DnaMatch (shared_cm 0-7400, shared_percentage 0-100, segment_count 0-10000, largest_segment_cm 0-300), DnaSegment (valid chromosome, start < end, cm > 0, snp_count >= 0), DnaCluster (name 1-200), DnaTriangulation (>=2 segments, >=3 profiles)
  - **Requirements:** 7.5, 7.6, 8.5, 8.6, 9.3, 9.4, 9.7, 10.1, 10.3, 13.4, 13.6, 14.1, 14.4, 14.6, 25.2

- [x] 4. Persistence Layer - Serialization
  - [x] 4.1 Implement `slaktbusken/persistence/serialization.py` with functions to serialize ProjectData to JSON string (UTF-8) with format_version as the first key, and deserialize JSON string back to ProjectData, handling all nested entity types
  - [x] 4.2 Implement `slaktbusken/persistence/file_io.py` with FilePersistence class: atomic save (write to temp file, os.replace), gzip read/write of .json.gz files, version check before full deserialization, CorruptedFileError and UnsupportedVersionError with specific problem descriptions
  - [x] 4.3 Implement `slaktbusken/persistence/migration.py` with MigrationManager class: version comparison logic (needs_migration, is_too_new), migration registry (decorator-based registration of version→version migration functions), sequential migration application (chained upgrades from old version to current), and backup creation before migration (appending old version to filename)
  - [x] 4.4 Implement `slaktbusken/persistence/translation_io.py` with read/write for translation JSON files (sources.json, places.json, persons.json) following the defined mapping format
  - [x] 4.5 Implement `slaktbusken/persistence/settings_io.py` with read/write for project settings JSON file (person_box_config, diagram_settings, ui_state)
  - **Requirements:** 2.1, 3.1, 3.2, 3.3, 3.4, 25.2, 25.3, 27.1, 27.2, 27.3, 27.4, 27.5, 27.6, 27.7

- [x] 5. Property Tests - Serialization and ID Generation
  - [x] 5.1 Write Hypothesis strategies in `tests/conftest.py` for generating valid instances of all dataclasses (Person, Family, Event, Place, Source, MediaItem, Repository, DNA entities, ResearchNote, ProjectData)
  - [x] 5.2 Write property test for serialization round-trip (Property 1): for any valid ProjectData, serialize then deserialize produces equal data (`tests/test_persistence/test_serialization.py`)
  - [x] 5.3 Write property test for gzip persistence round-trip (Property 2): write to .json.gz then read back produces equal data with identical intermediate JSON bytes (`tests/test_persistence/test_file_io.py`)
  - [x] 5.4 Write property test for ID generation uniqueness and non-reuse (Property 3): all generated IDs are unique, carry correct prefix, deleted IDs never reused (`tests/test_model/test_id_generator.py`)
  - [x] 5.5 Write property test for media file paths (Property 14): all MediaItem file paths use forward slashes and are relative (`tests/test_persistence/test_serialization.py`)
  - [x] 5.6 Write property test for migration correctness (Property 15): for any valid ProjectData at version N, migrating to version N+1 then deserializing produces valid ProjectData with no data loss; backup file is created with correct version suffix (`tests/test_persistence/test_migration.py`)
  - [x] 5.7 Write unit tests for version handling edge cases: file with current version loads without migration, file with older version triggers migration chain, file with newer version raises UnsupportedVersionError with Swedish message (`tests/test_persistence/test_migration.py`)
  - **Requirements:** 22.2, 24.1, 24.2, 24.3, 25.2, 27.1, 27.2, 27.3, 27.4, 27.5, 27.6, 27.7

- [x] 6. Property Tests - Validation
  - [x] 6.1 Write property test for entity validation rejects invalid data (Property 6): invalid entities are rejected with specific errors (`tests/test_model/test_validators.py`)
  - [x] 6.2 Write property test for entity validation accepts valid data (Property 7): valid entities pass validation without errors (`tests/test_model/test_validators.py`)
  - **Requirements:** 7.5, 7.6, 8.5, 8.6, 9.4, 13.4, 14.1

- [x] 7. Project Service
  - [x] 7.1 Implement `slaktbusken/services/project_service.py` with ProjectService class: create_project (folder structure, empty data file, settings, translation subfolder, media subfolders), open_project, save_project (validate then atomic save), close_project
  - [x] 7.2 Add entity management methods to ProjectService: add_person, add_family, add_event, add_place, add_source, add_media, add_repository, add_dna_company, add_dna_profile, add_dna_match, add_dna_segment, add_dna_cluster, add_dna_triangulation, add_research_note - each validates before adding
  - [x] 7.3 Add dirty tracking to ProjectService: mark dirty on any data modification, check dirty state on close, prompt save
  - [x] 7.4 Write unit tests for project creation (folder structure, empty data, settings, translations) and open/save/close lifecycle (`tests/test_services/test_project_service.py`)
  - **Requirements:** 1.1, 1.2, 1.3, 1.4, 3.1, 3.2

- [x] 8. Validation Service
  - [x] 8.1 Implement `slaktbusken/services/validation_service.py` with ValidationService class: validate_entity (single entity in context of project), validate_project (all entities pre-save)
  - [x] 8.2 Implement cross-entity referential integrity checks: person_id references in families, event participants, DNA profiles; place_id references in events; source_id references in source_refs; media_id references
  - [x] 8.3 Write unit tests for validation service including reference integrity failures (`tests/test_services/test_validation_service.py`)
  - **Requirements:** 8.5, 13.6, 14.6

- [ ] 9. GEDCOM Parser
  - [ ] 9.1 Implement `slaktbusken/gedcom/parser.py` with line-level GEDCOM parser that handles levels, tags, values, cross-references, and continuation lines (CONC/CONT)
  - [ ] 9.2 Add error handling: detect non-GEDCOM files, report malformed lines with line numbers, support best-effort parsing (continue on individual record failures)
  - [ ] 9.3 Write unit tests for GEDCOM parser with sample valid and invalid input (`tests/test_gedcom/test_parser.py`)
  - **Requirements:** 4.7, 4.8

- [ ] 10. GEDCOM Translation Modules
  - [ ] 10.1 Implement `slaktbusken/gedcom/translation/models.py` with shared dataclasses for translation entries (SourceMapping, PlaceMapping, PersonMapping)
  - [ ] 10.2 Implement person fingerprinting and hashing in `slaktbusken/gedcom/translation/person_mapping.py`: compute fingerprints from composite key (names, birth date, birth place) for identity matching, record hashes (hash of all person fields to detect content changes vs unchanged records), and relationship hashes (hash of family structure — partners and children — to detect structural changes)
  - [ ] 10.3 Implement person diff classification in `slaktbusken/gedcom/translation/person_mapping.py`: compare incoming GEDCOM persons against existing App_JSON (via translation file and fingerprints) to classify each as new (no match found), updated (matched but record hash differs), unchanged (matched and hash identical), missing (in App_JSON but absent from GEDCOM), or uncertain (fingerprint similarity above threshold but below exact match, requiring user verification)
  - [ ] 10.4 Implement import-diff report generation in `slaktbusken/gedcom/translation/person_mapping.py`: produce a structured ImportDiffReport summarizing counts and details for each category (new/updated/unchanged/missing/uncertain persons), suitable for presentation to the user before committing the import
  - [ ] 10.5 Write unit tests for person fingerprinting, diff classification, and import-diff report (`tests/test_gedcom/test_person_mapping.py`): test exact matches, near-matches flagged as uncertain, new person detection, missing person detection, and report accuracy
  - [ ] 10.6 Implement `slaktbusken/gedcom/translation/place_translation.py` with GEDCOM place string to hierarchical Place mapping logic
  - [ ] 10.7 Implement `slaktbusken/gedcom/translation/source_translation.py` with GEDCOM source ID to structured Source mapping logic
  - [ ] 10.8 Implement `slaktbusken/gedcom/translation/citation_translation.py` for building citation text from structured references
  - [ ] 10.9 Implement `slaktbusken/gedcom/translation/matcher.py` with fuzzy/exact matching logic for finding existing entities during re-import
  - [ ] 10.10 Implement `slaktbusken/gedcom/translation/__init__.py` exposing TranslationManager facade that coordinates all translation modules
  - **Requirements:** 4.1, 4.2, 4.4, 4.5, 4.6

- [ ] 11. GEDCOM Importer
  - [ ] 11.1 Implement `slaktbusken/gedcom/importer.py` with GEDCOMImporter class: import_file method parsing GEDCOM, mapping records to App_JSON entities via translation modules, returning ImportResult
  - [ ] 11.2 Add re-import support: use existing translation files to match GEDCOM IDs to previously assigned App_JSON IDs, update existing records, add only new entities
  - [ ] 11.3 Add warning accumulation for skipped records (unsupported tags, malformed data) with GEDCOM line number and tag in Swedish
  - [ ] 11.4 Implement ArkivDigital repository detection: when a source citation begins with "ArkivDigital:" or matches the ArkivDigital structured pattern, create or reuse an "ArkivDigital" Repository record (type: digital_archive) and attach it to the Source via repository_ref
  - [ ] 11.5 Write unit tests for GEDCOM import with sample GEDCOM files verifying correct entity creation and field mappings, including ArkivDigital repository detection (`tests/test_gedcom/test_importer.py`)
  - **Requirements:** 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 11.7, 22.3

- [ ] 12. GEDCOM Exporter
  - [ ] 12.1 Implement `slaktbusken/gedcom/exporter.py` with GEDCOMExporter class: export method producing GEDCOM 5.5.1-compliant UTF-8 output with HEAD, INDI, FAM, SOUR, TRLR records
  - [ ] 12.2 Implement deterministic GEDCOM ID generation from App_JSON IDs (stable mapping, same input produces same output)
  - [ ] 12.3 Implement place hierarchy resolution: walk up parent_place_id chain, produce comma-separated string from most specific to least specific
  - [ ] 12.4 Implement source citation resolution: write inline GEDCOM source citations from reference_text or concatenated structured_reference fields
  - [ ] 12.5 Implement omission tracking: identify App_JSON elements with no GEDCOM equivalent, collect counts by type
  - [ ] 12.6 Write unit tests and property tests for GEDCOM export: deterministic IDs (Property 4), place hierarchy resolution (Property 5), valid GEDCOM output (`tests/test_gedcom/test_exporter.py`)
  - **Requirements:** 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 22.4, 24.4

- [ ] 13. Import and Export Services
  - [ ] 13.1 Implement `slaktbusken/services/import_service.py` with ImportService class orchestrating the full import pipeline: parse, load translations, translate, validate, merge, persist translations, report
  - [ ] 13.2 Implement `slaktbusken/services/export_service.py` with ExportService class orchestrating the full export pipeline: resolve IDs, build GEDCOM, collect omissions, report
  - [ ] 13.3 Implement `slaktbusken/services/report_service.py` with ReportService class: format_import_result, format_export_result, format_validation_errors (all in Swedish)
  - [ ] 13.4 Write integration tests for import and export services (`tests/test_services/test_import_service.py`, `tests/test_services/test_export_service.py`)
  - **Requirements:** 4.1, 4.2, 4.3, 5.1, 5.6, 5.7

- [ ] 14. Translation Service
  - [ ] 14.1 Implement `slaktbusken/services/translation_service.py` with TranslationService class: load_translations, save_translations, update_mappings (coordinates with gedcom/translation/ package for mapping logic)
  - [ ] 14.2 Write unit tests for translation service lifecycle (`tests/test_services/test_translation_service.py`)
  - **Requirements:** 6.1, 6.2, 6.3, 6.4, 6.5, 6.6

- [ ] 15. Relationship Calculator
  - [ ] 15.1 Implement `slaktbusken/relationship/graph_builder.py` with adjacency graph construction from ProjectData (parent-to-child, child-to-parent, partner edges)
  - [ ] 15.2 Implement `slaktbusken/relationship/calculator.py` with RelationshipCalculator class: bidirectional BFS, find common ancestors, construct paths, classify relationships, limit by max_generations (30) and max_paths (50)
  - [ ] 15.3 Implement `slaktbusken/relationship/kinship_terms.py` with Swedish kinship term mapping (far, mor, bror, syster, farbror, morbror, faster, moster, kusin, syssling, etc.)
  - [ ] 15.4 Write property test for relationship path finding correctness (Property 8): connected persons have valid paths with correct edges (`tests/test_relationship/test_calculator.py`)
  - [ ] 15.5 Write property test for Swedish kinship term assignment (Property 9): correct terms for known generation counts (`tests/test_relationship/test_kinship_terms.py`)
  - [ ] 15.6 Write unit tests for specific relationship scenarios: parent-child, sibling, uncle/aunt, cousin, in-law, no connection found (`tests/test_relationship/test_calculator.py`)
  - **Requirements:** 15.1, 15.2, 15.3, 15.4, 15.5, 15.7, 22.5

- [ ] 16. UI Build Tooling and Resources
  - [ ] 16.1 Create placeholder `.ui` files for Qt Designer forms: main_window.ui, person_editor.ui, event_editor.ui, source_editor.ui, place_editor.ui, media_editor.ui, dna_editor.ui, repository_editor.ui, translation_editor.ui, new_project_dialog.ui, relationship_dialog.ui, settings_dialog.ui, person_list_panel.ui
  - [ ] 16.2 Create `slaktbusken/ui/resources/resources.qrc` resource file with icon and style references
  - [ ] 16.3 Run compile_ui.py to generate initial Python UI files in slaktbusken/ui/generated/
  - **Requirements:** 26.1

- [ ] 17. Main Window and Application Shell
  - [ ] 17.1 Implement `slaktbusken/app.py` as thin wiring shell: instantiate all services, connect them to UI, handle application-level signals
  - [ ] 17.2 Implement `slaktbusken/ui/main_window.py` with QMainWindow setup: menu bar (Arkiv, Redigera, Visa, Verktyg, Hjälp), toolbar, left/right panel arrangement, status bar
  - [ ] 17.3 Wire main window menu actions: New Project, Open Project, Save, Import GEDCOM, Export GEDCOM, Close, Exit, View switching (Family/Ancestry/Descendants), Relationship Calculator, Settings
  - [ ] 17.4 Implement `slaktbusken/__main__.py` entry point creating QApplication, instantiating app.py, showing main window
  - **Requirements:** 21.1, 21.2, 26.4

- [ ] 18. Person List Panel
  - [ ] 18.1 Implement `slaktbusken/ui/person_list_panel.py` with PersonListPanel: display all persons sorted by surname then given name, showing first name entry with birth/death years
  - [ ] 18.2 Implement filtering: text field (case-insensitive substring on names), birth year, death year, parish filters with AND logic, update within 200ms
  - [ ] 18.3 Implement selection: single-click sets active person in diagram panel, double-click opens edit window
  - [ ] 18.4 Write property test for person list filtering (Property 10): filtered results match exactly those persons satisfying all criteria (`tests/test_ui/test_person_list_filter.py`)
  - [ ] 18.5 Write property test for place hierarchy event filtering (Property 11): parish filter includes sub-place events (`tests/test_ui/test_person_list_filter.py`)
  - **Requirements:** 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 10.2

- [ ] 19. Diagram Panel Infrastructure
  - [ ] 19.1 Implement `slaktbusken/ui/diagram_panel.py` with DiagramPanel: QGraphicsScene, ZoomableGraphicsView (mouse wheel zoom 25%-400%), view switching (Family/Ancestry/Descendants)
  - [ ] 19.2 Implement `slaktbusken/ui/widgets/person_box.py` with PersonBoxItem QGraphicsItem: configurable content fields (name, dates, places, photo, DNA info), paint method
  - [ ] 19.3 Implement `slaktbusken/ui/widgets/placeholder_box.py` with PlaceholderBox for missing relatives (click to add)
  - [ ] 19.4 Implement `slaktbusken/ui/widgets/connection_line.py` with ConnectionLine QGraphicsItem for parent-child and partner connections
  - **Requirements:** 17.2, 17.3, 17.4, 17.5, 20.1, 20.4

- [ ] 20. Family View
  - [ ] 20.1 Implement `slaktbusken/ui/views/family_view.py` with Family View diagram logic: display active person with parents, siblings, partners, and children from each Family
  - [ ] 20.2 Add placeholder boxes for missing mother, father, and new child positions
  - [ ] 20.3 Add interaction: click to select (visual indicator), A key to set as active, double-click to open editor, click placeholder to create/link person
  - [ ] 20.4 Add print support for Family View diagram
  - **Requirements:** 17.1, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.9, 17.10

- [ ] 21. Ancestry View
  - [ ] 21.1 Implement `slaktbusken/ui/views/ancestry_view.py` with Ancestry View diagram logic: display ancestors up to configured depth (1-10, default 4)
  - [ ] 21.2 Add placeholders for missing ancestors at intermediate levels, continue rendering known ancestors at deeper levels
  - [ ] 21.3 Add interaction: click to select, A key to set as active, double-click to open editor
  - [ ] 21.4 Write property test for ancestry collection completeness (Property 12): correct ancestor set for given depth (`tests/test_ui/test_ancestry_view_data.py`)
  - [ ] 21.5 Add print support for Ancestry View diagram
  - **Requirements:** 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 18.7, 18.8

- [ ] 22. Descendants View
  - [ ] 22.1 Implement `slaktbusken/ui/views/descendants_view.py` with Descendants View diagram logic: display descendants up to configured depth (1-10, default 4)
  - [ ] 22.2 Handle case of no descendants with appropriate Swedish message
  - [ ] 22.3 Add interaction: click to select, A key to set as active, double-click to open editor
  - [ ] 22.4 Write property test for descendants collection completeness (Property 13): correct descendant set for given depth (`tests/test_ui/test_descendants_view_data.py`)
  - [ ] 22.5 Add print support for Descendants View diagram
  - **Requirements:** 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.7, 19.8

- [ ] 23. Source Translation Editor
  - [ ] 23.1 Design `slaktbusken/ui/forms/source_translation_editor.ui` with searchable list of GEDCOM source identifiers showing mapped App_JSON source titles, edit/add mapping controls, and validation indicators
  - [ ] 23.2 Implement `slaktbusken/ui/editors/source_translation_editor.py` using generated UI: load source translation file, display searchable list, edit existing mappings, add new mappings (specify GEDCOM ID, select target App_JSON source record), validate target exists before save
  - [ ] 23.3 Handle save errors with Swedish-language messages, retain unsaved changes in editor
  - **Requirements:** 6.1, 6.2, 6.5, 6.6

- [ ] 24. Place Translation Editor
  - [ ] 24.1 Design `slaktbusken/ui/forms/place_translation_editor.ui` with searchable list of GEDCOM place strings showing mapped App_JSON place names with hierarchy, edit/add mapping controls, and hierarchy visualization
  - [ ] 24.2 Implement `slaktbusken/ui/editors/place_translation_editor.py` using generated UI: load place translation file, display searchable list with hierarchy context, edit existing mappings, add new mappings (specify GEDCOM place string, select target App_JSON place with hierarchy display), validate target exists before save
  - [ ] 24.3 Handle save errors with Swedish-language messages, retain unsaved changes in editor
  - **Requirements:** 6.3, 6.4, 6.5, 6.6

- [ ] 25. Person Editor
  - [ ] 25.1 Design `slaktbusken/ui/forms/person_editor.ui` with tabs: Names (given, surname, type selector), Events, Photos, DNA and Clusters
  - [ ] 25.2 Implement `slaktbusken/ui/editors/person_editor.py` using generated UI: load/save person data, manage name entries, link events, select profile photo, display DNA info
  - [ ] 25.3 Implement validation feedback: prevent save without at least one name entry, display error for missing names
  - **Requirements:** 7.1, 7.2, 7.3, 7.4, 7.5, 7.6

- [ ] 26. Event Editor
  - [ ] 26.1 Design `slaktbusken/ui/forms/event_editor.ui` with fields for type selector (individual/family types), participants, date (value + precision), place, sources, media, and type-specific fields (cause of death, custom type name)
  - [ ] 26.2 Implement `slaktbusken/ui/editors/event_editor.py` using generated UI: create/edit events, add participants, attach source references with quality levels, link media
  - [ ] 26.3 Implement source reference management within events: add/remove source_refs with source_id, quality (primary/secondary/tertiary), and optional note
  - **Requirements:** 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 2.9, 2.10, 2.11

- [ ] 27. Place, Source, and Repository Editors
  - [ ] 27.1 Design and implement place editor (place_editor.ui + place_editor.py): type selector, name, parent place selection, coordinates, notes; place list view with filtering
  - [ ] 27.2 Design and implement source editor (source_editor.ui + source_editor.py): provider, source_type selector, title, reference_text, dynamic structured_reference fields based on type, media linking, repository_refs
  - [ ] 27.3 Design and implement repository editor (repository_editor.ui + repository_editor.py): name, type, address, phone list, email list, web list, notes, external_ids
  - [ ] 27.4 Implement deletion warnings for places (referenced by events) and sources (referenced by source_refs) and repositories (referenced by sources)
  - **Requirements:** 10.3, 10.4, 10.5, 11.1, 11.2, 11.3, 11.4, 11.5, 23.1, 23.3, 23.4

- [ ] 28. Media Editor
  - [ ] 28.1 Design and implement media editor (media_editor.ui + media_editor.py): file selection, type selector, title, linked entities management, type-specific fields (publication info, transcription, mentioned persons)
  - [ ] 28.2 Implement media list view for browsing all media across types
  - [ ] 28.3 Implement missing-file indicator for media items where the file path cannot be resolved
  - [ ] 28.4 Require at least one linked entity before saving a new MediaItem
  - **Requirements:** 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8

- [ ] 29. DNA Editor
  - [ ] 29.1 Design and implement DNA editor (dna_editor.ui + dna_editor.py): company management (name, notes, logo), profile management (person, company, test_type, kit details, admin info)
  - [ ] 29.2 Implement DNA match management: match entry (two profiles, shared_cM, percentage, segment_count, largest_segment, match_source)
  - [ ] 29.3 Implement DNA segment management: segment entry per match (chromosome, positions, cM, SNP count)
  - [ ] 29.4 Implement DNA cluster editor: name, notes, member profiles, associated matches, display color
  - [ ] 29.5 Implement DNA triangulation management: company, chromosome, overlap range, segment IDs, profile IDs, optional cluster link
  - **Requirements:** 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6

- [ ] 30. Relationship Dialog
  - [ ] 30.1 Design and implement relationship dialog (relationship_dialog.ui + relationship_dialog.py): person selection (two persons), options (blood only vs all, closest only vs all paths), result display
  - [ ] 30.2 Integrate RelationshipCalculator: display Swedish text description and graphical path diagram with person nodes and connecting edges
  - [ ] 30.3 Handle no-relationship-found case with Swedish message
  - [ ] 30.4 Add print support for relationship graph
  - **Requirements:** 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7

- [ ] 31. Settings and Configurable Person Box
  - [ ] 31.1 Design and implement settings dialog (settings_dialog.ui + settings_dialog.py): person box configuration (enable/disable each of 11 content fields), diagram depth settings
  - [ ] 31.2 Implement person box configuration persistence in project settings file; restore on project open
  - [ ] 31.3 Implement default configuration for new projects (name, birth date, death date enabled)
  - [ ] 31.4 Trigger diagram re-render within 2 seconds when person box configuration changes
  - **Requirements:** 20.1, 20.2, 20.3, 20.4, 20.5

- [ ] 32. New Project Dialog
  - [ ] 32.1 Design and implement new project dialog (new_project_dialog.ui + new_project_dialog.py): project name input (1-100 chars), location picker, validation, create button
  - [ ] 32.2 Wire to ProjectService.create_project, handle file system errors with Swedish error messages
  - **Requirements:** 1.1, 1.2, 1.3, 1.4

- [ ] 33. Swedish Language and Formatting
  - [ ] 33.1 Ensure all UI labels, menus, buttons, dialogs, tooltips, and system messages are in Swedish throughout the application
  - [ ] 33.2 Implement Swedish genealogical terminology for source types, place types, event types, and relationship labels
  - [ ] 33.3 Implement Swedish date formatting (YYYY-MM-DD) and number formatting (comma decimal separator, space thousands separator)
  - [ ] 33.4 Review and ensure all error messages, confirmation prompts, and validation feedback are in Swedish
  - **Requirements:** 21.1, 21.2, 21.3, 21.4

- [ ] 34. Error Handling Tests
  - [ ] 34.1 Write unit tests for corrupted file handling: invalid gzip header, JSON parse error, missing required sections (`tests/test_persistence/test_file_io.py`)
  - [ ] 34.2 Write unit tests for GEDCOM import error paths: non-GEDCOM file, malformed records, unsupported tags (`tests/test_gedcom/test_importer.py`)
  - [ ] 34.3 Write unit tests for missing reference errors: non-existent person_id in family, non-existent source_id in source_ref, non-existent place_id in event (`tests/test_services/test_validation_service.py`)
  - **Requirements:** 3.4, 4.7, 4.8, 22.6

## Task Dependency Graph

```json
{
  "waves": [
    [1],
    [2, 9],
    [3, 4, 10, 16],
    [5, 6, 7, 8, 11, 12, 14, 15],
    [13, 17, 34],
    [18, 19, 23, 24],
    [20, 21, 22, 25, 26, 27, 28, 29, 30, 31, 32],
    [33]
  ]
}
```

## Notes

- Tasks 1-8 form the foundational backend layer and should be completed before any UI tasks.
- Property-based tests (Tasks 5, 6, 15.4, 15.5, 18.4, 18.5, 21.4, 22.4) use the Hypothesis framework and validate the correctness properties defined in the design document.
- UI tasks (16-32) depend on the main window infrastructure and can be parallelized after Task 17 is complete.
- Task 33 (Swedish language) is a cross-cutting concern that should be applied throughout development but is listed separately for final review.
- The GEDCOM pipeline (Tasks 9-14) can be developed in parallel with the UI layer once the data model and persistence layers are complete.
