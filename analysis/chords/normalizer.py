import re


NO_CHORD_LABELS = {
    "N",
    "NC",
    "N.C.",
    "NO_CHORD",
}


ENHARMONIC_MAP = {
    "Cb": "B",
    "Db": "C#",
    "Eb": "D#",
    "Fb": "E",
    "Gb": "F#",
    "Ab": "G#",
    "Bb": "A#",
}


def normalize_chord_label(label: str) -> str:
    """
    Normalize chord labels into a simplified
    major / minor / no-chord vocabulary.

    Examples:
        Bbm7     -> A#m
        Ab6      -> G#
        F#7/A#   -> F#
        C#6      -> C#
        A#:min   -> A#m
        D#:min   -> D#m
        N        -> N
    """

    label = label.strip()

    if not label:
        return "N"

    if label.upper() in NO_CHORD_LABELS:
        return "N"

    # Convert BTC-style labels.
    # A#:min -> A#m
    # D#:min -> D#m
    # C:maj  -> C
    label = label.replace(":min", "m")
    label = label.replace(":maj", "")

    # Remove inversion/slash bass.
    # F#7/A# -> F#7
    root_part = label.split("/")[0]

    # Extract:
    # root note
    # accidental
    # chord quality
    match = re.match(
        r"^([A-Ga-g])([#b]?)(.*)$",
        root_part,
    )

    if not match:
        return "N"

    note = match.group(1).upper()
    accidental = match.group(2)
    quality = match.group(3).lower()

    root = f"{note}{accidental}"

    # Convert flats to equivalent sharp spelling.
    root = ENHARMONIC_MAP.get(root, root)

    # Minor chords.
    if quality.startswith("m") and not quality.startswith("maj"):
        return f"{root}m"

    # Everything else is treated as major
    # for the Sprint 1 vocabulary.
    return root
