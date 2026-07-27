"""Property-based tests for the Type Dropdown builder.

Tests Properties 6 and 7 from the place-hierarchy-levels design document.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.place import Place, RegionLevel
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.editors.place_editor import build_type_options


# ---------------------------------------------------------------------------
# Strategies for Property 6
# ---------------------------------------------------------------------------


@st.composite
def _project_with_countries(draw: DrawFn) -> ProjectData:
    """Generate a ProjectData with 0-3 country places having region_levels."""
    count = draw(st.integers(min_value=0, max_value=3))
    places: list[Place] = []
    for i in range(count):
        num_levels = draw(st.integers(min_value=1, max_value=3))
        keys = draw(
            st.lists(
                st.text(
                    alphabet=st.characters(categories=("L", "N")),
                    min_size=1,
                    max_size=20,
                ),
                min_size=num_levels,
                max_size=num_levels,
                unique=True,
            )
        )
        levels: list[RegionLevel] = []
        for j, key in enumerate(keys):
            label = draw(
                st.text(
                    alphabet=st.characters(categories=("L", "N", "Z")),
                    min_size=1,
                    max_size=50,
                )
            )
            levels.append(RegionLevel(key=key, label=label, order=j + 1))
        places.append(
            Place(
                id=f"country_{i}",
                type="country",
                name=f"Country {i}",
                parent_place_id="continent_1",
                region_levels=levels,
            )
        )
    return ProjectData(
        format="släktbuske-file",
        version="0.1",
        project=ProjectMetadata(title="Test"),
        places=places,
    )


# ---------------------------------------------------------------------------
# Property 6: Type dropdown contains all active region labels
# ---------------------------------------------------------------------------


class TestProperty6TypeDropdownContents:
    """Property 6: Type dropdown contains all active region labels.

    **Validates: Requirements 3.3, 3.4**
    """

    @given(project_data=_project_with_countries())
    @settings(max_examples=100)
    def test_dropdown_contains_exactly_fixed_region_and_universal_labels(
        self, project_data: ProjectData
    ) -> None:
        """The dropdown contains exactly the fixed + region + universal labels."""
        result = build_type_options(project_data)

        expected_fixed = ["Kontinent", "Land"]
        expected_universal = ["Kyrka", "Kyrkogård", "Gård", "Skola", "Ort"]
        expected_region = sorted(
            {
                rl.label
                for p in project_data.places
                if p.type == "country"
                for rl in p.region_levels
            }
        )
        expected = expected_fixed + expected_region + expected_universal
        assert result == expected

    @given(project_data=_project_with_countries())
    @settings(max_examples=100)
    def test_dropdown_always_starts_with_kontinent(
        self, project_data: ProjectData
    ) -> None:
        """The first entry is always Kontinent."""
        result = build_type_options(project_data)
        assert result[0] == "Kontinent"

    def test_empty_project_returns_only_fixed_and_universal(self) -> None:
        """Empty project (no countries) returns only fixed + universal types."""
        project_data = ProjectData(
            format="släktbuske-file",
            version="0.1",
            project=ProjectMetadata(title="Test"),
            places=[],
        )
        result = build_type_options(project_data)
        expected = ["Kontinent", "Land", "Kyrka", "Kyrkogård", "Gård", "Skola", "Ort"]
        assert result == expected


# ---------------------------------------------------------------------------
# Strategies for Property 7
# ---------------------------------------------------------------------------

# Use fixed label pools to avoid slow .filter() calls
_LABEL_POOL_A = ["AlphaRegion", "BetaRegion", "GammaRegion", "DeltaRegion"]
_LABEL_POOL_B = ["EpsilonRegion", "ZetaRegion", "EtaRegion", "ThetaRegion"]


@st.composite
def _project_with_exclusive_labels(draw: DrawFn):
    """Generate a project where one country has at least one exclusive label.

    Country A draws labels from pool A, country B draws from pool B.
    Since the pools are disjoint, all labels from country A are exclusive
    (not shared by country B) and vice versa.
    """
    # Country A with unique labels from pool A
    a_count = draw(st.integers(min_value=1, max_value=2))
    a_labels = draw(st.lists(
        st.sampled_from(_LABEL_POOL_A),
        min_size=a_count,
        max_size=a_count,
        unique=True,
    ))
    a_levels = []
    for i, label in enumerate(a_labels):
        a_levels.append(RegionLevel(key=f"a_key_{i}", label=label, order=i + 1))

    # Country B with labels from pool B (guaranteed disjoint from pool A)
    b_count = draw(st.integers(min_value=1, max_value=2))
    b_labels = draw(st.lists(
        st.sampled_from(_LABEL_POOL_B),
        min_size=b_count,
        max_size=b_count,
        unique=True,
    ))
    b_levels = []
    for i, label in enumerate(b_labels):
        b_levels.append(RegionLevel(key=f"b_key_{i}", label=label, order=i + 1))

    country_a = Place(
        id="country_a",
        type="country",
        name="CountryA",
        parent_place_id="c1",
        region_levels=a_levels,
    )
    country_b = Place(
        id="country_b",
        type="country",
        name="CountryB",
        parent_place_id="c1",
        region_levels=b_levels,
    )

    project = ProjectData(
        format="släktbuske-file",
        version="0.1",
        project=ProjectMetadata(title="Test"),
        places=[country_a, country_b],
    )
    return project, country_a, set(a_labels)


class TestProperty7RemovingCountryRemovesExclusiveLabels:
    """Property 7: Removing a country removes exclusive labels from dropdown.

    **Validates: Requirements 3.5**

    For any project with multiple countries, removing a country SHALL remove
    from the Type_Dropdown all region level labels that are not shared by any
    remaining country.
    """

    @given(data=_project_with_exclusive_labels())
    @settings(max_examples=100)
    def test_removing_country_removes_exclusive_labels(self, data):
        """Removing a country removes its exclusive labels from the dropdown."""
        project, removed_country, exclusive_labels = data

        # Before removal: exclusive labels present
        options_before = build_type_options(project)
        for label in exclusive_labels:
            assert label in options_before, (
                f"Expected exclusive label {label!r} in dropdown before removal, "
                f"got: {options_before}"
            )

        # Remove the country
        project.places = [p for p in project.places if p.id != removed_country.id]

        # After removal: exclusive labels gone
        options_after = build_type_options(project)
        for label in exclusive_labels:
            assert label not in options_after, (
                f"Exclusive label {label!r} should not be in dropdown after "
                f"removing country, got: {options_after}"
            )

    @given(data=_project_with_exclusive_labels())
    @settings(max_examples=100)
    def test_shared_labels_remain_after_removal(self, data):
        """Labels from remaining countries persist after removal."""
        project, removed_country, _exclusive_labels = data

        # Identify labels from the remaining country (country_b)
        remaining_countries = [
            p for p in project.places
            if p.type == "country" and p.id != removed_country.id
        ]
        remaining_labels = set()
        for country in remaining_countries:
            for rl in country.region_levels:
                remaining_labels.add(rl.label)

        # Remove the country
        project.places = [p for p in project.places if p.id != removed_country.id]

        # After removal: remaining country labels still present
        options_after = build_type_options(project)
        for label in remaining_labels:
            assert label in options_after, (
                f"Label {label!r} from remaining country should still be "
                f"in dropdown after removal, got: {options_after}"
            )
