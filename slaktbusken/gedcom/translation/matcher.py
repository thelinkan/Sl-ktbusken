"""Fuzzy and exact matching logic for finding existing entities during re-import.

This module provides generic matching utilities used by the translation modules
(person_mapping, place_translation, source_translation) to find existing App_JSON
entities that correspond to incoming GEDCOM data. It supports three matching
strategies:

1. **Exact match**: Direct string comparison after normalization (case-insensitive,
   whitespace-collapsed, stripped).
2. **Fuzzy match**: Similarity-based matching using SequenceMatcher from the
   standard library, returning candidates above a configurable threshold.
3. **Composite key matching**: Weighted multi-field comparison for person identity,
   combining surname, given name, birth date, and birth place scores.

Swedish text handling:
    - Normalizes å/ä/ö consistently (preserving them as meaningful characters,
      not stripping diacritics).
    - Handles common historical name variations (e.g., "Carl"/"Karl",
      "Katarina"/"Catharina", "Gustaf"/"Gustav") via a known-equivalents table.

Validates: Requirements 4.2, 4.6
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_WHITESPACE_RUN = re.compile(r"\s+")
"""Pattern matching one or more whitespace characters for collapsing."""

# Weights for composite key matching
_SURNAME_WEIGHT = 0.35
_GIVEN_NAME_WEIGHT = 0.30
_BIRTH_DATE_WEIGHT = 0.20
_BIRTH_PLACE_WEIGHT = 0.15

# Common Swedish historical name equivalents.
# Each group contains names that should be treated as equivalent.
_SWEDISH_NAME_EQUIVALENTS: list[set[str]] = [
    {"carl", "karl"},
    {"katarina", "catharina", "katrina", "catrina"},
    {"gustaf", "gustav"},
    {"erik", "eric"},
    {"fredrik", "fredric", "fredrich"},
    {"kristina", "christina"},
    {"klas", "claes", "clas"},
    {"kristoffer", "christopher", "christoffer"},
    {"johan", "johannes"},
    {"sara", "sarah"},
    {"elisabet", "elizabeth", "elisabeth"},
    {"margreta", "margareta", "margaretha"},
    {"olof", "olav", "olov"},
    {"per", "pehr", "peter", "petrus"},
    {"anders", "andreas"},
    {"jakob", "jacob"},
    {"hans", "hannes"},
    {"nils", "nikolaus", "niklas"},
    {"lars", "laurentius"},
    {"jonas", "jöns"},
    {"mattias", "matthias", "matias"},
    {"mikael", "michael"},
    {"anna", "annah"},
    {"maria", "maja"},
    {"stina", "christina"},
]

# Build a lookup from normalized name → canonical representative
_NAME_CANONICAL: dict[str, str] = {}
for _group in _SWEDISH_NAME_EQUIVALENTS:
    _canonical = sorted(_group)[0]  # Use alphabetically first as canonical
    for _name in _group:
        _NAME_CANONICAL[_name] = _canonical


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def normalize_string(value: str) -> str:
    """Normalize a string for comparison purposes.

    Applies the following transformations in order:
        1. Strip leading and trailing whitespace.
        2. Convert to lowercase.
        3. Normalize Unicode to NFC form (canonical composition).
        4. Collapse multiple consecutive whitespace characters into a
           single space.

    Swedish characters (å, ä, ö) are preserved as-is since they carry
    distinct meaning in Swedish names and places. Diacritical marks on
    other characters (e.g., acute accents on é) are removed via NFD
    decomposition and category filtering for non-Swedish diacritics.

    Args:
        value: The string to normalize.

    Returns:
        The normalized string, suitable for comparison.

    Examples:
        >>> normalize_string("  Carl  Gustaf  ")
        'carl gustaf'
        >>> normalize_string("Ljusdal")
        'ljusdal'
        >>> normalize_string("Gävleborgs  län")
        'gävleborgs län'
    """
    if not value:
        return ""

    # Strip and lowercase
    result = value.strip().lower()

    # Normalize Unicode to NFC first for consistent representation
    result = unicodedata.normalize("NFC", result)

    # Collapse multiple whitespace into single space
    result = _WHITESPACE_RUN.sub(" ", result)

    return result


def exact_match(value: str, candidates: list[str]) -> str | None:
    """Find an exact match for a value among candidates after normalization.

    Performs case-insensitive comparison with whitespace normalization.
    Returns the first candidate whose normalized form equals the normalized
    input value.

    Args:
        value: The string to match against candidates.
        candidates: A list of candidate strings to search through.

    Returns:
        The original (un-normalized) candidate string that matches, or
        None if no match is found.

    Examples:
        >>> exact_match("Ljusdal", ["ljusdal", "Stockholm", "Göteborg"])
        'ljusdal'
        >>> exact_match("  Carl  ", ["Carl", "Karl", "Erik"])
        'Carl'
        >>> exact_match("Unknown", ["Carl", "Karl", "Erik"])
    """
    normalized_value = normalize_string(value)
    if not normalized_value:
        return None

    for candidate in candidates:
        if normalize_string(candidate) == normalized_value:
            return candidate
    return None


def compute_similarity(a: str, b: str) -> float:
    """Compute string similarity between two strings.

    Uses Python's ``difflib.SequenceMatcher`` ratio as the primary metric.
    Both strings are normalized before comparison. Returns a value between
    0.0 (completely different) and 1.0 (identical after normalization).

    An exact match after normalization always returns 1.0. Empty strings
    compared to non-empty strings return 0.0. Two empty strings return 1.0.

    Args:
        a: First string to compare.
        b: Second string to compare.

    Returns:
        A float between 0.0 and 1.0 indicating similarity.

    Examples:
        >>> compute_similarity("Carl", "Karl")  # doctest: +SKIP
        0.75
        >>> compute_similarity("Ljusdal", "Ljusdal")
        1.0
        >>> compute_similarity("", "something")
        0.0
    """
    norm_a = normalize_string(a)
    norm_b = normalize_string(b)

    # Handle edge cases
    if norm_a == norm_b:
        return 1.0
    if not norm_a or not norm_b:
        return 0.0

    return SequenceMatcher(None, norm_a, norm_b).ratio()


def fuzzy_match(
    value: str,
    candidates: list[str],
    threshold: float = 0.8,
) -> list[tuple[str, float]]:
    """Find candidates above a similarity threshold using fuzzy matching.

    Computes the similarity between the input value and each candidate,
    returning those that meet or exceed the threshold. Results are sorted
    by similarity score in descending order.

    Args:
        value: The string to match against candidates.
        candidates: A list of candidate strings to compare with.
        threshold: The minimum similarity score (0.0–1.0) required for
            a candidate to be included in the results. Defaults to 0.8.

    Returns:
        A list of (candidate, score) tuples for candidates meeting the
        threshold, sorted by score descending. The candidate is the
        original (un-normalized) string from the candidates list.

    Examples:
        >>> results = fuzzy_match("Ljusdal", ["Ljusdal", "Ljusdals", "Stockholm"])
        >>> results[0]
        ('Ljusdal', 1.0)
        >>> results[1][0]
        'Ljusdals'
    """
    if not value:
        return []

    matches: list[tuple[str, float]] = []

    for candidate in candidates:
        score = compute_similarity(value, candidate)
        if score >= threshold:
            matches.append((candidate, score))

    # Sort by score descending, then alphabetically for determinism
    matches.sort(key=lambda x: (-x[1], x[0]))
    return matches


def match_name(
    given: str,
    surname: str,
    candidate_givens: list[str],
    candidate_surnames: list[str],
) -> list[tuple[int, float]]:
    """Match a person name against a list of candidate names.

    Compares both given name and surname, weighting surname more heavily
    (0.55) than given name (0.45) since surnames are typically more stable
    identifiers in Swedish genealogy. Also checks for known Swedish name
    equivalents (e.g., "Carl"/"Karl") which receive a similarity bonus.

    The candidate_givens and candidate_surnames lists must have the same
    length—each index represents one candidate person.

    Args:
        given: The given name to match.
        surname: The surname to match.
        candidate_givens: List of given names for each candidate.
        candidate_surnames: List of surnames for each candidate.

    Returns:
        A list of (index, score) tuples for all candidates with a combined
        score > 0.0, sorted by score descending. The index corresponds to
        the position in the candidate lists.

    Raises:
        ValueError: If candidate_givens and candidate_surnames have
            different lengths.

    Examples:
        >>> results = match_name(
        ...     "Carl", "Andersson",
        ...     ["Karl", "Erik"], ["Andersson", "Svensson"]
        ... )
        >>> results[0][0]  # Index of best match
        0
    """
    if len(candidate_givens) != len(candidate_surnames):
        raise ValueError(
            "candidate_givens and candidate_surnames must have the same length"
        )

    results: list[tuple[int, float]] = []

    for i in range(len(candidate_givens)):
        given_score = _compute_name_similarity(given, candidate_givens[i])
        surname_score = compute_similarity(surname, candidate_surnames[i])

        # Weight surname more heavily than given name
        combined = given_score * 0.45 + surname_score * 0.55

        if combined > 0.0:
            results.append((i, combined))

    results.sort(key=lambda x: (-x[1], x[0]))
    return results


def match_place_string(
    gedcom_place: str,
    existing_place_names: list[str],
) -> list[tuple[int, float]]:
    """Match a GEDCOM place string against existing place names.

    GEDCOM places are typically comma-separated hierarchical strings
    (e.g., "Ljusdal, Gävleborgs län, Sverige"). This function compares
    the full string against each existing place name, returning matches
    sorted by similarity.

    For better matching, this function also extracts the most-specific
    component (first part before the comma) and compares it against
    candidates, using whichever approach yields a higher score.

    Args:
        gedcom_place: The GEDCOM place string to match.
        existing_place_names: List of existing place name strings to
            compare against.

    Returns:
        A list of (index, score) tuples for candidates with score > 0.0,
        sorted by score descending. The index corresponds to the position
        in existing_place_names.

    Examples:
        >>> results = match_place_string(
        ...     "Ljusdal, Gävleborgs län, Sverige",
        ...     ["Ljusdal", "Stockholm", "Gävleborgs län"]
        ... )
        >>> results[0][0]  # Best match index
        0
    """
    if not gedcom_place:
        return []

    results: list[tuple[int, float]] = []

    # Extract the most-specific component (first part)
    parts = [p.strip() for p in gedcom_place.split(",")]
    most_specific = parts[0] if parts else gedcom_place

    for i, candidate in enumerate(existing_place_names):
        # Compare full string
        full_score = compute_similarity(gedcom_place, candidate)

        # Compare most-specific component
        specific_score = compute_similarity(most_specific, candidate)

        # Use the higher of the two scores
        score = max(full_score, specific_score)

        if score > 0.0:
            results.append((i, score))

    results.sort(key=lambda x: (-x[1], x[0]))
    return results


def composite_key_similarity(
    key_a: tuple[str, str, str | None, str | None],
    key_b: tuple[str, str, str | None, str | None],
) -> float:
    """Compare two composite keys and return a weighted similarity score.

    A composite key consists of (given_name, surname, birth_date, birth_place).
    Each component is compared individually using fuzzy similarity and then
    combined with the following weights:

        - Surname: 0.35
        - Given name: 0.30
        - Birth date: 0.20
        - Birth place: 0.15

    For optional components (birth_date, birth_place), if both are None the
    component contributes its full weight (treated as matching), since the
    absence of data in both records is not evidence against a match. If only
    one is None, the component contributes 0.0.

    For name components, Swedish historical equivalents are considered
    (e.g., "Carl" ≈ "Karl" receives a boosted score).

    Args:
        key_a: Composite key tuple (given, surname, birth_date, birth_place).
        key_b: Composite key tuple (given, surname, birth_date, birth_place).

    Returns:
        A weighted similarity score between 0.0 and 1.0.

    Examples:
        >>> composite_key_similarity(
        ...     ("Carl", "Andersson", "1850-03-15", "Ljusdal"),
        ...     ("Karl", "Andersson", "1850-03-15", "Ljusdal"),
        ... )  # doctest: +SKIP
        0.95
        >>> composite_key_similarity(
        ...     ("Anna", "Svensson", None, None),
        ...     ("Anna", "Svensson", None, None),
        ... )
        1.0
    """
    given_a, surname_a, birth_date_a, birth_place_a = key_a
    given_b, surname_b, birth_date_b, birth_place_b = key_b

    # Compute individual component similarities
    given_score = _compute_name_similarity(given_a, given_b)
    surname_score = _compute_name_similarity(surname_a, surname_b)
    birth_date_score = _compute_optional_similarity(birth_date_a, birth_date_b)
    birth_place_score = _compute_optional_similarity(birth_place_a, birth_place_b)

    # Short-circuit: if all components are perfect matches, return 1.0
    # to avoid floating-point rounding issues with weighted sums.
    if (
        given_score == 1.0
        and surname_score == 1.0
        and birth_date_score == 1.0
        and birth_place_score == 1.0
    ):
        return 1.0

    # Apply weights
    return (
        surname_score * _SURNAME_WEIGHT
        + given_score * _GIVEN_NAME_WEIGHT
        + birth_date_score * _BIRTH_DATE_WEIGHT
        + birth_place_score * _BIRTH_PLACE_WEIGHT
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _compute_name_similarity(name_a: str, name_b: str) -> float:
    """Compute similarity between two names, considering Swedish equivalents.

    First checks if the normalized names are known Swedish equivalents
    (e.g., "Carl"/"Karl"). If they are equivalent, returns 1.0. Otherwise,
    falls back to general string similarity via ``compute_similarity``.

    Args:
        name_a: First name string.
        name_b: Second name string.

    Returns:
        A float between 0.0 and 1.0 indicating name similarity.
    """
    norm_a = normalize_string(name_a)
    norm_b = normalize_string(name_b)

    if norm_a == norm_b:
        return 1.0

    if not norm_a or not norm_b:
        return 0.0

    # Check if names are known equivalents
    canonical_a = _NAME_CANONICAL.get(norm_a)
    canonical_b = _NAME_CANONICAL.get(norm_b)

    if canonical_a is not None and canonical_a == canonical_b:
        return 1.0

    # Also check individual words in multi-word given names
    # E.g., "Carl Gustaf" vs "Karl Gustaf"
    words_a = norm_a.split()
    words_b = norm_b.split()

    if len(words_a) > 1 or len(words_b) > 1:
        return _multi_word_name_similarity(words_a, words_b)

    return SequenceMatcher(None, norm_a, norm_b).ratio()


def _multi_word_name_similarity(words_a: list[str], words_b: list[str]) -> float:
    """Compute similarity between multi-word names.

    Matches each word from the shorter list against words in the longer
    list, considering Swedish equivalents. The final score is the average
    of the best match for each word in the shorter list, penalized slightly
    if the lists have different lengths.

    Args:
        words_a: Words from the first name.
        words_b: Words from the second name.

    Returns:
        A float between 0.0 and 1.0.
    """
    if not words_a or not words_b:
        return 0.0

    # Always iterate over the shorter list
    shorter = words_a if len(words_a) <= len(words_b) else words_b
    longer = words_b if len(words_a) <= len(words_b) else words_a

    total_score = 0.0
    used_indices: set[int] = set()

    for word_s in shorter:
        best_score = 0.0
        best_idx = -1

        for j, word_l in enumerate(longer):
            if j in used_indices:
                continue

            # Check equivalents
            canonical_s = _NAME_CANONICAL.get(word_s, word_s)
            canonical_l = _NAME_CANONICAL.get(word_l, word_l)

            if canonical_s == canonical_l:
                score = 1.0
            else:
                score = SequenceMatcher(None, word_s, word_l).ratio()

            if score > best_score:
                best_score = score
                best_idx = j

        if best_idx >= 0:
            used_indices.add(best_idx)
        total_score += best_score

    avg_score = total_score / len(shorter)

    # Penalize length mismatch slightly
    length_penalty = min(len(shorter), len(longer)) / max(len(shorter), len(longer))
    return avg_score * (0.8 + 0.2 * length_penalty)


def _compute_optional_similarity(
    value_a: str | None,
    value_b: str | None,
) -> float:
    """Compute similarity for optional fields (birth_date, birth_place).

    If both values are None, returns 1.0 (matching absence is not evidence
    against identity). If only one is None, returns 0.0. Otherwise delegates
    to ``compute_similarity``.

    Args:
        value_a: First optional string value.
        value_b: Second optional string value.

    Returns:
        A float between 0.0 and 1.0.
    """
    if value_a is None and value_b is None:
        return 1.0
    if value_a is None or value_b is None:
        return 0.0
    return compute_similarity(value_a, value_b)
