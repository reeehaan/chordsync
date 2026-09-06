from pathlib import Path

from analysis.chords.models import ChordSegment
from analysis.chords.normalizer import normalize_chord_label


def parse_btc_lab(lab_path: Path) -> list[ChordSegment]:
    if not lab_path.exists():
        raise FileNotFoundError(
            f"BTC lab file not found: {lab_path}"
        )

    segments = []

    with lab_path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line:
                continue

            parts = line.split(maxsplit=2)

            if len(parts) != 3:
                continue

            start_text, end_text, raw_label = parts

            try:
                start = float(start_text)
                end = float(end_text)
            except ValueError:
                continue

            segments.append(
                ChordSegment(
                    start=start,
                    end=end,
                    raw_label=raw_label,
                    normalized_label=normalize_chord_label(
                        raw_label
                    ),
                    source="btc",
                )
            )

    return segments
