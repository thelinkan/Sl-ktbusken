"""Example tests for the merge candidate model and its id prefixes.

Validates: Requirements 2.2, 3.1, 34.9
"""

from __future__ import annotations

import re

from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.model.merge_candidate import (
    ASSESSMENT_LABELS_SV,
    CANDIDATE_ASSESSMENTS,
    MergeCandidate,
    MergeCandidateComment,
    pair_key,
)


def test_candidate_defaults():
    cand = MergeCandidate(id="mergecand_1", person_1_id="person_1", person_2_id="person_2")
    assert cand.assessment == "unreviewed"
    assert cand.enabled is True
    assert cand.research_case_id is None
    assert cand.comments == []


def test_candidate_comments_not_shared():
    a = MergeCandidate(id="mergecand_1", person_1_id="p1", person_2_id="p2")
    b = MergeCandidate(id="mergecand_2", person_1_id="p1", person_2_id="p3")
    a.comments.append(MergeCandidateComment(id="mergecomment_1"))
    assert b.comments == []


def test_comment_defaults():
    comment = MergeCandidateComment(id="mergecomment_1")
    assert comment.date == ""
    assert comment.text == ""


def test_pair_key_symmetry():
    assert pair_key("person_1", "person_2") == pair_key("person_2", "person_1")
    assert pair_key("person_2", "person_1") == ("person_1", "person_2")
    assert pair_key("person_1", "person_1") == ("person_1", "person_1")


def test_id_prefixes_are_distinct_and_isolated():
    prefixes = {
        "merge_candidate": "mergecand_",
        "merge_candidate_comment": "mergecomment_",
        "merge_history": "merge_",
    }
    for entity_type, prefix in prefixes.items():
        assert IDGenerator._PREFIXES[entity_type] == prefix

    patterns = {p: re.compile(rf"^{re.escape(p)}(\d+)$") for p in prefixes.values()}
    samples = {p: f"{p}7" for p in prefixes.values()}
    for prefix, pattern in patterns.items():
        for other_prefix, sample in samples.items():
            assert bool(pattern.match(sample)) == (prefix == other_prefix)


def test_id_generator_counters_independent_across_merge_prefixes():
    gen = IDGenerator({"mergecand_5", "mergecomment_9", "merge_2"})
    assert gen.generate("merge_candidate") == "mergecand_6"
    assert gen.generate("merge_candidate_comment") == "mergecomment_10"
    assert gen.generate("merge_history") == "merge_3"


def test_assessment_labels_cover_all_assessments_in_swedish():
    assert set(ASSESSMENT_LABELS_SV) == set(CANDIDATE_ASSESSMENTS)
    assert ASSESSMENT_LABELS_SV == {
        "unreviewed": "Ej granskad",
        "possible": "Möjlig dubblett",
        "confirmed": "Bekräftad dublett",
        "rejected": "Inte samma person",
    }
