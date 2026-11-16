"""Allow-list of change paths that mutate a ProjectData collection directly.

Each entry is ``(module, function, reason)``; ``module`` is relative to
``slaktbusken/``. Every entry was reviewed in task 6.3. An entry means the
mutation is covered elsewhere (an Edit_Session commit, a ``mark_changed`` call
in ``app.py`` after the dialog, or a working copy), not that it is exempt from
marking the project changed.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.mandatory_integrity

CHANGE_PATH_ALLOWLIST: tuple[tuple[str, str, str], ...] = (
    (
        'app.py',
        'add_standalone_person',
        'Appends the new person while the Edit_Session of the add-person dialog is active; the commit marks changed (task 7.2).',
    ),
    (
        'app.py',
        '_add_relative_in_session',
        'Appends the relative and its families inside the Edit_Session opened for the add-relative dialog (task 7.2).',
    ),
    (
        'gedcom/importer.py',
        '_reconcile_imported_placement_families',
        'Import runs on a working copy, task 11.2 rebuilds the import path; the import is registered in the change-path registry as gedcom_import (task 11.5).',
    ),
    (
        'gedcom/importer.py',
        '_process_sources',
        'Import runs on a working copy, task 11.2 rebuilds the import path; the import is registered in the change-path registry as gedcom_import (task 11.5).',
    ),
    (
        'gedcom/importer.py',
        '_attach_arkiv_digital_repository',
        'Import runs on a working copy, task 11.2 rebuilds the import path; the import is registered in the change-path registry as gedcom_import (task 11.5).',
    ),
    (
        'gedcom/importer.py',
        '_update_translation_xref',
        'Import runs on a working copy, task 11.2 rebuilds the import path; the import is registered in the change-path registry as gedcom_import (task 11.5).',
    ),
    (
        'gedcom/importer.py',
        '_create_person',
        'Import runs on a working copy, task 11.2 rebuilds the import path; the import is registered in the change-path registry as gedcom_import (task 11.5).',
    ),
    (
        'gedcom/importer.py',
        '_update_person',
        'Import runs on a working copy, task 11.2 rebuilds the import path; the import is registered in the change-path registry as gedcom_import (task 11.5).',
    ),
    (
        'gedcom/importer.py',
        '_add_residence',
        'Appends the residence that task 10.3 creates for a new RESI record; import runs on a working copy, task 11.2 rebuilds the import path; the import is registered in the change-path registry as gedcom_import (task 11.5). _resolve_residence_place and _derive_residence mutate no collection themselves (places go through _resolve_place), so they need no entry.',
    ),
    (
        'gedcom/importer.py',
        '_create_family',
        'Import runs on a working copy, task 11.2 rebuilds the import path; the import is registered in the change-path registry as gedcom_import (task 11.5).',
    ),
    (
        'gedcom/importer.py',
        '_update_family',
        'Import runs on a working copy, task 11.2 rebuilds the import path; the import is registered in the change-path registry as gedcom_import (task 11.5).',
    ),
    (
        'gedcom/importer.py',
        '_create_paired_end_event',
        'Import runs on a working copy, task 11.2 rebuilds the import path; the import is registered in the change-path registry as gedcom_import (task 11.5).',
    ),
    (
        'gedcom/importer.py',
        '_create_event',
        'Import runs on a working copy, task 11.2 rebuilds the import path; the import is registered in the change-path registry as gedcom_import (task 11.5).',
    ),
    (
        'gedcom/importer.py',
        '_create_family_event',
        'Import runs on a working copy, task 11.2 rebuilds the import path; the import is registered in the change-path registry as gedcom_import (task 11.5).',
    ),
    (
        'gedcom/importer.py',
        '_resolve_place',
        'Import runs on a working copy, task 11.2 rebuilds the import path; the import is registered in the change-path registry as gedcom_import (task 11.5).',
    ),
    (
        'gedcom/importer.py',
        '_resolve_single_word_place',
        'Import runs on a working copy, task 11.2 rebuilds the import path; the import is registered in the change-path registry as gedcom_import (task 11.5).',
    ),
    (
        'services/place_dedupe.py',
        'deduplicate_project_places',
        'Reviewed in task 6.3: runs only from persistence.serialization.deserialize while a project is loaded; the load establishes the clean state, so no mark is wanted.',
    ),
    (
        'ui/editors/dna_editor.py',
        '_on_choose_logo',
        'Dna_Editor mutates live data; app.show_dna_editor calls mark_changed after the dialog closes, and nested use from the Person_Editor runs inside its Edit_Session.',
    ),
    (
        'ui/editors/dna_editor.py',
        '_on_remove_company',
        'Dna_Editor mutates live data; app.show_dna_editor calls mark_changed after the dialog closes, and nested use from the Person_Editor runs inside its Edit_Session.',
    ),
    (
        'ui/editors/dna_editor.py',
        '_on_save_company',
        'Dna_Editor mutates live data; app.show_dna_editor calls mark_changed after the dialog closes, and nested use from the Person_Editor runs inside its Edit_Session.',
    ),
    (
        'ui/editors/dna_editor.py',
        '_on_remove_profile',
        'Dna_Editor mutates live data; app.show_dna_editor calls mark_changed after the dialog closes, and nested use from the Person_Editor runs inside its Edit_Session.',
    ),
    (
        'ui/editors/dna_editor.py',
        '_on_save_profile',
        'Dna_Editor mutates live data; app.show_dna_editor calls mark_changed after the dialog closes, and nested use from the Person_Editor runs inside its Edit_Session.',
    ),
    (
        'ui/editors/dna_editor.py',
        '_on_remove_match',
        'Dna_Editor mutates live data; app.show_dna_editor calls mark_changed after the dialog closes, and nested use from the Person_Editor runs inside its Edit_Session.',
    ),
    (
        'ui/editors/dna_editor.py',
        '_on_save_match',
        'Dna_Editor mutates live data; app.show_dna_editor calls mark_changed after the dialog closes, and nested use from the Person_Editor runs inside its Edit_Session.',
    ),
    (
        'ui/editors/dna_editor.py',
        '_on_remove_segment',
        'Dna_Editor mutates live data; app.show_dna_editor calls mark_changed after the dialog closes, and nested use from the Person_Editor runs inside its Edit_Session.',
    ),
    (
        'ui/editors/dna_editor.py',
        '_on_save_segment',
        'Dna_Editor mutates live data; app.show_dna_editor calls mark_changed after the dialog closes, and nested use from the Person_Editor runs inside its Edit_Session.',
    ),
    (
        'ui/editors/dna_editor.py',
        '_on_create_cluster',
        'Dna_Editor mutates live data; app.show_dna_editor calls mark_changed after the dialog closes, and nested use from the Person_Editor runs inside its Edit_Session.',
    ),
    (
        'ui/editors/dna_editor.py',
        '_on_remove_cluster',
        'Dna_Editor mutates live data; app.show_dna_editor calls mark_changed after the dialog closes, and nested use from the Person_Editor runs inside its Edit_Session.',
    ),
    (
        'ui/editors/dna_editor.py',
        '_on_add_triangulation',
        'Dna_Editor mutates live data; app.show_dna_editor calls mark_changed after the dialog closes, and nested use from the Person_Editor runs inside its Edit_Session.',
    ),
    (
        'ui/editors/dna_editor.py',
        '_on_remove_triangulation',
        'Dna_Editor mutates live data; app.show_dna_editor calls mark_changed after the dialog closes, and nested use from the Person_Editor runs inside its Edit_Session.',
    ),
    (
        'ui/editors/dna_editor.py',
        '_on_save_triangulation',
        'Dna_Editor mutates live data; app.show_dna_editor calls mark_changed after the dialog closes, and nested use from the Person_Editor runs inside its Edit_Session.',
    ),
    (
        'ui/editors/event_editor.py',
        '_on_photo_add',
        'Event_Editor is only opened from the Person_Editor and mutates live data inside its Edit_Session (task 7.2); the commit marks changed.',
    ),
    (
        'ui/editors/event_editor.py',
        '_on_event_media_add',
        'Event_Editor is only opened from the Person_Editor and mutates live data inside its Edit_Session (task 7.2); the commit marks changed.',
    ),
    (
        'ui/editors/event_editor.py',
        '_offer_create_matching_placement_start',
        'Event_Editor is only opened from the Person_Editor and mutates live data inside its Edit_Session (task 7.2); the commit marks changed.',
    ),
    (
        'ui/editors/media_editor.py',
        '_on_delete_media',
        'Media_Editor mutates live data; app._open_single_entity_editor marks changed after save or media deletion, nested use runs inside the Person_Editor Edit_Session.',
    ),
    (
        'ui/editors/media_editor.py',
        '_on_save',
        'Media_Editor mutates live data; app._open_single_entity_editor marks changed after save or media deletion, nested use runs inside the Person_Editor Edit_Session.',
    ),
    (
        'ui/editors/person_editor.py',
        '_open_placement_event_editor',
        'Mutates live data inside the Edit_Session of the Person_Editor (committed or rolled back as one unit, task 7.2).',
    ),
    (
        'ui/editors/person_editor.py',
        '_on_add_event',
        'Mutates live data inside the Edit_Session of the Person_Editor (committed or rolled back as one unit, task 7.2).',
    ),
    (
        'ui/editors/person_editor.py',
        '_on_remove_event',
        'Mutates live data inside the Edit_Session of the Person_Editor (committed or rolled back as one unit, task 7.2).',
    ),
    (
        'ui/editors/person_editor.py',
        '_ensure_family_for_event',
        'Mutates live data inside the Edit_Session of the Person_Editor (committed or rolled back as one unit, task 7.2).',
    ),
    (
        'ui/editors/person_editor.py',
        '_on_create_residence',
        'Mutates live data inside the Edit_Session of the Person_Editor (committed or rolled back as one unit, task 7.2).',
    ),
    (
        'ui/editors/person_editor.py',
        '_on_delete_residence',
        'Mutates live data inside the Edit_Session of the Person_Editor (committed or rolled back as one unit, task 7.2).',
    ),
    (
        'ui/editors/person_editor.py',
        '_on_add_dna_profile',
        'Mutates live data inside the Edit_Session of the Person_Editor (committed or rolled back as one unit, task 7.2).',
    ),
    (
        'ui/editors/person_editor.py',
        '_on_add_dna_match',
        'Mutates live data inside the Edit_Session of the Person_Editor (committed or rolled back as one unit, task 7.2).',
    ),
    (
        'ui/editors/person_editor.py',
        '_on_add_triangulation',
        'Mutates live data inside the Edit_Session of the Person_Editor (committed or rolled back as one unit, task 7.2).',
    ),
    (
        'ui/editors/place_editor.py',
        '_on_delete_place',
        'Place_Editor: save appends a place and save_requested is connected to mark_changed (app.show_place_editor); the delete fallback without a ProjectService is headless only; nested use runs inside the Person_Editor Edit_Session.',
    ),
    (
        'ui/editors/place_editor.py',
        '_on_save',
        'Place_Editor: save appends a place and save_requested is connected to mark_changed (app.show_place_editor); the delete fallback without a ProjectService is headless only; nested use runs inside the Person_Editor Edit_Session.',
    ),
    (
        'ui/editors/place_editor.py',
        '_on_photo_add',
        'Place_Editor: save appends a place and save_requested is connected to mark_changed (app.show_place_editor); the delete fallback without a ProjectService is headless only; nested use runs inside the Person_Editor Edit_Session.',
    ),
    (
        'ui/editors/place_translation_editor.py',
        '_on_add',
        'Place_Translation_Editor mutates live data; app.show_place_translation_editor calls mark_changed when editor.is_dirty. The no-service fallbacks of the delete and create paths are for headless use only.',
    ),
    (
        'ui/editors/place_translation_editor.py',
        '_on_create_place',
        'Place_Translation_Editor mutates live data; app.show_place_translation_editor calls mark_changed when editor.is_dirty. The no-service fallbacks of the delete and create paths are for headless use only.',
    ),
    (
        'ui/editors/place_translation_editor.py',
        '_on_remove',
        'Place_Translation_Editor mutates live data; app.show_place_translation_editor calls mark_changed when editor.is_dirty. The no-service fallbacks of the delete and create paths are for headless use only.',
    ),
    (
        'ui/editors/provider_editor.py',
        '_save_new_leverantor',
        'Provider_Editor edits live data; app.show_provider_editor calls mark_changed after the dialog closes.',
    ),
    (
        'ui/editors/provider_editor.py',
        '_save_new_kalltyp',
        'Provider_Editor edits live data; app.show_provider_editor calls mark_changed after the dialog closes.',
    ),
    (
        'ui/editors/repository_editor.py',
        '_on_delete_repository',
        'Repository_Editor is only opened nested from the Source_Editor: inside the Person_Editor session, or standalone under the Source_Editor whose save_requested calls mark_changed (app.show_source_editor).',
    ),
    (
        'ui/editors/residence_editor.py',
        '_on_bulk_execute',
        'Residence_Editor is only opened from the Person_Editor (Boenden tab, residents dialog) and mutates live data inside its Edit_Session (task 7.2); the commit marks changed.',
    ),
    (
        'ui/editors/residence_editor.py',
        '_apply_bulk_plan',
        'Residence_Editor is only opened from the Person_Editor (Boenden tab, residents dialog) and mutates live data inside its Edit_Session (task 7.2); the commit marks changed.',
    ),
    (
        'ui/editors/residence_editor.py',
        '_create_source_from_candidate',
        'Residence_Editor is only opened from the Person_Editor (Boenden tab, residents dialog) and mutates live data inside its Edit_Session (task 7.2); the commit marks changed.',
    ),
    (
        'ui/editors/residence_editor.py',
        '_on_split',
        'Residence_Editor is only opened from the Person_Editor (Boenden tab, residents dialog) and mutates live data inside its Edit_Session (task 7.2); the commit marks changed.',
    ),
    (
        'ui/editors/residence_editor.py',
        '_on_create_flytt',
        'Residence_Editor is only opened from the Person_Editor (Boenden tab, residents dialog) and mutates live data inside its Edit_Session (task 7.2); the commit marks changed.',
    ),
    (
        'ui/editors/residence_editor.py',
        '_perform_merge',
        'Residence_Editor is only opened from the Person_Editor (Boenden tab, residents dialog) and mutates live data inside its Edit_Session (task 7.2); the commit marks changed.',
    ),
    (
        'ui/editors/residence_editor.py',
        '_commit_fact',
        'Residence_Editor is only opened from the Person_Editor (Boenden tab, residents dialog) and mutates live data inside its Edit_Session (task 7.2); the commit marks changed.',
    ),
    (
        'ui/editors/residence_editor.py',
        '_replace_fact_in_project',
        'Residence_Editor is only opened from the Person_Editor (Boenden tab, residents dialog) and mutates live data inside its Edit_Session (task 7.2); the commit marks changed.',
    ),
    (
        'ui/editors/residence_editor.py',
        '_remove_fact_from_project',
        'Residence_Editor is only opened from the Person_Editor (Boenden tab, residents dialog) and mutates live data inside its Edit_Session (task 7.2); the commit marks changed.',
    ),
    (
        'ui/editors/source_editor.py',
        '_on_delete_source',
        'Source_Editor mutates live data; app.show_source_editor connects save_requested to mark_changed, nested use runs inside the Person_Editor Edit_Session. _on_add_media appends before save and emits media_added, which app.show_source_editor and app._open_single_entity_editor connect to mark_changed.',
    ),
    (
        'ui/editors/source_editor.py',
        '_on_add_media',
        'Source_Editor mutates live data; app.show_source_editor connects save_requested to mark_changed, nested use runs inside the Person_Editor Edit_Session. _on_add_media appends before save and emits media_added, which app.show_source_editor and app._open_single_entity_editor connect to mark_changed.',
    ),
    (
        'ui/editors/source_editor.py',
        '_on_save',
        'Source_Editor mutates live data; app.show_source_editor connects save_requested to mark_changed, nested use runs inside the Person_Editor Edit_Session. _on_add_media appends before save and emits media_added, which app.show_source_editor and app._open_single_entity_editor connect to mark_changed.',
    ),
    (
        'ui/editors/source_translation_editor.py',
        '_on_add',
        'Source_Translation_Editor edits live data; app.show_source_translation_editor calls mark_changed when editor.is_dirty.',
    ),
    (
        'ui/editors/source_translation_editor.py',
        '_on_remove',
        'Source_Translation_Editor edits live data; app.show_source_translation_editor calls mark_changed when editor.is_dirty.',
    ),
    (
        'ui/widgets/foto_tab.py',
        '_on_delete_photo',
        'FotoTab lives in the Person_Editor and mutates live data inside its Edit_Session (task 7.2).',
    ),
    (
        'ui/widgets/foto_tab.py',
        '_on_add_photo',
        'FotoTab lives in the Person_Editor and mutates live data inside its Edit_Session (task 7.2).',
    ),
)
