import re


NO_CHORD_LABELS = {
    "N",
    "NC",
    "N.C.",
    "NO_CHORD",
}


def normalize_chord_label(label: str) -> str:
    """
    Normalize extended chord labels into a simple
    major/minor/no-chord vocabulary.

    Examples:
        Bbm7    -> Bbm
        Ab6     -> Ab
        F#7/A#  -> F#
        C#6     -> C#
        N       -> N
    """

    label = label.strip()

    if not label:
        return "N"

    if label.upper() in NO_CHORD_LABELS:
        return "N"

    # Remove inversion/slash bass.
    root_part = label.split("/")[0]

    # Extract root note: A-G plus optional # or b.
    match = re.match(r"^([A-Ga-g])([#b]?)(.*)$", root_part)

    if not match:
        return "N"

    note = match.group(1).upper()
    accidental = match.group(2)
    quality = match.group(3).lower()

    root = f"{note}{accidental}"

    # Treat explicit minor chords as minor.
    if quality.startswith("m") and not quality.startswith("maj"):
        return f"{root}m"

    # Everything else becomes major for Sprint 1.
    return root
