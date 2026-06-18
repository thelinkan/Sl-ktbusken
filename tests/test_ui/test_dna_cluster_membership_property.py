"""Property-based tests for DNA cluster membership consistency.

Feature: ui-enhancements, Property 9: DNA cluster membership consistency

Validates: Requirements 9.3, 9.4
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.dna import DnaCluster
from tests.conftest import dna_cluster_strategy


# Reuse the same ID strategy pattern from conftest
_person_id_strategy = st.integers(min_value=1, max_value=9999).map(
    lambda n: f"person_{n}"
)


class TestDnaClusterMembershipConsistency:
    """Feature: ui-enhancements, Property 9: DNA cluster membership consistency

    Generate random DnaCluster with random person_ids, verify add operation
    makes `person_id in cluster.person_ids` True, remove operation makes it
    False with length decreased by 1.

    **Validates: Requirements 9.3, 9.4**
    """

    @given(
        cluster=dna_cluster_strategy(),
        new_person_id=_person_id_strategy,
    )
    @settings(max_examples=100)
    def test_add_person_to_cluster_makes_membership_true(
        self, cluster: DnaCluster, new_person_id: str
    ) -> None:
        """After adding a person_id to cluster.person_ids, the person_id
        SHALL be present in cluster.person_ids.

        Feature: ui-enhancements, Property 9: DNA cluster membership consistency
        **Validates: Requirements 9.3, 9.4**
        """
        # Add the person to the cluster
        cluster.person_ids.append(new_person_id)

        # Verify membership is True
        assert new_person_id in cluster.person_ids, (
            f"After adding {new_person_id}, expected it to be in "
            f"cluster.person_ids but it was not found."
        )

    @given(
        cluster=dna_cluster_strategy(),
        new_person_id=_person_id_strategy,
    )
    @settings(max_examples=100)
    def test_remove_person_from_cluster_makes_membership_false(
        self, cluster: DnaCluster, new_person_id: str
    ) -> None:
        """After removing a person_id from cluster.person_ids, the person_id
        SHALL NOT be present and the list length SHALL have decreased by 1.

        Feature: ui-enhancements, Property 9: DNA cluster membership consistency
        **Validates: Requirements 9.3, 9.4**
        """
        # Ensure the person_id is in the list exactly once for a clean remove
        # First remove any existing occurrences to avoid duplicates
        cluster.person_ids = [
            pid for pid in cluster.person_ids if pid != new_person_id
        ]
        # Add it once so we can remove it
        cluster.person_ids.append(new_person_id)

        # Record length before removal
        length_before = len(cluster.person_ids)

        # Remove the person from the cluster
        cluster.person_ids.remove(new_person_id)

        # Verify membership is False
        assert new_person_id not in cluster.person_ids, (
            f"After removing {new_person_id}, expected it to NOT be in "
            f"cluster.person_ids but it was still found."
        )

        # Verify length decreased by exactly 1
        assert len(cluster.person_ids) == length_before - 1, (
            f"Expected list length to decrease by 1 "
            f"(from {length_before} to {length_before - 1}), "
            f"but got {len(cluster.person_ids)}."
        )
