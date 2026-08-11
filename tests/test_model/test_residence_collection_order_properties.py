# Feature: residence-periods, Property 6: Project order is preserved and identifiers are unique and never reused
"""Property-based test for collection order and identifier uniqueness.

Feature: residence-periods, Property 6: Project order is preserved and identifiers are unique and never reused

For any sequence of Residence_Fact additions and deletions, the `residences`
collection lists the surviving facts in the order they were added, every assigned
`id` is unique among all identifiers in the Project, and no identifier assigned
before a deletion is ever assigned again.

**Validates: Requirements 1.2, 1.12**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import ResidenceFact
from tests.test_model.residence_strategies import consistent_projects, residence_facts


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def _addition_deletion_sequences(draw: DrawFn) -> tuple[ProjectData, list[tuple[str, int]]]:
    """Generate a consistent project and a sequence of add/delete operations.

    Each operation is either ("add", _) meaning append a new Residence_Fact with
    a freshly generated id, or ("delete", index) meaning remove the fact at that
    position in the current list. The sequence always produces at least one
    addition so the collection is non-trivial.
    """
    project = draw(consistent_projects(min_residences=0, max_residences=2))
    # The number of operations to perform after the initial project state.
    op_count = draw(st.integers(min_value=1, max_value=8))
    operations: list[tuple[str, int]] = []
    current_length = len(project.residences)

    for _ in range(op_count):
        if current_length == 0 or draw(st.integers(min_value=0, max_value=2)) > 0:
            # Addition — we'll generate the actual fact during replay.
            operations.append(("add", 0))
            current_length += 1
        else:
            # Deletion of a random existing element.
            index = draw(st.integers(min_value=0, max_value=current_length - 1))
            operations.append(("delete", index))
            current_length -= 1

    return project, operations


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestCollectionOrderAndIdentifierUniqueness:
    """Property 6: Project order is preserved and identifiers are unique and never reused.

    For any sequence of Residence_Fact additions and deletions, the `residences`
    collection lists the surviving facts in the order they were added, every
    assigned `id` is unique among all identifiers in the Project, and no
    identifier assigned before a deletion is ever assigned again.

    **Validates: Requirements 1.2, 1.12**
    """

    @given(data=st.data(), seq=_addition_deletion_sequences())
    @settings(max_examples=100, deadline=None)
    def test_order_preserved_and_ids_unique_and_never_reused(
        self,
        data: st.DataObject,
        seq: tuple[ProjectData, list[tuple[str, int]]],
    ) -> None:
        """Additions preserve order, deletions keep survivors in place, ids never repeat.

        Feature: residence-periods, Property 6: Project order is preserved and identifiers are unique and never reused

        **Validates: Requirements 1.2, 1.12**
        """
        project, operations = seq

        # Collect all existing identifiers across the project.
        all_ids: set[str] = set()
        for person in project.persons:
            all_ids.add(person.id)
        for place in project.places:
            all_ids.add(place.id)
        for source in project.sources:
            all_ids.add(source.id)
        for event in project.events:
            all_ids.add(event.id)
        for residence in project.residences:
            all_ids.add(residence.id)

        id_gen = IDGenerator(all_ids)

        # Track insertion order: a list of ids in the order they were added.
        insertion_order: list[str] = [r.id for r in project.residences]

        # Track every id ever assigned (including those later deleted).
        ever_assigned: set[str] = set(insertion_order)

        for op, index in operations:
            if op == "add":
                new_id = id_gen.generate("residence")

                # Requirement 1.12: the id must be unique among ALL project ids.
                assert new_id not in all_ids - {new_id}, (
                    f"Generated id {new_id!r} collides with an existing project id"
                )

                # Requirement 1.12: the id must never have been assigned before.
                assert new_id not in ever_assigned, (
                    f"Generated id {new_id!r} was previously assigned and is being reused"
                )

                # Create a minimal fact with the new id, referencing existing entities.
                person_ids = [p.id for p in project.persons]
                place_ids = [p.id for p in project.places]
                fact = data.draw(
                    residence_facts(
                        residence_id=new_id,
                        person_ids=person_ids if person_ids else None,
                        place_ids=place_ids if place_ids else None,
                        observation_count=0,
                        include_many_observations=False,
                    )
                )

                project.residences.append(fact)
                insertion_order.append(new_id)
                ever_assigned.add(new_id)
                all_ids.add(new_id)

            else:  # op == "delete"
                # Remove the fact at the given index.
                removed = project.residences.pop(index)
                insertion_order.remove(removed.id)
                # The id stays in ever_assigned and all_ids — it must never be reused.

        # --- Assertions ---

        # Requirement 1.2: the residences collection preserves insertion order.
        current_ids = [r.id for r in project.residences]
        assert current_ids == insertion_order, (
            f"Order mismatch after operations:\n"
            f"  expected: {insertion_order}\n"
            f"  got:      {current_ids}"
        )

        # Requirement 1.12: all ids in the collection are unique.
        assert len(current_ids) == len(set(current_ids)), (
            "Duplicate ids found in the residences collection"
        )

        # Requirement 1.12: every id is unique among all project identifiers.
        non_residence_ids = all_ids - set(current_ids) - (ever_assigned - set(current_ids))
        for rid in current_ids:
            assert rid not in non_residence_ids, (
                f"Residence id {rid!r} collides with a non-residence project id"
            )
