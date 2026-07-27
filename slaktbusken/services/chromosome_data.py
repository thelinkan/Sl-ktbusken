"""GRCh37/hg19 chromosome length constants and segment position calculations."""

# Chromosome lengths in base pairs (GRCh37/hg19 reference)
CHROMOSOME_LENGTHS: dict[str, int] = {
    "1": 249250621,
    "2": 243199373,
    "3": 198022430,
    "4": 191154276,
    "5": 180915260,
    "6": 171115067,
    "7": 159138663,
    "8": 146364022,
    "9": 141213431,
    "10": 135534747,
    "11": 135006516,
    "12": 133851895,
    "13": 115169878,
    "14": 107349540,
    "15": 102531392,
    "16": 90354753,
    "17": 81195210,
    "18": 78077248,
    "19": 59128983,
    "20": 63025520,
    "21": 48129895,
    "22": 51304566,
    "X": 155270560,
}


def segment_relative_position(start: int, chrom: str) -> float:
    """Calculate relative horizontal position (0.0–1.0) of a segment start on a chromosome.

    Args:
        start: The start position of the segment in base pairs.
        chrom: The chromosome identifier (e.g., "1", "22", "X").

    Returns:
        A float between 0.0 and 1.0 representing the relative position.

    Raises:
        KeyError: If the chromosome is not in CHROMOSOME_LENGTHS.
    """
    return start / CHROMOSOME_LENGTHS[chrom]


def segment_relative_width(start: int, end: int, chrom: str) -> float:
    """Calculate relative width (0.0–1.0) of a segment on a chromosome.

    Args:
        start: The start position of the segment in base pairs.
        end: The end position of the segment in base pairs.
        chrom: The chromosome identifier (e.g., "1", "22", "X").

    Returns:
        A float between 0.0 and 1.0 representing the relative width.

    Raises:
        KeyError: If the chromosome is not in CHROMOSOME_LENGTHS.
    """
    return (end - start) / CHROMOSOME_LENGTHS[chrom]
