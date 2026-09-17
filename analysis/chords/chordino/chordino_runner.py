from pathlib import Path
import csv
import io
import os
import shutil
import subprocess

from analysis.preprocessing.audio_preprocessor import get_audio_metadata

from analysis.chords.models import ChordSegment
from analysis.chords.normalizer import normalize_chord_label


DEFAULT_PLUGIN = "vamp:nnls-chroma:chordino:simplechord"
SONIC_ANNOTATOR_ENV = "CHORDSYNC_SONIC_ANNOTATOR"


class SonicAnnotatorNotFoundError(RuntimeError):
    pass


def get_sonic_annotator_path() -> Path:
    configured_path = os.getenv(SONIC_ANNOTATOR_ENV) or os.getenv(
        "SONIC_ANNOTATOR_PATH"
    )

    if configured_path:
        executable = Path(configured_path).expanduser()
        if executable.is_file() and os.access(executable, os.X_OK):
            return executable
        raise SonicAnnotatorNotFoundError(
            f"{SONIC_ANNOTATOR_ENV} does not identify an executable file."
        )

    discovered_path = shutil.which("sonic-annotator")
    if discovered_path:
        return Path(discovered_path)
    raise SonicAnnotatorNotFoundError(
        f"sonic-annotator is not configured; set {SONIC_ANNOTATOR_ENV}."
    )


def run_chordino(audio_path: Path) -> list[ChordSegment]:
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    sonic_annotator = get_sonic_annotator_path()

    command = [
        str(sonic_annotator),
        "-d",
        DEFAULT_PLUGIN,
        "-w",
        "csv",
        "--csv-stdout",
        str(audio_path),
    ]

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"Chordino analysis failed:\n{error.stderr}"
        ) from error

    events = parse_chordino_csv(result.stdout)

    duration = get_audio_metadata(audio_path)["duration"]

    return events_to_segments(events, duration)


def parse_chordino_csv(csv_output: str) -> list[dict]:
    events = []

    reader = csv.reader(io.StringIO(csv_output))

    for row in reader:
        if len(row) < 3:
            continue

        try:
            timestamp = float(row[-2])
        except ValueError:
            continue

        label = row[-1].strip().strip('"')

        events.append({
            "time": timestamp,
            "label": label,
        })

    return events


def events_to_segments(
    events: list[dict],
    duration: float,
) -> list[ChordSegment]:
    if not events:
        return []

    segments = []

    for index, event in enumerate(events):
        start = event["time"]

        if index + 1 < len(events):
            end = events[index + 1]["time"]
        else:
            end = duration

        segments.append(
    ChordSegment(
        start=round(start, 6),
        end=round(end, 6),
        raw_label=event["label"],
        normalized_label=normalize_chord_label(
            event["label"]
        ),
        source="chordino",
    )
)

    return segments
