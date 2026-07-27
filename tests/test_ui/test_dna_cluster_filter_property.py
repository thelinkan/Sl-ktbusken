# Feature: dna-cluster-enhancements, Property 5: Cluster DNA match filter correctness
"""Property-based tests for cluster DNA match filter correctness.

Feature: dna-cluster-enhancements, Property 5: Cluster DNA match filter correctness

For any cluster containing persons, and any person P within that cluster who has
at least one DnaProfile, filtering the cluster's person list on P's DNA matches
SHALL return only persons who have at least one DnaMatch linking one of their
profiles to one of P's profiles.

**Validates: Requirements 9.3, 9.4**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.dna import DnaMatch, DnaProfile
from slaktbusken.services.cluster_filter import get_dna_match_filtered_persons


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_person_id_strategy = st.integers(min_value=1, max_value=200).map(
    lambda n: f"person_{n}"
)

_profile_id_strategy = st.integers(min_value=1, max_value=500).map(
    lambda n: f"dnaprofile_{n}"
)

_company_id_strategy = st.just("dnacompany_1")

_TEST_TYPES = ["autosomal", "y-dna", "mtdna", "combined"]


@st.composite
def cluster_with_profiles_and_matches(
    draw: DrawFn,
) -> tuple[str, list[str], list[DnaProfile], list[DnaMatch]]:
    """Generate a cluster scenario with persons, profiles, and matches.

    Returns:
        A tuple of (person_id_P, cluster_person_ids, profiles, matches) where:
        - person_id_P is the person we filter on (has at least one profile)
        - cluster_person_ids contains person_id_P and other persons
        - profiles contains at least one profile for person_id_P
        - matches may or may not link profiles between persons
    """
    # Generate cluster persons (at least 2, one of which is P)
    num_persons = draw(st.integers(min_value=2, max_value=8))
    cluster_person_ids = [f"person_{i}" for i in range(1, num_persons + 1)]

    # Pick P from the cluster
    person_p = draw(st.sampled_from(cluster_person_ids))

    # Generate profiles: ensure P has at least one
    profiles: list[DnaProfile] = []
    profile_counter = 1

    # P's profiles (at least 1)
    num_p_profiles = draw(st.integers(min_value=1, max_value=3))
    for _ in range(num_p_profiles):
        profiles.append(DnaProfile(
            id=f"dnaprofile_{profile_counter}",
            person_id=person_p,
            company_id="dnacompany_1",
            test_type=draw(st.sampled_from(_TEST_TYPES)),
        ))
        profile_counter += 1

    # Other persons' profiles (0–2 each)
    for pid in cluster_person_ids:
        if pid == person_p:
            continue
        num_profiles = draw(st.integers(min_value=0, max_value=2))
        for _ in range(num_profiles):
            profiles.append(DnaProfile(
                id=f"dnaprofile_{profile_counter}",
                person_id=pid,
                company_id="dnacompany_1",
                test_type=draw(st.sampled_from(_TEST_TYPES)),
            ))
            profile_counter += 1

    # Generate matches between profiles
    # Only create matches between existing profile IDs
    all_profile_ids = [p.id for p in profiles]
    p_profile_ids = [p.id for p in profiles if p.person_id == person_p]

    num_matches = draw(st.integers(min_value=0, max_value=6))
    matches: list[DnaMatch] = []
    for i in range(num_matches):
        if len(all_profile_ids) < 2:
            break
        # Pick two distinct profiles for the match
        prof1 = draw(st.sampled_from(all_profile_ids))
        prof2 = draw(st.sampled_from(
            [pid for pid in all_profile_ids if pid != prof1]
        ) if len(all_profile_ids) > 1 else st.just(prof1))
        if prof1 == prof2:
            continue
        matches.append(DnaMatch(
            id=f"dnamatch_{i + 1}",
            profile1_id=prof1,
            profile2_id=prof2,
            shared_cm=draw(st.floats(min_value=1.0, max_value=3500.0, allow_nan=False)),
        ))

    return (person_p, cluster_person_ids, profiles, matches)


class TestClusterDnaMatchFilterCorrectness:
    """Feature: dna-cluster-enhancements, Property 5: Cluster DNA match filter correctness

    For any cluster containing persons, and any person P within that cluster who
    has at least one DnaProfile, filtering the cluster's person list on P's DNA
    matches SHALL return only persons who have at least one DnaMatch linking one
    of their profiles to one of P's profiles.

    **Validates: Requirements 9.3, 9.4**
    """

    @given(data=cluster_with_profiles_and_matches())
    @settings(max_examples=100)
    def test_filter_returns_only_persons_with_dna_match_to_p(
        self,
        data: tuple[str, list[str], list[DnaProfile], list[DnaMatch]],
    ) -> None:
        """Every returned person_id has at least one DnaMatch linking their
        profile to one of P's profiles, and every person NOT in the result
        has no such match.

        Feature: dna-cluster-enhancements, Property 5: Cluster DNA match filter correctness
        **Validates: Requirements 9.3, 9.4**
        """
        person_p, cluster_person_ids, profiles, matches = data

        result = get_dna_match_filtered_persons(
            person_id=person_p,
            cluster_person_ids=cluster_person_ids,
            profiles=profiles,
            matches=matches,
        )

        # Compute P's profile IDs
        p_profile_ids = {p.id for p in profiles if p.person_id == person_p}

        # Build expected set: persons in the cluster (excluding P) who have
        # at least one DnaMatch linking one of their profiles to P's profiles
        expected = set()
        for pid in cluster_person_ids:
            if pid == person_p:
                continue
            pid_profile_ids = {p.id for p in profiles if p.person_id == pid}
            if not pid_profile_ids:
                continue
            # Check if any match links pid's profiles with P's profiles
            for match in matches:
                link_p_to_other = (
                    match.profile1_id in p_profile_ids
                    and match.profile2_id in pid_profile_ids
                )
                link_other_to_p = (
                    match.profile1_id in pid_profile_ids
                    and match.profile2_id in p_profile_ids
                )
                if link_p_to_other or link_other_to_p:
                    expected.add(pid)
                    break

        # Assert: result set equals expected set
        result_set = set(result)
        assert result_set == expected, (
            f"Filter result mismatch.\n"
            f"  Person P: {person_p}\n"
            f"  P's profiles: {p_profile_ids}\n"
            f"  Result: {result_set}\n"
            f"  Expected: {expected}\n"
            f"  Difference (extra): {result_set - expected}\n"
            f"  Difference (missing): {expected - result_set}"
        )

    @given(data=cluster_with_profiles_and_matches())
    @settings(max_examples=100)
    def test_filter_result_is_subset_of_cluster(
        self,
        data: tuple[str, list[str], list[DnaProfile], list[DnaMatch]],
    ) -> None:
        """Every returned person_id SHALL be in cluster_person_ids.

        Feature: dna-cluster-enhancements, Property 5: Cluster DNA match filter correctness
        **Validates: Requirements 9.3, 9.4**
        """
        person_p, cluster_person_ids, profiles, matches = data

        result = get_dna_match_filtered_persons(
            person_id=person_p,
            cluster_person_ids=cluster_person_ids,
            profiles=profiles,
            matches=matches,
        )

        cluster_set = set(cluster_person_ids)
        for pid in result:
            assert pid in cluster_set, (
                f"Returned person_id {pid} is NOT in cluster_person_ids."
            )

    @given(data=cluster_with_profiles_and_matches())
    @settings(max_examples=100)
    def test_filter_excludes_person_p_from_result(
        self,
        data: tuple[str, list[str], list[DnaProfile], list[DnaMatch]],
    ) -> None:
        """Person P SHALL NOT appear in the filtered result (filtering on
        their own matches should not include themselves).

        Feature: dna-cluster-enhancements, Property 5: Cluster DNA match filter correctness
        **Validates: Requirements 9.3, 9.4**
        """
        person_p, cluster_person_ids, profiles, matches = data

        result = get_dna_match_filtered_persons(
            person_id=person_p,
            cluster_person_ids=cluster_person_ids,
            profiles=profiles,
            matches=matches,
        )

        assert person_p not in result, (
            f"Person P ({person_p}) should NOT be in the filtered result."
        )

    @given(data=cluster_with_profiles_and_matches())
    @settings(max_examples=100)
    def test_no_profiles_no_matches_returns_empty(
        self,
        data: tuple[str, list[str], list[DnaProfile], list[DnaMatch]],
    ) -> None:
        """When P has profiles but no matches exist linking them to others,
        the result SHALL be empty.

        Feature: dna-cluster-enhancements, Property 5: Cluster DNA match filter correctness
        **Validates: Requirements 9.3, 9.4**
        """
        person_p, cluster_person_ids, profiles, _matches = data

        # Use empty matches to test the edge case
        result = get_dna_match_filtered_persons(
            person_id=person_p,
            cluster_person_ids=cluster_person_ids,
            profiles=profiles,
            matches=[],
        )

        assert result == [], (
            f"With no matches, expected empty result but got: {result}"
        )

    @given(data=cluster_with_profiles_and_matches())
    @settings(max_examples=100)
    def test_filter_preserves_cluster_order(
        self,
        data: tuple[str, list[str], list[DnaProfile], list[DnaMatch]],
    ) -> None:
        """The result SHALL preserve the order of cluster_person_ids.

        Feature: dna-cluster-enhancements, Property 5: Cluster DNA match filter correctness
        **Validates: Requirements 9.3, 9.4**
        """
        person_p, cluster_person_ids, profiles, matches = data

        result = get_dna_match_filtered_persons(
            person_id=person_p,
            cluster_person_ids=cluster_person_ids,
            profiles=profiles,
            matches=matches,
        )

        # Check that result maintains relative order from cluster_person_ids
        result_indices = []
        for pid in result:
            idx = cluster_person_ids.index(pid)
            result_indices.append(idx)

        assert result_indices == sorted(result_indices), (
            f"Result does not preserve cluster order.\n"
            f"  cluster_person_ids: {cluster_person_ids}\n"
            f"  result: {result}\n"
            f"  result_indices: {result_indices}"
        )
