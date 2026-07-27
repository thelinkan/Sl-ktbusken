"""Pure filter logic for cluster DNA match filtering.

Provides functions to filter cluster persons based on DNA match relationships.
No Qt dependencies — suitable for property-based testing.
"""

from __future__ import annotations

from slaktbusken.model.dna import DnaMatch, DnaProfile


def get_dna_match_filtered_persons(
    person_id: str,
    cluster_person_ids: list[str],
    profiles: list[DnaProfile],
    matches: list[DnaMatch],
) -> list[str]:
    """Filter cluster persons to those with a DNA match to the given person.

    Steps:
    1. Find all profile_ids belonging to person_id
    2. Find all DnaMatches where those profiles appear as profile1_id or profile2_id
    3. Get the other profile_id from each match
    4. Resolve those profiles to person_ids
    5. Filter cluster_person_ids to only those in the resolved set

    Args:
        person_id: The person whose DNA matches we filter on.
        cluster_person_ids: All person_ids in the current cluster.
        profiles: All DnaProfile records in the project.
        matches: All DnaMatch records in the project.

    Returns:
        A list of person_ids from cluster_person_ids that have at least one
        DnaMatch linking one of their profiles to one of person_id's profiles.
        The order follows the order of cluster_person_ids.
    """
    # Step 1: Find all profile_ids belonging to person_id
    person_profile_ids: set[str] = {
        p.id for p in profiles if p.person_id == person_id
    }

    if not person_profile_ids:
        return []

    # Step 2: Find all DnaMatches involving any of person's profiles
    # Step 3: Get the other profile_id from each match
    other_profile_ids: set[str] = set()
    for match in matches:
        if match.profile1_id in person_profile_ids:
            other_profile_ids.add(match.profile2_id)
        elif match.profile2_id in person_profile_ids:
            other_profile_ids.add(match.profile1_id)

    if not other_profile_ids:
        return []

    # Step 4: Resolve those profiles to person_ids
    matched_person_ids: set[str] = {
        p.person_id for p in profiles if p.id in other_profile_ids
    }

    # Step 5: Filter cluster_person_ids to only those in the matched set
    # Exclude the person themselves from the result
    return [
        pid for pid in cluster_person_ids
        if pid in matched_person_ids and pid != person_id
    ]
