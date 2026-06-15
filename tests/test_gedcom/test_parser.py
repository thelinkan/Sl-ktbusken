"""Unit tests for the GEDCOM line-level parser.

Validates Requirements:
- 4.7: Non-GEDCOM files produce error; parsing failures reported in Swedish.
- 4.8: Malformed records logged with line number and tag; valid data continues.
"""

from __future__ import annotations

import pytest

from slaktbusken.gedcom.parser import (
    GedcomLine,
    GedcomParseError,
    ParseResult,
    ParseWarning,
    parse_gedcom,
)


# ---------------------------------------------------------------------------
# Sample GEDCOM data
# ---------------------------------------------------------------------------

VALID_GEDCOM = """\
0 HEAD
1 SOUR MyGenealogyApp
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Erik /Andersson/
1 SEX M
1 BIRT
2 DATE 15 MAY 1920
2 PLAC Ljusdal, Gävleborgs län
0 @I2@ INDI
1 NAME Anna /Svensson/
1 SEX F
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
0 @S1@ SOUR
1 TITL Husförhörslängd
1 AUTH Ljusdals församling
0 TRLR
"""

GEDCOM_WITH_CONC_CONT = """\
0 HEAD
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Erik /Andersson/
1 NOTE This is a note
2 CONC  that continues on same line
2 CONT and wraps to a new line
2 CONT with another line
0 TRLR
"""

GEDCOM_EMPTY_VALUES = """\
0 HEAD
0 @I1@ INDI
1 BIRT
2 DATE 1920
0 TRLR
"""


# ---------------------------------------------------------------------------
# Tests for valid GEDCOM parsing (9.1)
# ---------------------------------------------------------------------------


class TestValidGedcomParsing:
    """Tests for parsing well-formed GEDCOM input."""

    def test_parse_basic_structure(self) -> None:
        """Top-level records are extracted correctly."""
        result = parse_gedcom(VALID_GEDCOM)

        assert isinstance(result, ParseResult)
        assert len(result.warnings) == 0

        # Should have HEAD, 2 INDI, 1 FAM, 1 SOUR, TRLR = 6 records
        tags = [r.tag for r in result.records]
        assert tags == ["HEAD", "INDI", "INDI", "FAM", "SOUR", "TRLR"]

    def test_xref_ids_parsed(self) -> None:
        """Cross-reference IDs are correctly extracted."""
        result = parse_gedcom(VALID_GEDCOM)

        assert result.records[0].xref_id is None  # HEAD has no xref
        assert result.records[1].xref_id == "@I1@"
        assert result.records[2].xref_id == "@I2@"
        assert result.records[3].xref_id == "@F1@"
        assert result.records[4].xref_id == "@S1@"

    def test_values_parsed(self) -> None:
        """Tag values are correctly extracted."""
        result = parse_gedcom(VALID_GEDCOM)

        head = result.records[0]
        assert head.children[0].tag == "SOUR"
        assert head.children[0].value == "MyGenealogyApp"
        assert head.children[1].tag == "CHAR"
        assert head.children[1].value == "UTF-8"

    def test_tree_structure(self) -> None:
        """Child lines are correctly nested under their parents."""
        result = parse_gedcom(VALID_GEDCOM)

        # @I1@ INDI record
        indi1 = result.records[1]
        assert indi1.tag == "INDI"
        assert len(indi1.children) == 3  # NAME, SEX, BIRT

        name_line = indi1.children[0]
        assert name_line.tag == "NAME"
        assert name_line.value == "Erik /Andersson/"

        birt_line = indi1.children[2]
        assert birt_line.tag == "BIRT"
        assert birt_line.value is None
        assert len(birt_line.children) == 2  # DATE, PLAC

        date_line = birt_line.children[0]
        assert date_line.tag == "DATE"
        assert date_line.value == "15 MAY 1920"

        plac_line = birt_line.children[1]
        assert plac_line.tag == "PLAC"
        assert plac_line.value == "Ljusdal, Gävleborgs län"

    def test_family_record(self) -> None:
        """FAM records with cross-reference values are parsed correctly."""
        result = parse_gedcom(VALID_GEDCOM)

        fam = result.records[3]
        assert fam.tag == "FAM"
        assert fam.xref_id == "@F1@"

        husb = fam.children[0]
        assert husb.tag == "HUSB"
        assert husb.value == "@I1@"

        wife = fam.children[1]
        assert wife.tag == "WIFE"
        assert wife.value == "@I2@"

    def test_source_record(self) -> None:
        """SOUR records are parsed with their sub-tags."""
        result = parse_gedcom(VALID_GEDCOM)

        sour = result.records[4]
        assert sour.tag == "SOUR"
        assert sour.xref_id == "@S1@"
        assert len(sour.children) == 2

        assert sour.children[0].tag == "TITL"
        assert sour.children[0].value == "Husförhörslängd"

    def test_line_numbers_tracked(self) -> None:
        """Each parsed line records its 1-based line number."""
        result = parse_gedcom(VALID_GEDCOM)

        assert result.records[0].line_number == 1  # 0 HEAD
        assert result.records[1].line_number == 4  # 0 @I1@ INDI

    def test_empty_values_handled(self) -> None:
        """Lines without values produce None for the value field."""
        result = parse_gedcom(GEDCOM_EMPTY_VALUES)

        indi = result.records[1]
        birt = indi.children[0]
        assert birt.tag == "BIRT"
        assert birt.value is None
        assert birt.children[0].tag == "DATE"
        assert birt.children[0].value == "1920"


