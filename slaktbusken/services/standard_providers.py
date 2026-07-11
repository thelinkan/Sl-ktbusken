"""Standard Leverantörer and Källtyper initialization for new projects.

This module defines the predefined set of source providers (Leverantörer)
and source types (Källtyper) that are populated when a new project is
created. The data is defined as constants and the initialization function
generates fresh UUIDs for each entity at creation time.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
"""

from __future__ import annotations

import uuid
from typing import Union

from slaktbusken.model.project import ProjectData
from slaktbusken.model.source import Kalltyp, Leverantor

# Type alias for Källtyp entries: either a plain name string or a dict
# with name and optional root_url.
KalltypEntry = Union[str, dict[str, str]]

# The shared list of Källtyper used by both "Arkiv Digital" and
# "Nationell arkivdatabas" (Requirement 3.2, 3.3).
_SHARED_KALLTYPER: list[str] = [
    "Husförhörslängd",
    "Församlingsbok",
    "Mantalslängd",
    "Folkräkning",
    "Inflyttningslängd",
    "Utflyttningslängd",
    "In- och Utflyttningslängd",
    "Födelse- och dopbok",
    "Lysnings- och vigselbok",
    "Död- och begravningsbok",
    "Generalmönstringsrullor",
    "Bouppteckningar",
    "Konfirmationsbok",
    "Övrigt",
]

# Complete definition of all standard providers and their Källtyper.
# Order matters — Requirement 3.1 specifies the exact order.
STANDARD_PROVIDERS: list[dict[str, Union[str, list[KalltypEntry]]]] = [
    {
        "name": "Arkiv Digital",
        "kalltyper": _SHARED_KALLTYPER,
    },
    {
        "name": "Nationell arkivdatabas",
        "kalltyper": _SHARED_KALLTYPER,
    },
    {
        "name": "Rötter.se",
        "kalltyper": [
            {
                "name": "Sveriges Dödbok Webb",
                "root_url": "https://www.rotter.se/abonnemang/sveriges-dodbok-webb/post/",
            },
            {"name": "Sveriges Dödbok (sticka/dvd)"},
            {"name": "Övrigt"},
        ],
    },
    {
        "name": "Skatteverket",
        "kalltyper": ["Personbild (6401)", "Övrigt"],
    },
    {
        "name": "Övrigt",
        "kalltyper": ["Dödsannons", "Tidningsartikel", "Övrig databas", "Övrigt"],
    },
]


def initialize_standard_providers(project_data: ProjectData) -> None:
    """Populate project_data with standard Leverantörer and Källtyper.

    Generates fresh UUIDs for each Leverantör and Källtyp. Each Källtyp
    is linked to its parent Leverantör via leverantor_id.

    This function should ONLY be called during new project creation, NOT
    when opening existing projects (Requirement 3.8).

    Args:
        project_data: The ProjectData instance to populate.
    """
    for provider_def in STANDARD_PROVIDERS:
        leverantor_id = str(uuid.uuid4())
        leverantor = Leverantor(
            id=leverantor_id,
            name=str(provider_def["name"]),
        )
        project_data.leverantorer.append(leverantor)

        kalltyper_defs = provider_def["kalltyper"]
        assert isinstance(kalltyper_defs, list)

        for kt_def in kalltyper_defs:
            kalltyp_id = str(uuid.uuid4())

            if isinstance(kt_def, str):
                kalltyp = Kalltyp(
                    id=kalltyp_id,
                    leverantor_id=leverantor_id,
                    name=kt_def,
                )
            else:
                # Dict with name and optional root_url.
                kalltyp = Kalltyp(
                    id=kalltyp_id,
                    leverantor_id=leverantor_id,
                    name=kt_def["name"],
                    root_url=kt_def.get("root_url", ""),
                )

            project_data.kalltyper.append(kalltyp)
