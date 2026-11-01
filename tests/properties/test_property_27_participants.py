"""Property 27: Event participants.

**Validates: Requirements 21.12, 21.13**
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from slaktbusken.model.event import Participant
from slaktbusken.services.merge_rules import rewrite_participants

RETIRED = "I_retired"
SURVIVOR = "I_survivor"
OTHERS = ["I_a", "I_b", "I_c"]
ROLES = ["principal", "witness", "godparent", "officiant"]


@st.composite
def participant_lists(draw):
    ids = draw(st.lists(st.sampled_from(OTHERS + [RETIRED, SURVIVOR]), max_size=8))
    return [Participant(person_id=i, role=draw(st.sampled_from(ROLES))) for i in ids]


def _group(ps):
    return [p for p in ps if p.person_id in (RETIRED, SURVIVOR)]


@given(participant_lists(), st.one_of(st.none(), st.sampled_from(ROLES)))
def test_property_27_event_participants(participants, chosen):
    original = [(p.person_id, p.role) for p in participants]
    res = rewrite_participants(participants, RETIRED, SURVIVOR, chosen)

    # Input is not modified.
    assert [(p.person_id, p.role) for p in participants] == original

    group = _group(participants)
    out = res.participants

    # Retired id never remains; at most one entry for the survivor.
    assert all(p.person_id != RETIRED for p in out)
    assert sum(1 for p in out if p.person_id == SURVIVOR) == (1 if group else 0)

    # Other participants unchanged and in order.
    assert [(p.person_id, p.role) for p in out if p.person_id not in (SURVIVOR,)] == [
        (p.person_id, p.role) for p in participants if p.person_id not in (RETIRED, SURVIVOR)
    ]

    if not group:
        assert res.removed == 0 and not res.has_conflict
        return

    assert res.removed == len(group) - 1
    # Survivor entry sits at the position of the first group entry.
    first_pos = next(i for i, p in enumerate(participants) if p.person_id in (RETIRED, SURVIVOR))
    assert out[first_pos].person_id == SURVIVOR

    roles = list(dict.fromkeys(p.role for p in group))
    if len(roles) == 1:
        assert not res.has_conflict
        assert out[first_pos].role == roles[0]
    elif chosen in roles:
        assert not res.has_conflict
        assert out[first_pos].role == chosen
    else:
        assert res.has_conflict
        assert res.conflicting_roles == tuple(roles)
