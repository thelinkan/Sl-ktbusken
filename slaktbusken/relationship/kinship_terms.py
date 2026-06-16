"""Swedish kinship term mapping.

Provides correct Swedish kinship terminology based on generational distances
from a common ancestor, the sex of the relative, and the relationship type.

Terminology patterns:
- Direct: far, mor, son, dotter, bror, syster
- Uncle/aunt: farbror, morbror, faster, moster
- Nephew/niece: brorson, brordotter, systerson, systerdotter
- Cousins: kusin (= tvåmänning), tremänning, fyrmänning, femmänning...
- Removed cousins: "X släktled bort" (e.g., "tremänning, ett släktled bort")
- Grand-: farfar, farmor, morfar, mormor (deeper with "gammel-" prefix)
- In-law: svärfar, svärmor, svåger, svägerska
- Partner: "gift med X" for spouse-of-relative
"""

from __future__ import annotations

from typing import Optional


# Blood relationship type constants
_BLOOD_TYPES = {"biological"}


def is_blood_parentage(parentage_type: str) -> bool:
    """Check if a parentage type represents a blood relationship.

    Args:
        parentage_type: The parentage type string.

    Returns:
        True if the parentage type is biological (blood).
    """
    return parentage_type in _BLOOD_TYPES


class SwedishKinshipTerms:
    """Maps generation counts and relationship context to Swedish kinship terms.

    The generation counts (generations_a and generations_b) represent the number
    of steps from each person to their common ancestor. For example:
    - Parent-child: generations_a=0, generations_b=1 (A is ancestor of B)
    - Siblings: generations_a=1, generations_b=1
    - Uncle/aunt: generations_a=2, generations_b=1
    - Cousins: generations_a=2, generations_b=2
    """

    def get_term(
        self,
        generations_a: int,
        generations_b: int,
        sex_of_relative: str,
        relationship_type: str = "blood",
        via_partner: bool = False,
        partner_term_base: Optional[str] = None,
    ) -> str:
        """Get the Swedish kinship term for a relationship.

        Args:
            generations_a: Steps from person A up to common ancestor.
            generations_b: Steps from common ancestor down to person B.
            sex_of_relative: Sex of person B ('M', 'F', 'X', 'U').
            relationship_type: 'blood', 'legal', or 'adoption'.
            via_partner: If True, the relationship goes through a partner link.
            partner_term_base: If via_partner, the base term for the relative
                whose partner we are describing.

        Returns:
            The Swedish kinship term string.
        """
        if via_partner and partner_term_base:
            return self._get_in_law_or_partner_term(
                partner_term_base, sex_of_relative
            )

        # Direct ancestor/descendant line
        if generations_a == 0 and generations_b == 0:
            return "samma person"

        if generations_b == 0:
            # Person B is an ancestor of person A
            return self._get_ancestor_term(generations_a, sex_of_relative)

        if generations_a == 0:
            # Person A is an ancestor of person B
            return self._get_descendant_term(generations_b, sex_of_relative)

        # Siblings (same generation from common ancestor)
        if generations_a == 1 and generations_b == 1:
            return self._get_sibling_term(sex_of_relative)

        # Uncle/aunt: A is 1 gen from ancestor, B is 2+ gens from ancestor
        # Actually: uncle/aunt = gen_a=2, gen_b=1 (B is one step from ancestor,
        # A is two steps) meaning B is A's parent's sibling
        # Wait - let me reconsider the convention:
        # generations_a = steps from A to common ancestor
        # generations_b = steps from B to common ancestor
        # If gen_a=1, gen_b=2: A is child of ancestor, B is grandchild
        #   => B is A's niece/nephew
        # If gen_a=2, gen_b=1: A is grandchild, B is child of ancestor
        #   => B is A's uncle/aunt

        if generations_b == 1 and generations_a >= 2:
            # B is uncle/aunt (or great-uncle etc.) of A
            return self._get_uncle_aunt_term(
                generations_a, sex_of_relative
            )

        if generations_a == 1 and generations_b >= 2:
            # B is nephew/niece (or grand-nephew etc.) of A
            return self._get_nephew_niece_term(
                generations_b, sex_of_relative
            )

        # Cousins: both generations >= 2
        if generations_a >= 2 and generations_b >= 2:
            return self._get_cousin_term(generations_a, generations_b)

        return "släkting"

    def _get_ancestor_term(self, generations: int, sex: str) -> str:
        """Get term for a direct ancestor at given generation distance.

        Args:
            generations: Number of generations up from the person.
            sex: Sex of the ancestor ('M', 'F', 'X', 'U').

        Returns:
            Swedish term for the ancestor.
        """
        if generations == 1:
            return "far" if sex == "M" else "mor"

        if generations == 2:
            # Grandparent - but we don't know the intermediate parent's sex
            # Use generic terms
            if sex == "M":
                return "farfar/morfar"
            else:
                return "farmor/mormor"

        if generations == 3:
            if sex == "M":
                return "gammelfar"
            else:
                return "gammelmor"

        # For deeper ancestors, use "gammel-" prefix pattern
        prefix = "gammel" * (generations - 2)
        if sex == "M":
            return f"{prefix}far"
        else:
            return f"{prefix}mor"

    def _get_descendant_term(self, generations: int, sex: str) -> str:
        """Get term for a direct descendant at given generation distance.

        Args:
            generations: Number of generations down from the person.
            sex: Sex of the descendant ('M', 'F', 'X', 'U').

        Returns:
            Swedish term for the descendant.
        """
        if generations == 1:
            return "son" if sex == "M" else "dotter"

        if generations == 2:
            if sex == "M":
                return "barnbarn"
            else:
                return "barnbarn"

        if generations == 3:
            if sex == "M":
                return "barnbarnsbarn"
            else:
                return "barnbarnsbarn"

        # Generic deep descendant
        return "barn" * (generations - 1) + "barn"

    def _get_sibling_term(self, sex: str) -> str:
        """Get term for a sibling.

        Args:
            sex: Sex of the sibling ('M', 'F', 'X', 'U').

        Returns:
            Swedish term for the sibling.
        """
        if sex == "M":
            return "bror"
        elif sex == "F":
            return "syster"
        return "syskon"

    def _get_uncle_aunt_term(self, generations_a: int, sex: str) -> str:
        """Get term for uncle/aunt relationships.

        When generations_a=2, generations_b=1: direct uncle/aunt.
        When generations_a=3, generations_b=1: grand-uncle/aunt (gammel-).

        Args:
            generations_a: Steps from person A to common ancestor.
            sex: Sex of person B (the uncle/aunt).

        Returns:
            Swedish term for uncle/aunt.
        """
        if generations_a == 2:
            # Direct uncle/aunt - we use generic terms since we don't
            # always know which parent's sibling this is from path alone
            if sex == "M":
                return "farbror/morbror"
            elif sex == "F":
                return "faster/moster"
            return "förälderns syskon"

        # Great-uncle/aunt and beyond
        prefix = "gammel" * (generations_a - 2)
        if sex == "M":
            return f"{prefix}farbror/{prefix}morbror"
        elif sex == "F":
            return f"{prefix}faster/{prefix}moster"
        return f"{prefix}förälderns syskon"

    def _get_nephew_niece_term(self, generations_b: int, sex: str) -> str:
        """Get term for nephew/niece relationships.

        When generations_a=1, generations_b=2: direct nephew/niece.
        When generations_a=1, generations_b=3: grand-nephew/niece.

        Args:
            generations_b: Steps from common ancestor down to person B.
            sex: Sex of person B (the nephew/niece).

        Returns:
            Swedish term for nephew/niece.
        """
        if generations_b == 2:
            if sex == "M":
                return "brorson/systerson"
            elif sex == "F":
                return "brordotter/systerdotter"
            return "syskonbarn"

        # Grand-nephew/niece and beyond
        prefix = "gammel" * (generations_b - 2)
        if sex == "M":
            return f"{prefix}brorson/{prefix}systerson"
        elif sex == "F":
            return f"{prefix}brordotter/{prefix}systerdotter"
        return f"{prefix}syskonbarn"

    def _get_cousin_term(self, generations_a: int, generations_b: int) -> str:
        """Get term for cousin relationships using -männing pattern.

        Swedish cousin terminology:
        - kusin (= tvåmänning): gen_a=2, gen_b=2
        - tremänning: gen_a=3, gen_b=3
        - fyrmänning: gen_a=4, gen_b=4
        - etc.

        Removed cousins use "X släktled bort":
        - "kusin, ett släktled bort" (first cousin once removed)
        - "tremänning, ett släktled bort" (second cousin once removed)
        - "femmänning, två släktled bort" (fourth cousin twice removed)

        The cousin degree is min(gen_a, gen_b) and the removal is
        abs(gen_a - gen_b).

        Args:
            generations_a: Steps from person A to common ancestor.
            generations_b: Steps from common ancestor down to person B.

        Returns:
            Swedish cousin term.
        """
        # The degree of cousinship: min generation minus 1 gives the
        # "männing" number. Actually the convention is:
        # First cousins (gen_a=2, gen_b=2) = tvåmänning = kusin
        # Second cousins (gen_a=3, gen_b=3) = tremänning
        # Third cousins (gen_a=4, gen_b=4) = fyrmänning
        # The männing number = min(gen_a, gen_b)
        degree = min(generations_a, generations_b)
        removal = abs(generations_a - generations_b)

        base_term = self._cousin_degree_term(degree)

        if removal == 0:
            return base_term

        # "X släktled bort" for removed cousins
        removal_text = self._removal_text(removal)
        return f"{base_term}, {removal_text}"

    def _cousin_degree_term(self, degree: int) -> str:
        """Get the base cousin term for a given degree.

        Args:
            degree: The männing number (min of the two generation counts).

        Returns:
            The base Swedish cousin term.
        """
        terms = {
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
        if degree in terms:
            return terms[degree]

        # For very distant cousins, use numeric pattern
        return f"{degree}-männing"

    def _removal_text(self, removal: int) -> str:
        """Get the Swedish text for cousin removal distance.

        Args:
            removal: Number of generations removed.

        Returns:
            Swedish text like "ett släktled bort", "två släktled bort".
        """
        ordinals = {
            1: "ett",
            2: "två",
            3: "tre",
            4: "fyra",
            5: "fem",
            6: "sex",
            7: "sju",
            8: "åtta",
            9: "nio",
            10: "tio",
        }
        num_text = ordinals.get(removal, str(removal))
        return f"{num_text} släktled bort"

    def _get_in_law_or_partner_term(
        self, base_term: str, sex: str
    ) -> str:
        """Get in-law or partner-of-relative term.

        Direct in-laws:
        - svärfar (father-in-law), svärmor (mother-in-law)
        - svåger (brother-in-law), svägerska (sister-in-law)

        For spouse-of-relative: "gift med X" where X is the base term.

        Args:
            base_term: The kinship term of the person whose partner this is.
            sex: Sex of the partner person.

        Returns:
            Swedish in-law or partner term.
        """
        # Direct in-law terms
        if base_term == "son" or base_term == "dotter":
            # Parent-in-law: partner of my child's... no
            # Actually: if base_term is what the person is to person A,
            # and we're looking at their partner:
            # - Partner of my "far"/"mor" = step-parent (not in-law)
            # - Partner of my "son"/"dotter" = son/daughter-in-law
            if sex == "M":
                return "svärson"
            else:
                return "svärdotter"

        if base_term in ("far", "mor"):
            # Partner of my parent = step-parent or in-law
            if sex == "M":
                return "svärfar"
            else:
                return "svärmor"

        if base_term in ("bror", "syster", "syskon"):
            if sex == "M":
                return "svåger"
            else:
                return "svägerska"

        # For all other relatives: "gift med X"
        return f"gift med {base_term}"


def get_kinship_term(
    generations_a: int,
    generations_b: int,
    sex_of_relative: str,
    relationship_type: str = "blood",
    via_partner: bool = False,
    partner_term_base: Optional[str] = None,
) -> str:
    """Convenience function to get a Swedish kinship term.

    Args:
        generations_a: Steps from person A up to common ancestor.
        generations_b: Steps from common ancestor down to person B.
        sex_of_relative: Sex of person B ('M', 'F', 'X', 'U').
        relationship_type: 'blood', 'legal', or 'adoption'.
        via_partner: If True, relationship goes through a partner link.
        partner_term_base: If via_partner, the base term for the relative.

    Returns:
        The Swedish kinship term string.
    """
    terms = SwedishKinshipTerms()
    return terms.get_term(
        generations_a=generations_a,
        generations_b=generations_b,
        sex_of_relative=sex_of_relative,
        relationship_type=relationship_type,
        via_partner=via_partner,
        partner_term_base=partner_term_base,
    )
