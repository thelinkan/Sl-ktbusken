"""Age calculation helper for person box display."""

from __future__ import annotations

from datetime import date
from typing import Optional


def compute_age_display(
    birth_date_str: str,
    death_date_str: Optional[str],
) -> tuple[Optional[str], bool]:
    """Compute age display text for a person box.

    Rules:
    - If person is dead (has death date): show "Blev X år" (or "Blev under 1 år")
    - If person is alive (no death date): show "Är X år" if age < 120,
      otherwise don't show (presumed dead with missing data)
    - over_100 flag is True when living age > 100 (for red text display)

    Args:
        birth_date_str: Birth date as ISO string (YYYY, YYYY-MM, YYYY-MM-DD).
        death_date_str: Death date as ISO string, or None if alive.

    Returns:
        Tuple of (display_text, over_100_flag). display_text is None
        if age cannot be calculated or shouldn't be shown.
    """
    try:
        birth_year = int(birth_date_str[:4])
    except (ValueError, IndexError):
        return None, False

    birth_month = _parse_month(birth_date_str)
    birth_day = _parse_day(birth_date_str)

    if death_date_str:
        # Person is dead — calculate age at death
        try:
            death_year = int(death_date_str[:4])
        except (ValueError, IndexError):
            return None, False

        death_month = _parse_month(death_date_str)
        death_day = _parse_day(death_date_str)

        age = death_year - birth_year
        if death_month < birth_month or (
            death_month == birth_month and death_day < birth_day
        ):
            age -= 1

        if age < 0:
            return None, False
        if age < 1:
            return "Blev under 1 år", False
        return f"Blev {age} år", False
    else:
        # Person presumably alive — calculate current age
        today = date.today()
        age = today.year - birth_year
        if today.month < birth_month or (
            today.month == birth_month and today.day < birth_day
        ):
            age -= 1

        if age < 0 or age >= 120:
            return None, False

        over_100 = age > 100
        return f"Är {age} år", over_100


def _parse_month(date_str: str) -> int:
    """Parse month from ISO date string, defaulting to 1."""
    try:
        if len(date_str) >= 7:
            return int(date_str[5:7])
    except (ValueError, IndexError):
        pass
    return 1


def _parse_day(date_str: str) -> int:
    """Parse day from ISO date string, defaulting to 1."""
    try:
        if len(date_str) >= 10:
            return int(date_str[8:10])
    except (ValueError, IndexError):
        pass
    return 1
