"""Direct link generation for source records."""

from __future__ import annotations

from typing import Optional

from slaktbusken.model.source import Kalltyp, Source


def generate_direct_link(source: Source, kalltyper: list[Kalltyp]) -> Optional[str]:
    """Generate a direct link to the online record for a source.

    The link is formed by concatenating the Källtyp's root_url with the source's
    arkivreferens.

    Args:
        source: The source record.
        kalltyper: All Källtyper in the project (to look up root_url).

    Returns:
        The full URL string if conditions are met, None otherwise.

    Conditions for generating a link:
    1. source.kalltyp_id is non-empty
    2. A Källtyp with that ID exists in kalltyper
    3. That Källtyp has a non-empty root_url
    4. source.arkivreferens is non-empty

    If any condition is not met, returns None.
    """
    if not source.kalltyp_id:
        return None

    kalltyp = None
    for kt in kalltyper:
        if kt.id == source.kalltyp_id:
            kalltyp = kt
            break

    if kalltyp is None:
        return None

    if not kalltyp.root_url:
        return None

    if not source.arkivreferens:
        return None

    return kalltyp.root_url + source.arkivreferens
