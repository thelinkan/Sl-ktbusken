"""Unit tests for the IDGenerator."""

from __future__ import annotations

import pytest

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