# ---------------------------------------------------------------------------
# Tests for CONC/CONT handling (9.1)
# ---------------------------------------------------------------------------


class TestConcContHandling:
    """Tests for continuation line processing."""

    def test_conc_appends_without_space(self) -> None:
        """CONC appends to previous value without adding a space."""
        result = parse_gedcom(GEDCOM_WITH_CONC_CONT)

        indi = result.records[1]
        note = indi.children[1]
        assert note.tag == "NOTE"
        # CONC appends directly: "This is a note" + " that continues on same line"
        # CONT appends with newline: + "\nand wraps to a new line" + "\nwith another line"
        assert "This is a note that continues on same line" in note.value
        assert "\nand wraps to a new line" in note.value
        assert "\nwith another line" in note.value

    def test_cont_appends_with_newline(self) -> None:
        """CONT appends to previous value with a newline separator."""
        result = parse_gedcom(GEDCOM_WITH_CONC_CONT)

        indi = result.records[1]
        note = indi.children[1]

        expected = "This is a note that continues on same line\nand wraps to a new line\nwith another line"
        assert note.value == expected

    def test_conc_on_empty_value(self) -> None:
        """CONC on a line with no initial value starts the value."""
        text = "0 HEAD\n0 @I1@ INDI\n1 NOTE\n2 CONC Hello\n0 TRLR\n"
        result = parse_gedcom(text)

        indi = result.records[1]
        note = indi.children[0]
        assert note.value == "Hello"

    def test_cont_on_empty_value(self) -> None:
        """CONT on a line with no initial value prepends a newline."""
        text = "0 HEAD\n0 @I1@ INDI\n1 NOTE\n2 CONT Hello\n0 TRLR\n"
        result = parse_gedcom(text)

        indi = result.records[1]
        note = indi.children[0]
        assert note.value == "\nHello"

    def test_multiple_conc_lines(self) -> None:
        """Multiple CONC lines concatenate without spaces."""
        text = "0 HEAD\n0 @I1@ INDI\n1 NOTE AB\n2 CONC CD\n2 CONC EF\n0 TRLR\n"
        result = parse_gedcom(text)

        indi = result.records[1]
        note = indi.children[0]
        assert note.value == "ABCDEF"


