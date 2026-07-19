"""Source, repository, and structured reference data containers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union


@dataclass
class StructuredReference:
    """A bag of source-type-specific structured reference fields."""

    fields: dict[str, Optional[Union[str, int]]] = field(default_factory=dict)


@dataclass
class RepositoryRef:
    """A reference linking a source to a repository holding."""

    repository_id: str
    call_number: str = ""
    source_type: str = ""
    image_number: Optional[int] = None
    page_number: Optional[int] = None
    media_type: str = ""
    media_name: str = ""
    notes: str = ""


@dataclass
class Leverantor:
    """A source provider (e.g., Arkiv Digital, Rötter.se)."""

    id: str
    name: str
    comment: str = ""


@dataclass
class Kalltyp:
    """A source type belonging to a specific Leverantör."""

    id: str
    leverantor_id: str
    name: str
    comment: str = ""
    root_url: str = ""


@dataclass
class ArkivReferens:
    """A single archive reference entry linking a provider name to a reference value."""

    leverantor_name: str
    reference_value: str


@dataclass
class Source:
    """A genealogical source record."""

    id: str
    provider: str
    source_type: str
    title: str
    reference_text: str = ""
    provider_ref: str = ""
    short_note: str = ""
    free_note: str = ""
    structured_reference: StructuredReference = field(default_factory=StructuredReference)
    media_ids: list[str] = field(default_factory=list)
    repository_refs: list[RepositoryRef] = field(default_factory=list)
    leverantor_id: str = ""
    kalltyp_id: str = ""
    arkivreferens: str = ""
    arkivreferenser: list[ArkivReferens] = field(default_factory=list)


@dataclass
class Repository:
    """An archive or repository holding sources."""

    id: str
    name: str
    type: str
    address: Optional[str] = None
    phone: list[str] = field(default_factory=list)
    email: list[str] = field(default_factory=list)
    web: list[str] = field(default_factory=list)
    notes: str = ""
    external_ids: list[str] = field(default_factory=list)
