"""Property-based tests for Swedish kinship term assignment.

Property 9: For any valid RelationshipPath with known generation counts,
the kinship term assignment produces the correct Swedish term.

**Validates: Requirements 15.5**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.relationship.kinship_terms import SwedishKinshipTerms


# ---------------------------------------------------------------------------
# Property Test (Property 9): Correct Swedish terms for known generation counts
# **Validates: Requirements 15.5**
# ---------------------------------------------------------------------------


@given(sex=st.sampled_from(["M", "F"]))
@settings(max_examples=20, deadline=None)
def test_property_parent_term(sex: str):
    """Parent (gen_a=1, gen_b=0) produces 'far' or 'mor'.

    **Validates: Requirements 15.5**
    """
    terms = SwedishKinshipTerms()
    result = terms.get_term(
        generations_a=1, generations_b=0, sex_of_relative=sex
    )
    if sex == "M":
        assert result == "far"
    else:
        assert result == "mor"


@given(sex=st.sampled_from(["M", "F"]))
@settings(max_examples=20, deadline=None)
def test_property_child_term(sex: str):
    """Child (gen_a=0, gen_b=1) produces 'son' or 'dotter'.

    **Validates: Requirements 15.5**
    """
    terms = SwedishKinshipTerms()
    result = terms.get_term(
        generations_a=0, generations_b=1, sex_of_relative=sex
    )
    if sex == "M":
        assert result == "son"
    else:
        assert result == "dotter"


@given(sex=st.sampled_from(["M", "F", "X"]))
@settings(max_examples=20, deadline=None)
def test_property_sibling_term(sex: str):
    """Sibling (gen_a=1, gen_b=1) produces 'bror', 'syster', or 'syskon'.

    **Validates: Requirements 15.5**
    """
    terms = SwedishKinshipTerms()
    result = terms.get_term(
        generations_a=1, generations_b=1, sex_of_relative=sex
    )
    if sex == "M":
        assert result == "bror"
    elif sex == "F":
        assert result == "syster"
    else:
        assert result == "syskon"


@given(sex=st.sampled_from(["M", "F"]))
@settings(max_examples=20, deadline=None)
def test_property_uncle_aunt_term(sex: str):
    """Uncle/aunt (gen_a=2, gen_b=1) produces correct term.

    **Validates: Requirements 15.5**
    """
    terms = SwedishKinshipTerms()
    result = terms.get_term(
        generations_a=2, generations_b=1, sex_of_relative=sex
    )
    if sex == "M":
        assert result == "farbror/morbror"
    else:
        assert result == "faster/moster"


@given(degree=st.integers(min_value=2, max_value=10))
@settings(max_examples=30, deadline=None)
def test_property_cousin_degree_symmetry(degree: int):
    """Cousins (gen_a=degree, gen_b=degree) produce correct männing term.

    **Validates: Requirements 15.5**
    """
    terms = SwedishKinshipTerms()
    result = terms.get_term(
        generations_a=degree, generations_b=degree, sex_of_relative="M"
    )

    expected_terms = {
        2: "kusin",
        3: "tremänning",
        4: "fyrmänning",
        5: "femmänning",
        6: "sexmänning",
        7: "sjumänning",
        8: "åttamänning",
        9: "niomänning",
        10: "tiomänning",
    }
    assert result == expected_terms[degree]


@given(
    degree=st.integers(min_value=2, max_value=8),
    removal=st.integers(min_value=1, max_value=5),
)
@settings(max_examples=50, deadline=None)
def test_property_removed_cousin_format(degree: int, removal: int):
    """Removed cousins produce 'X, Y släktled bort' format.

    **Validates: Requirements 15.5**
    """
    terms = SwedishKinshipTerms()
    # gen_a = degree, gen_b = degree + removal
    result = terms.get_term(
        generations_a=degree,
        generations_b=degree + removal,
        sex_of_relative="M",
    )

    # Should contain "släktled bort"
    assert "släktled bort" in result

    # Should start with the cousin degree term
    base_terms = {
        2: "kusin",
        3: "tremänning",
        4: "fyrmänning",
        5: "femmänning",
        6: "sexmänning",
        7: "sjumänning",
        8: "åttamänning",
    }
    expected_base = base_terms[degree]
    assert result.startswith(expected_base + ",")


@given(
    generations=st.integers(min_value=1, max_value=10),
    sex=st.sampled_from(["M", "F"]),
)
@settings(max_examples=30, deadline=None)
def test_property_ancestor_terms_are_nonempty(generations: int, sex: str):
    """All ancestor terms are non-empty strings.

    **Validates: Requirements 15.5**
    """
    terms = SwedishKinshipTerms()
    result = terms.get_term(
        generations_a=generations, generations_b=0, sex_of_relative=sex
    )
    assert len(result) > 0
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Foster kinship terms (Task 8.2)
# **Validates: Requirements 9.2, 9.4**
# ---------------------------------------------------------------------------


def test_foster_immediate_parent_male():
    """Immediate foster father (gen_a=1, gen_b=0, M) => 'fosterfar'.

    **Validates: Requirements 9.2**
    """
    terms = SwedishKinshipTerms()
    result = terms.get_term(
        generations_a=1,
        generations_b=0,
        sex_of_relative="M",
        relationship_type="foster",
    )
    assert result == "fosterfar"


def test_foster_immediate_parent_female():
    """Immediate foster mother (gen_a=1, gen_b=0, F) => 'fostermor'.

    **Validates: Requirements 9.2**
    """
    terms = SwedishKinshipTerms()
    result = terms.get_term(
        generations_a=1,
        generations_b=0,
        sex_of_relative="F",
        relationship_type="foster",
    )
    assert result == "fostermor"


def test_foster_immediate_parent_unknown_sex():
    """Immediate foster parent with unknown sex => 'fosterförälder'.

    **Validates: Requirements 9.2**
    """
    terms = SwedishKinshipTerms()
    result = terms.get_term(
        generations_a=1,
        generations_b=0,
        sex_of_relative="X",
        relationship_type="foster",
    )
    assert result == "fosterförälder"


@given(sex=st.sampled_from(["M", "F"]))
@settings(max_examples=10, deadline=None)
def test_foster_immediate_child(sex: str):
    """Immediate foster child (gen_a=0, gen_b=1) => 'fosterbarn'.

    **Validates: Requirements 9.2**
    """
    terms = SwedishKinshipTerms()
    result = terms.get_term(
        generations_a=0,
        generations_b=1,
        sex_of_relative=sex,
        relationship_type="foster",
    )
    assert result == "fosterbarn"


def test_foster_distant_sibling_prefixed():
    """A foster sibling (gen_a=1, gen_b=1, M) yields a foster-prefixed term.

    The natural closed form 'fosterbror' is used, which still starts with
    'foster' and contains the base 'bror'.

    **Validates: Requirements 9.2**
    """
    terms = SwedishKinshipTerms()
    result = terms.get_term(
        generations_a=1,
        generations_b=1,
        sex_of_relative="M",
        relationship_type="foster",
    )
    assert result.startswith("foster")
    assert "bror" in result


def test_foster_uncle_hyphen_prefixed():
    """A foster uncle (gen_a=2, gen_b=1) gets the hyphenated 'foster-' prefix.

    **Validates: Requirements 9.2**
    """
    terms = SwedishKinshipTerms()
    result = terms.get_term(
        generations_a=2,
        generations_b=1,
        sex_of_relative="M",
        relationship_type="foster",
    )
    assert result.startswith("foster-")
    assert "farbror/morbror" in result


# ---------------------------------------------------------------------------
# Regression: adoption/legal unchanged, blood unchanged (Req 9.4)
# ---------------------------------------------------------------------------


@given(
    generations_a=st.integers(min_value=0, max_value=5),
    generations_b=st.integers(min_value=0, max_value=5),
    sex=st.sampled_from(["M", "F", "X"]),
)
@settings(max_examples=100, deadline=None)
def test_adoption_matches_blood(generations_a, generations_b, sex):
    """adoption/legal produce the SAME term as blood (adoption unchanged).

    **Validates: Requirements 9.4**
    """
    terms = SwedishKinshipTerms()
    blood = terms.get_term(
        generations_a, generations_b, sex, relationship_type="blood"
    )
    adoption = terms.get_term(
        generations_a, generations_b, sex, relationship_type="adoption"
    )
    legal = terms.get_term(
        generations_a, generations_b, sex, relationship_type="legal"
    )
    assert adoption == blood
    assert legal == blood


def test_blood_parent_unchanged():
    """Blood parent (gen_a=1, gen_b=0, M) is still 'far'.

    **Validates: Requirements 9.4**
    """
    terms = SwedishKinshipTerms()
    assert (
        terms.get_term(1, 0, "M", relationship_type="blood") == "far"
    )
    assert (
        terms.get_term(0, 1, "F", relationship_type="blood") == "dotter"
    )
