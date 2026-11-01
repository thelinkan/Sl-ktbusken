"""Registry of the Mandatory_Test_Groups of Requirement 35.

This file is the single source for the conftest hooks, the guard test
(``tests/test_meta/test_mandatory_groups_guard.py``) and the runner
(``scripts/run_mandatory_tests.py``).

Paths are relative to the repository root and use forward slashes.
``required_tests`` entries have the form ``"<module path>::<test name>"``.
A test name matches a function or method by its name, so parametrised tests
match on the function name. A name may end in ``*`` (``test_property_25_*``)
to require at least one test whose name starts with the prefix.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MandatoryGroup:
    key: str  # "reference_preservation", ...
    title_sv: str  # shown by the runner
    requirement: str  # "35.1(a)" ...
    modules: tuple[str, ...]  # test files that belong to the group
    properties: tuple[int, ...]  # design property numbers the group must cover
    required_tests: tuple[str, ...]  # "module::test_name" that must exist and be collected


_SERVICES = "tests/test_services/"
_GEDCOM = "tests/test_gedcom/"


def _req(module: str, *names: str) -> tuple[str, ...]:
    return tuple(f"{module}::{name}" for name in names)


_REFERENCE_INDEX = _SERVICES + "test_person_reference_index.py"
_REFERENCE_RULES = _SERVICES + "test_merge_reference_rules.py"
_FAMILY_INTEGRITY = _SERVICES + "test_merge_family_integrity.py"
_FAILURES = _SERVICES + "test_merge_failures.py"
_SAVED_STATE = _SERVICES + "test_saved_state.py"
_COMMIT_FAULTS = _SERVICES + "test_commit_faults.py"
_COMMIT_REFUSAL = _SERVICES + "test_commit_recovery_refusal.py"
_COMMIT_SUBPROCESS = _SERVICES + "test_commit_subprocess.py"
_RETIRED_IDS = _SERVICES + "test_retired_ids.py"
_REIMPORT = _GEDCOM + "test_merge_reimport.py"

MANDATORY_GROUPS: tuple[MandatoryGroup, ...] = (
    MandatoryGroup(
        key="reference_preservation",
        title_sv="Bevarande av personreferenser",
        requirement="35.1(a)",
        modules=(_REFERENCE_INDEX, _REFERENCE_RULES),
        properties=(25, 29, 30, 31),
        required_tests=(
            *_req(
                _REFERENCE_INDEX,
                "test_inventory_lists_every_person_reference_field",
                "test_inventory_check_fails_for_unlisted_field",
                "test_merge_refused_when_handler_missing",
            ),
            *_req(
                _REFERENCE_RULES,
                "test_every_inventory_row_has_a_rule_test",
                "test_rewire_rows_leave_no_retired_reference",
                "test_property_25_*",
                "test_property_29_*",
                "test_property_30_*",
                "test_property_31_*",
            ),
        ),
    ),
    MandatoryGroup(
        key="family_relationship_integrity",
        title_sv="Familje- och släktskapsintegritet",
        requirement="35.1(b)",
        modules=(_FAMILY_INTEGRITY,),
        properties=(32, 33, 34, 35),
        required_tests=_req(
            _FAMILY_INTEGRITY,
            "test_cycle_blocks_merge",
            "test_self_partner_blocks_merge",
            "test_self_parent_child_link_blocks_merge",
            "test_parent_child_link_types_preserved",
            "test_foster_adoptive_families_resynchronised",
            "test_two_brita_seven_distinct_children",
            "test_same_name_siblings_stay_distinct",
            "test_duplicate_families_stay_separate_with_warning",
            "test_property_32_*",
            "test_property_33_*",
            "test_property_34_*",
            "test_property_35_*",
        ),
    ),
    MandatoryGroup(
        key="failed_merges",
        title_sv="Misslyckade sammanslagningar",
        requirement="35.1(c)",
        modules=(_FAILURES, _SAVED_STATE),
        properties=(39, 47),
        required_tests=(
            *_req(
                _FAILURES,
                "test_failed_merge_leaves_data_unchanged",
                "test_failed_merge_leaves_translation_files_unchanged",
                "test_failed_merge_leaves_dirty_flag_unchanged",
                "test_property_39_*",
            ),
            *_req(
                _SAVED_STATE,
                "test_dirty_project_refused",
                "test_unsaved_editor_refused",
                "test_property_47_*",
            ),
        ),
    ),
    MandatoryGroup(
        key="crash_recovery",
        title_sv="Återställning efter krasch",
        requirement="35.1(d)",
        modules=(_COMMIT_FAULTS, _COMMIT_REFUSAL, _COMMIT_SUBPROCESS),
        properties=(40, 41, 49),
        required_tests=(
            *_req(
                _COMMIT_FAULTS,
                "test_crash_matrix_every_operation",
                "test_recovery_idempotent",
                "test_crash_during_recovery_converges",
                "test_property_40_*",
                "test_property_41_*",
            ),
            *_req(
                _COMMIT_REFUSAL,
                "test_refusal_project_file_matches_neither",
                "test_refusal_persons_json_matches_neither",
                "test_refusal_one_new_other_neither",
                "test_refusal_corrupt_journal",
                "test_refusal_backup_missing_or_corrupt",
                "test_refusal_preserves_every_artifact_byte_for_byte",
                "test_property_49_*",
            ),
            *_req(_COMMIT_SUBPROCESS, "test_os_exit_at_representative_points"),
        ),
    ),
    MandatoryGroup(
        key="retired_id_preservation",
        title_sv="Bevarande av pensionerade id:n",
        requirement="35.1(e)",
        modules=(_RETIRED_IDS,),
        properties=(3,),
        required_tests=_req(
            _RETIRED_IDS,
            "test_retired_id_never_reissued",
            "test_retired_id_with_highest_suffix_not_reissued",
            "test_retired_id_not_reissued_after_save_and_reopen",
            "test_importer_seeded_with_retired_ids",
            "test_property_3_retired_ids",
        ),
    ),
    MandatoryGroup(
        key="gedcom_reimport_after_merge",
        title_sv="GEDCOM-återimport efter sammanslagning",
        requirement="35.1(f)",
        modules=(_REIMPORT,),
        properties=(42, 43),
        required_tests=_req(
            _REIMPORT,
            "test_reimport_identical_file_does_not_recreate_retired_person",
            "test_reimport_edited_variant_matches_by_fingerprint",
            "test_reimport_counts_unchanged",
            "test_both_partners_same_person_gives_warning",
            "test_negative_without_alias_recreates_person",
            "test_property_42_*",
            "test_property_43_*",
        ),
    ),
)

# The guard test is itself mandatory (the only module outside the six groups).
GUARD_MODULE = "tests/test_meta/test_mandatory_groups_guard.py"

# Platform-conditional tests (Windows file-sharing semantics). They are required,
# are the only tests allowed a ``skipif``, and the only permitted condition is
# ``sys.platform != "win32"``. On win32 a skip is turned into a failure.
WINDOWS_ONLY_MODULE = "tests/test_services/test_commit_preflight.py"
WINDOWS_ONLY_TESTS: tuple[str, ...] = (
    f"{WINDOWS_ONLY_MODULE}::test_second_handle_without_write_sharing_refused",
)
WINDOWS_ONLY_SKIPIF_CONDITION = 'sys.platform != "win32"'


def mandatory_modules() -> frozenset[str]:
    """All module paths subject to the mandatory machinery (groups plus guard)."""
    modules = {m for group in MANDATORY_GROUPS for m in group.modules}
    modules.add(GUARD_MODULE)
    return frozenset(modules)


def all_required_tests() -> tuple[str, ...]:
    """Every ``module::name`` entry of every group."""
    return tuple(t for group in MANDATORY_GROUPS for t in group.required_tests)