# ---------------------------------------------------------------------------
# Tests for error handling (9.2)
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error detection and best-effort parsing."""

    def test_non_gedcom_file_raises_error(self) -> None:
        """A file without '0 HEAD' near the beginning raises GedcomParseError."""
        non_gedcom = "This is just a plain text file.\nWith multiple lines.\n"
        with pytest.raises(GedcomParseError) as exc_info:
            parse_gedcom(non_gedcom)

        assert "GEDCOM" in exc_info.value.message
        # Error message should be in Swedish
        assert "giltig" in exc_info.value.message.lower() or "saknar" in exc_info.value.message.lower()

    def test_empty_file_raises_error(self) -> None:
        """An empty file raises GedcomParseError."""
        with pytest.raises(GedcomParseError):
            parse_gedcom("")

    def test_whitespace_only_raises_error(self) -> None:
        """A file with only whitespace raises GedcomParseError."""
        with pytest.raises(GedcomParseError):
            parse_gedcom("   \n\n   \n")

    def test_head_not_first_but_within_five_lines(self) -> None:
        """HEAD within first 5 non-empty lines is accepted (e.g., BOM prefix)."""
        # Some GEDCOM files have a BOM or comment before HEAD
        text = "\n\n0 HEAD\n1 CHAR UTF-8\n0 TRLR\n"
        result = parse_gedcom(text)
        assert result.records[0].tag == "HEAD"

    def test_malformed_line_generates_warning(self) -> None:
        """Malformed lines produce warnings with line numbers."""
        text = "0 HEAD\n1 CHAR UTF-8\nTHIS IS NOT VALID\n0 TRLR\n"
        result = parse_gedcom(text)

        assert len(result.warnings) == 1
        assert result.warnings[0].line_number == 3
        assert "3" in result.warnings[0].message

    def test_best_effort_parsing_continues_after_error(self) -> None:
        """Parser continues after malformed lines, processing remaining valid data."""
        text = (
            "0 HEAD\n"
            "1 CHAR UTF-8\n"
            "BROKEN LINE\n"
            "0 @I1@ INDI\n"
            "1 NAME Erik /Test/\n"
            "ANOTHER BROKEN\n"
            "0 TRLR\n"
        )
        result = parse_gedcom(text)

        # Should have warnings for the 2 broken lines
        assert len(result.warnings) == 2
        assert result.warnings[0].line_number == 3
        assert result.warnings[1].line_number == 6

        # Should still parse the valid records
        tags = [r.tag for r in result.records]
        assert "HEAD" in tags
        assert "INDI" in tags
        assert "TRLR" in tags

    def test_orphan_level_generates_warning(self) -> None:
        """A line at a level too deep for context generates a warning."""
        text = "0 HEAD\n3 DEEP tag_value\n0 TRLR\n"
        result = parse_gedcom(text)

        # Level 3 without a level 2 parent should warn
        assert len(result.warnings) >= 1
        found = any("nivå" in w.message.lower() or "3" in w.message for w in result.warnings)
        assert found

    def test_conc_without_parent_generates_warning(self) -> None:
        """A CONC/CONT line without a preceding value line generates a warning."""
        text = "0 HEAD\n1 CONC orphan text\n0 TRLR\n"
        result = parse_gedcom(text)

        # The CONC at level 1 should find HEAD (level 0) as parent
        # Actually, let's test with a level that truly has no parent
        text2 = "0 HEAD\n0 @I1@ INDI\n1 CONT text at wrong level\n0 TRLR\n"
        result2 = parse_gedcom(text2)
        # CONT at level 1 should append to INDI (level 0) - this is valid
        # Let's try a case that truly orphans
        text3 = "0 HEAD\n3 CONC orphan\n0 TRLR\n"
        result3 = parse_gedcom(text3)
        assert len(result3.warnings) >= 1

    def test_xml_file_raises_error(self) -> None:
        """An XML file is rejected as non-GEDCOM."""
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<root>\n<item/>\n</root>\n'
        with pytest.raises(GedcomParseError):
            parse_gedcom(xml)

    def test_json_file_raises_error(self) -> None:
        """A JSON file is rejected as non-GEDCOM."""
        json_text = '{"name": "test", "value": 42}\n'
        with pytest.raises(GedcomParseError):
            parse_gedcom(json_text)


# ---------------------------------------------------------------------------
# Tests for cross-reference parsing (9.1)
# ---------------------------------------------------------------------------


class TestCrossReferences:
    """Tests for cross-reference (XREF) ID parsing."""

    def test_xref_with_numeric_id(self) -> None:
        """Standard numeric XREF IDs like @I1@ are parsed."""
        text = "0 HEAD\n0 @I1@ INDI\n0 TRLR\n"
        result = parse_gedcom(text)
        assert result.records[1].xref_id == "@I1@"

    def test_xref_with_alphanumeric_id(self) -> None:
        """Alphanumeric XREF IDs like @PERSON_123@ are parsed."""
        text = "0 HEAD\n0 @PERSON_123@ INDI\n0 TRLR\n"
        result = parse_gedcom(text)
        assert result.records[1].xref_id == "@PERSON_123@"

    def test_xref_in_value_position(self) -> None:
        """XREF references in value position (like HUSB @I1@) are treated as values."""
        text = "0 HEAD\n0 @F1@ FAM\n1 HUSB @I1@\n0 TRLR\n"
        result = parse_gedcom(text)

        fam = result.records[1]
        husb = fam.children[0]
        assert husb.tag == "HUSB"
        assert husb.value == "@I1@"
        assert husb.xref_id is None

    def test_family_xref(self) -> None:
        """Family XREF IDs are parsed."""
        text = "0 HEAD\n0 @F42@ FAM\n0 TRLR\n"
        result = parse_gedcom(text)
        assert result.records[1].xref_id == "@F42@"

    def test_source_xref(self) -> None:
        """Source XREF IDs are parsed."""
        text = "0 HEAD\n0 @S1@ SOUR\n1 TITL Test Source\n0 TRLR\n"
        result = parse_gedcom(text)
        assert result.records[1].xref_id == "@S1@"
        assert result.records[1].children[0].value == "Test Source"
