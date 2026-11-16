"""Allow-list of places that may construct ResidenceFact without origins.

Each entry is ``(module, function, reason)``. Every other construction of a
ResidenceFact in application code must copy the origins of an existing fact
(``dataclasses.replace`` or ``copy.deepcopy``), or be the GEDCOM importer.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.mandatory_integrity

RESIDENCE_CONSTRUCTION_ALLOWLIST: tuple[tuple[str, str, str], ...] = (
    (
        "slaktbusken/ui/editors/residence_editor.py",
        "_apply_bulk_plan",
        "New residence typed by the user in the bulk paste dialog; it has no "
        "GEDCOM record, so origins stay an empty list (Requirement 22.22).",
    ),
    (
        "slaktbusken/ui/editors/residence_editor.py",
        "build_fact_from_fields",
        "Builds a residence from the form only when no existing residence is "
        "edited (a new residence); an existing one is rebuilt with "
        "dataclasses.replace and keeps its origins, so a new one has no GEDCOM "
        "record and its origins stay an empty list (Requirement 22.22).",
    ),
    (
        "slaktbusken/ui/editors/person_editor.py",
        "_on_create_residence",
        "New residence added by the user from the Boenden tab; it has no "
        "GEDCOM record, so origins stay an empty list (Requirement 22.22).",
    ),
)
