"""Unit tests and property-based tests for the IDGenerator."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model import IDGenerator


def test_type_prefixed_format():
    gen = IDGenerator(set())
    assert gen.generate("person") == "person_1"
    assert gen.generate("family") == "family_1"
    assert gen.generate("event") == "event_1"
    assert gen.generate("repository") == "repo_1"
    assert gen.generate("research_note") == "note_1"
    assert gen.generate("dna_triangulation") == "dna_triangulation_1"


def test_monotonic_increment_per_type():
    gen = IDGenerator(set())
    assert gen.generate("person") == "person_1"
    assert gen.generate("person") == "person_2"
    assert gen.generate("person") == "person_3"
    # Different type maintains its own counter.
    assert gen.generate("place") == "place_1"
    assert gen.generate("person") == "person_4"


def test_initialization_from_existing_ids_high_water_mark():
    gen = IDGenerator({"person_5"})
    assert gen.generate("person") == "person_6"


def test_high_water_mark_uses_max_not_count():
    # Set size is 2 but highest suffix is 10, so next must be 11.
    gen = IDGenerator({"person_3", "person_10"})
    assert gen.generate("person") == "person_11"


def test_non_reuse_after_conceptual_delete():
    gen = IDGenerator(set())
    first = gen.generate("person")  # person_1
    second = gen.generate("person")  # person_2
    assert first == "person_1"
    assert second == "person_2"
    # Even though person_2 is "deleted" externally, the generator retains it
    # in its used set and the counter never decreases.
    third = gen.generate("person")
    assert third == "person_3"
    assert third not in {first, second}


def test_register_external_id_prevents_reuse():
    gen = IDGenerator(set())
    gen.register("person_7")
    assert gen.generate("person") == "person_8"


def test_unknown_entity_type_raises_value_error():
    gen = IDGenerator(set())
    with pytest.raises(ValueError):
        gen.generate("unicorn")


def test_dna_prefixes_do_not_collide():
    gen = IDGenerator({"dna_company_2"})
    # dna_company_ and dna_cluster_ share the dna_ stem but are distinct.
    assert gen.generate("dna_company") == "dna_company_3"
    assert gen.generate("dna_cluster") == "dna_cluster_1"


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# ---------------------------------------------------------------------------

ENTITY_TYPES = list(IDGenerator._PREFIXES.keys())


class TestPropertyIDGeneration:
    """Property-based tests for IDGenerator.

    **Validates: Requirements 24.1, 24.2, 24.3**
    """

    @given(entity_types=st.lists(st.sampled_from(ENTITY_TYPES), min_size=1, max_size=100))
    @settings(max_examples=100)
    def test_all_generated_ids_are_unique(self, entity_types: list[str]) -> None:
        """For any sequence of generate() calls, all returned IDs are unique."""
        gen = IDGenerator(set())
        ids = [gen.generate(t) for t in entity_types]
        assert len(ids) == len(set(ids))

    @given(entity_type=st.sampled_from(ENTITY_TYPES), count=st.integers(min_value=1, max_value=20))
    @settings(max_examples=100)
    def test_generated_ids_carry_correct_prefix(self, entity_type: str, count: int) -> None:
        """For any entity_type, the generated ID starts with the correct prefix."""
        gen = IDGenerator(set())
        prefix = IDGenerator._PREFIXES[entity_type]
        for _ in range(count):
            generated = gen.generate(entity_type)
            assert generated.startswith(prefix)
            # The part after the prefix should be a positive integer
            suffix = generated[len(prefix):]
            assert suffix.isdigit()
            assert int(suffix) > 0

    @given(
        entity_type=st.sampled_from(ENTITY_TYPES),
        existing_count=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=100)
    def test_deleted_ids_never_reused(self, entity_type: str, existing_count: int) -> None:
        """Given pre-existing IDs, no subsequent generate() returns any of those IDs."""
        prefix = IDGenerator._PREFIXES[entity_type]
        existing = {f"{prefix}{i}" for i in range(1, existing_count + 1)}
        gen = IDGenerator(existing)
        # Generate more IDs - none should be in the existing set
        new_ids = [gen.generate(entity_type) for _ in range(existing_count + 5)]
        for new_id in new_ids:
            assert new_id not in existing

    @given(entity_type=st.sampled_from(ENTITY_TYPES), count=st.integers(min_value=2, max_value=20))
    @settings(max_examples=100)
    def test_sequential_ids_have_monotonically_increasing_suffixes(
        self, entity_type: str, count: int
    ) -> None:
        """For a given entity_type, sequential calls produce increasing numeric suffixes."""
        gen = IDGenerator(set())
        prefix = IDGenerator._PREFIXES[entity_type]
        ids = [gen.generate(entity_type) for _ in range(count)]
        suffixes = [int(id_[len(prefix):]) for id_ in ids]
        for i in range(1, len(suffixes)):
            assert suffixes[i] > suffixes[i - 1]
