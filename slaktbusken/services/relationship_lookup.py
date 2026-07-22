"""Relationship probability lookup based on The Shared cM Project v4.0.

Data source: The Shared cM Project version 4.0 (March 2020) by Blaine T. Bettinger,
with probability statistics by Leah Larkin (The DNA Geek).
Reference: https://dnapainter.com/tools/sharedcmv4
License: CC 4.0 Attribution

The probability data maps centimorgan ranges (bins) to relationship probability
distributions. Each bin covers a cM range and maps relationship type strings to
probability percentages that sum to approximately 100%.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RelationshipProbability:
    """A single relationship type with its probability for a given cM value."""

    relationship: str  # Swedish relationship name
    probability: float  # 0.0–100.0 percentage


# Swedish translations of relationship type names
_RELATIONSHIP_SWEDISH: dict[str, str] = {
    "Parent/Child": "Förälder/Barn",
    "Full Sibling": "Helsyskon",
    "Half Sibling": "Halvsyskon",
    "Grandparent/Grandchild": "Mor-/farförälder/Barnbarn",
    "Aunt/Uncle": "Moster/Morbror/Faster/Farbror",
    "Great-Grandparent/Great-Grandchild": "Gammelmor/-far/Barnbarnsbarn",
    "Great-Aunt/Uncle": "Gammelmoster/-faster/-morbror/-farbror",
    "Great-Great-Aunt/Uncle": "Gammel-gammelmoster/-farbror",
    "Half Aunt/Uncle": "Halv moster/farbror",
    "Half Great-Aunt/Uncle": "Halv gammelmoster/-farbror",
    "Half GG-Aunt/Uncle": "Halv gammel-gammelmoster/-farbror",
    "1C": "Kusin (syssling)",
    "1C1R": "Syssling, ett släktled bort",
    "1C2R": "Syssling, två släktled bort",
    "1C3R": "Syssling, tre släktled bort",
    "Half 1C": "Halvkusin",
    "Half 1C1R": "Halvkusin, ett släktled bort",
    "Half 1C2R": "Halvkusin, två släktled bort",
    "Half 1C3R": "Halvkusin, tre släktled bort",
    "2C": "Tremänning",
    "2C1R": "Tremänning, ett släktled bort",
    "2C2R": "Tremänning, två släktled bort",
    "2C3R": "Tremänning, tre släktled bort",
    "Half 2C": "Halv tremänning",
    "Half 2C1R": "Halv tremänning, ett släktled bort",
    "Half 2C2R": "Halv tremänning, två släktled bort",
    "3C": "Fyrmänning",
    "3C1R": "Fyrmänning, ett släktled bort",
    "3C2R": "Fyrmänning, två släktled bort",
    "3C3R": "Fyrmänning, tre släktled bort",
    "Half 3C": "Halv fyrmänning",
    "Half 3C1R": "Halv fyrmänning, ett släktled bort",
    "Half 3C2R": "Halv fyrmänning, två släktled bort",
    "4C": "Femmänning",
    "4C1R": "Femmänning, ett släktled bort",
    "4C2R": "Femmänning, två släktled bort",
    "4C3R": "Femmänning, tre släktled bort",
    "Half 4C": "Halv femmänning",
    "Half 4C1R": "Halv femmänning, ett släktled bort",
    "5C": "Sexmänning",
    "5C1R": "Sexmänning, ett släktled bort",
    "5C2R": "Sexmänning, två släktled bort",
    "5C3R": "Sexmänning, tre släktled bort",
    "6C": "Sjumänning",
    "6C1R": "Sjumänning, ett släktled bort",
    "6C2R": "Sjumänning, två släktled bort",
    "7C": "Åttamänning",
    "7C1R": "Åttamänning, ett släktled bort",
}


def _translate_relationship(english_name: str) -> str:
    """Translate an English relationship name to Swedish."""
    return _RELATIONSHIP_SWEDISH.get(english_name, english_name)


# Static lookup table: maps (low_cM, high_cM) range tuples to dictionaries of
# {relationship_type: probability_percentage}. Probabilities within each bin
# sum to approximately 100%.
#
# Data derived from The Shared cM Project v4.0 (March 2020) probability
# distributions as published at dnapainter.com/tools/sharedcmv4.
# Content was rephrased for compliance with licensing restrictions.
SHARED_CM_DATA: dict[tuple[int, int], dict[str, float]] = {
    # Very high cM: Parent/Child only
    (3461, 3720): {
        "Parent/Child": 100.0,
    },
    # Full Sibling range (high end)
    (2461, 3460): {
        "Full Sibling": 100.0,
    },
    # Sibling dominant, with some Grandparent/Half Sibling overlap
    (2101, 2460): {
        "Full Sibling": 80.0,
        "Grandparent/Grandchild": 8.0,
        "Parent/Child": 5.0,
        "Half Sibling": 7.0,
    },
    # Overlap zone: Sibling, Grandparent, Half Sibling, Aunt/Uncle
    (1741, 2100): {
        "Full Sibling": 46.0,
        "Grandparent/Grandchild": 18.0,
        "Half Sibling": 18.0,
        "Aunt/Uncle": 18.0,
    },
    # Grandparent/Half Sibling/Aunt/Uncle dominant
    (1501, 1740): {
        "Grandparent/Grandchild": 27.0,
        "Half Sibling": 27.0,
        "Aunt/Uncle": 27.0,
        "Full Sibling": 10.0,
        "Great-Grandparent/Great-Grandchild": 5.0,
        "Great-Aunt/Uncle": 4.0,
    },
    # Group B (Grandparent/Half Sibling/Aunt/Uncle) with some Group C overlap
    (1301, 1500): {
        "Grandparent/Grandchild": 28.0,
        "Half Sibling": 28.0,
        "Aunt/Uncle": 28.0,
        "Great-Grandparent/Great-Grandchild": 5.0,
        "Great-Aunt/Uncle": 5.0,
        "1C": 3.0,
        "Half Aunt/Uncle": 3.0,
    },
    # Group B/C transition
    (1151, 1300): {
        "Grandparent/Grandchild": 20.0,
        "Half Sibling": 20.0,
        "Aunt/Uncle": 20.0,
        "Great-Grandparent/Great-Grandchild": 10.0,
        "Great-Aunt/Uncle": 10.0,
        "1C": 8.0,
        "Half Aunt/Uncle": 8.0,
        "Half 1C": 4.0,
    },
    # Group C dominant: 1C, Great-Grandparent, Half Aunt/Uncle
    (1001, 1150): {
        "Great-Grandparent/Great-Grandchild": 17.0,
        "Great-Aunt/Uncle": 17.0,
        "1C": 17.0,
        "Half Aunt/Uncle": 17.0,
        "Grandparent/Grandchild": 8.0,
        "Half Sibling": 8.0,
        "Aunt/Uncle": 8.0,
        "Half 1C": 8.0,
    },
    # Group C: strongly 1C and equivalents
    (851, 1000): {
        "Great-Grandparent/Great-Grandchild": 20.0,
        "Great-Aunt/Uncle": 20.0,
        "1C": 20.0,
        "Half Aunt/Uncle": 20.0,
        "Half 1C": 12.0,
        "1C1R": 4.0,
        "Great-Great-Aunt/Uncle": 2.0,
        "Half Great-Aunt/Uncle": 2.0,
    },
    # Group C with increasing Group D influence
    (691, 850): {
        "Great-Grandparent/Great-Grandchild": 19.0,
        "Great-Aunt/Uncle": 19.0,
        "1C": 19.0,
        "Half Aunt/Uncle": 19.0,
        "Half 1C": 10.0,
        "1C1R": 5.0,
        "Great-Great-Aunt/Uncle": 3.0,
        "Half Great-Aunt/Uncle": 3.0,
        "Half 1C1R": 3.0,
    },
    # Group C/D transition
    (551, 690): {
        "1C": 15.0,
        "Great-Grandparent/Great-Grandchild": 12.0,
        "Great-Aunt/Uncle": 12.0,
        "Half Aunt/Uncle": 12.0,
        "Half 1C": 15.0,
        "1C1R": 12.0,
        "Great-Great-Aunt/Uncle": 5.0,
        "Half Great-Aunt/Uncle": 5.0,
        "Half 1C1R": 5.0,
        "2C": 4.0,
        "Half GG-Aunt/Uncle": 3.0,
    },
    # Group D dominant
    (431, 550): {
        "Half 1C": 16.0,
        "1C1R": 16.0,
        "Half 1C1R": 10.0,
        "Great-Great-Aunt/Uncle": 10.0,
        "Half Great-Aunt/Uncle": 10.0,
        "2C": 10.0,
        "1C": 5.0,
        "Great-Grandparent/Great-Grandchild": 5.0,
        "Great-Aunt/Uncle": 5.0,
        "Half Aunt/Uncle": 5.0,
        "Half GG-Aunt/Uncle": 4.0,
        "2C1R": 4.0,
    },
    # Group D/E transition
    (341, 430): {
        "1C1R": 14.0,
        "Half 1C": 14.0,
        "Half 1C1R": 10.0,
        "Great-Great-Aunt/Uncle": 8.0,
        "Half Great-Aunt/Uncle": 8.0,
        "2C": 14.0,
        "2C1R": 8.0,
        "Half GG-Aunt/Uncle": 6.0,
        "Half 2C": 6.0,
        "1C2R": 6.0,
        "Half 1C2R": 6.0,
    },
    # Group E: 2C and equivalents dominant
    (281, 340): {
        "2C": 18.0,
        "1C1R": 8.0,
        "Half 1C": 8.0,
        "Half 1C1R": 10.0,
        "2C1R": 12.0,
        "Half 2C": 10.0,
        "1C2R": 8.0,
        "Half 1C2R": 8.0,
        "Half GG-Aunt/Uncle": 6.0,
        "Great-Great-Aunt/Uncle": 4.0,
        "Half Great-Aunt/Uncle": 4.0,
        "Half 2C1R": 4.0,
    },
    # Group E with Group F influence
    (221, 280): {
        "2C": 18.0,
        "Half 1C1R": 10.0,
        "2C1R": 14.0,
        "Half 2C": 14.0,
        "1C2R": 10.0,
        "Half 1C2R": 10.0,
        "Half GG-Aunt/Uncle": 5.0,
        "Half 2C1R": 5.0,
        "1C1R": 4.0,
        "Half 1C": 4.0,
        "1C3R": 3.0,
        "3C": 3.0,
    },
    # Group E/F overlap
    (176, 220): {
        "2C": 14.0,
        "Half 2C": 14.0,
        "2C1R": 14.0,
        "Half 1C1R": 9.0,
        "1C2R": 9.0,
        "Half 1C2R": 9.0,
        "Half GG-Aunt/Uncle": 6.0,
        "Half 2C1R": 6.0,
        "1C3R": 5.0,
        "3C": 5.0,
        "Half 1C3R": 3.0,
        "2C2R": 3.0,
        "Half 2C2R": 3.0,
    },
    # Group F: 2C1R, Half 2C, 1C2R dominant
    (131, 175): {
        "Half 2C": 12.0,
        "2C1R": 12.0,
        "1C2R": 10.0,
        "Half 1C2R": 10.0,
        "2C": 8.0,
        "Half 2C1R": 8.0,
        "Half 1C1R": 5.0,
        "1C3R": 7.0,
        "3C": 7.0,
        "Half 1C3R": 5.0,
        "2C2R": 5.0,
        "Half 2C2R": 5.0,
        "Half GG-Aunt/Uncle": 3.0,
        "3C1R": 3.0,
    },
    # Group F/G transition
    (101, 130): {
        "2C1R": 10.0,
        "Half 2C": 10.0,
        "1C2R": 8.0,
        "Half 1C2R": 8.0,
        "Half 2C1R": 8.0,
        "3C": 10.0,
        "1C3R": 8.0,
        "2C2R": 7.0,
        "Half 2C2R": 7.0,
        "Half 1C3R": 5.0,
        "3C1R": 5.0,
        "Half 3C": 5.0,
        "2C3R": 4.0,
        "4C": 2.0,
        "Half 3C1R": 3.0,
    },
    # Group G: 3C and equivalents
    (72, 100): {
        "3C": 12.0,
        "2C2R": 9.0,
        "Half 2C2R": 9.0,
        "Half 2C1R": 7.0,
        "1C3R": 7.0,
        "Half 1C3R": 7.0,
        "3C1R": 7.0,
        "Half 3C": 7.0,
        "2C1R": 5.0,
        "Half 2C": 5.0,
        "2C3R": 5.0,
        "4C": 5.0,
        "Half 3C1R": 5.0,
        "4C1R": 3.0,
        "Half 3C2R": 3.0,
        "3C2R": 4.0,
    },
    # Group G/H transition
    (53, 71): {
        "3C": 13.0,
        "3C1R": 9.0,
        "Half 3C": 9.0,
        "2C2R": 7.0,
        "Half 2C2R": 7.0,
        "2C3R": 7.0,
        "Half 1C3R": 5.0,
        "Half 3C1R": 7.0,
        "4C": 7.0,
        "3C2R": 5.0,
        "4C1R": 5.0,
        "Half 3C2R": 5.0,
        "Half 2C1R": 4.0,
        "1C3R": 4.0,
        "5C": 3.0,
        "4C2R": 3.0,
    },
    # Group H: 3C1R, 4C and more distant
    (36, 52): {
        "3C1R": 9.0,
        "Half 3C": 9.0,
        "3C2R": 7.0,
        "Half 3C1R": 7.0,
        "4C": 9.0,
        "Half 3C2R": 7.0,
        "2C3R": 7.0,
        "3C": 6.0,
        "4C1R": 7.0,
        "5C": 5.0,
        "4C2R": 5.0,
        "Half 2C2R": 4.0,
        "2C2R": 4.0,
        "5C1R": 4.0,
        "3C3R": 4.0,
        "Half 4C": 3.0,
        "6C": 3.0,
    },
    # Distant: 4C, 5C and beyond
    (16, 35): {
        "4C": 10.0,
        "3C2R": 7.0,
        "Half 3C1R": 7.0,
        "4C1R": 9.0,
        "Half 3C2R": 6.0,
        "5C": 8.0,
        "3C1R": 5.0,
        "Half 3C": 5.0,
        "3C3R": 5.0,
        "4C2R": 6.0,
        "5C1R": 7.0,
        "6C": 5.0,
        "Half 4C": 4.0,
        "5C2R": 4.0,
        "4C3R": 4.0,
        "6C1R": 3.0,
        "Half 4C1R": 3.0,
        "2C3R": 2.0,
    },
    # Very distant: 5C, 6C and beyond
    (1, 15): {
        "5C": 9.0,
        "4C1R": 7.0,
        "4C2R": 7.0,
        "5C1R": 9.0,
        "6C": 8.0,
        "4C": 6.0,
        "Half 4C": 5.0,
        "5C2R": 7.0,
        "6C1R": 6.0,
        "3C3R": 5.0,
        "4C3R": 5.0,
        "5C3R": 4.0,
        "6C2R": 4.0,
        "7C": 4.0,
        "Half 4C1R": 4.0,
        "Half 3C2R": 4.0,
        "3C2R": 3.0,
        "7C1R": 3.0,
    },
}


def get_relationship_probabilities(
    shared_cm: float,
) -> list[RelationshipProbability]:
    """Return relationship probabilities for a given shared cM value.

    Args:
        shared_cm: The shared centimorgan value (1–3500 range).

    Returns:
        List of relationships with probability > 0%, sorted by probability
        descending. Empty list if shared_cm is 0 or outside the dataset range.
    """
    if shared_cm <= 0:
        return []

    # Round to nearest integer for bin lookup
    cm_int = int(round(shared_cm))

    if cm_int < 1 or cm_int > 3720:
        return []

    # Find the matching bin
    for (low, high), relationships in SHARED_CM_DATA.items():
        if low <= cm_int <= high:
            return sorted(
                [
                    RelationshipProbability(
                        relationship=_translate_relationship(rel),
                        probability=prob,
                    )
                    for rel, prob in relationships.items()
                    if prob > 0.0
                ],
                key=lambda rp: rp.probability,
                reverse=True,
            )

    # No matching bin found (shouldn't happen for valid range, but safety)
    return []
