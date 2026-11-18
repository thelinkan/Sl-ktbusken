"""Hypothesis strategies for date tests (data-integrity-0-3-0, task 5.5)."""

from __future__ import annotations

from hypothesis import strategies as st

from slaktbusken.model.date_semantics import _month_len
from slaktbusken.model.event import DateValue

MONTH_NAMES = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)

SINGLE_QUALIFIERS = ("about", "estimated", "calculated", "before", "after", "from", "to")
RANGE_QUALIFIERS = ("between", "from_to")
NON_EXACT_QUALIFIERS = SINGLE_QUALIFIERS + RANGE_QUALIFIERS + ("interpreted",)

calendars = st.sampled_from(["gregorian", "julian"])


def real_iso(calendar: str, precision: str, years=st.integers(1000, 2100)):
    """ISO text real in *calendar* with the given precision."""

    @st.composite
    def build(draw):
        y = draw(years)
        if precision == "year":
            return f"{y:04d}"
        m = draw(st.integers(1, 12))
        if precision == "month":
            return f"{y:04d}-{m:02d}"
        d = draw(st.integers(1, _month_len(y, m, calendar)))
        return f"{y:04d}-{m:02d}-{d:02d}"

    return build()


precisions = st.sampled_from(["year", "month", "day"])


@st.composite
def valid_date_values(draw, qualifiers=("exact",) + NON_EXACT_QUALIFIERS, years=st.integers(1000, 2100)):
    """A valid DateValue (``validate_date_value`` returns no errors)."""
    qualifier = draw(st.sampled_from(qualifiers))
    calendar = draw(calendars)
    precision = draw(precisions)
    first = draw(real_iso(calendar, precision, years))
    value_to = None
    if qualifier in RANGE_QUALIFIERS:
        second = draw(real_iso(calendar, precision, years))
        first, value_to = sorted([first, second])
    original_text = None
    if qualifier == "interpreted":
        original_text = f"INT {first} (tolkat)"
    return DateValue(
        value=first,
        precision="approximate" if qualifier != "exact" else precision,
        qualifier=qualifier,
        value_to=value_to,
        calendar=calendar,
        original_text=original_text,
    )


_TOKENS = [
    "BET", "AND", "FROM", "TO", "ABT", "BEF", "AFT", "EST", "CAL", "INT",
    "@#DJULIAN@", "@#DGREGORIAN@", "@#DHEBREW@", "1", "29", "30", "31", "FEB",
    "JAN", "MAR", "1700", "1712", "1850", "1850/51", "(x)", "(", ")", "/",
    "1850-05-03", "3.5.1850", "abt", "xyz", "OKT",
]


@st.composite
def date_like_texts(draw):
    """Non-empty text built from date tokens or arbitrary characters."""
    text = draw(
        st.one_of(
            st.lists(st.sampled_from(_TOKENS), min_size=1, max_size=7).map(" ".join),
            st.text(max_size=30),
        )
    )
    if not text.strip():
        text = "x"
    return text
