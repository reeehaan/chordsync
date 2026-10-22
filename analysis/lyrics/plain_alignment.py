"""Align plain (untimed) lyrics to the vocals of a whole song with MMS.

Synced lyrics tell the aligner where each line starts. Plain lyrics do not, so the
whole text is aligned against the whole vocal track in one pass (CTC forced
alignment): the model finds when each word is sung, and its blank symbol absorbs
instrumental stretches. Nothing is transcribed.

Forced alignment always places every word somewhere, even when the text does not
belong to the audio. So the result carries a confidence, and a low one means the
lyrics should not be shown.

Runs in the WhisperX environment (it needs torch, torchaudio and uroman):

    python -m analysis.lyrics.plain_alignment --audio vocals.wav \\
        --lyrics lyrics.txt --output aligned.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

CHUNK_SECONDS = 20.0
CONTEXT_SECONDS = 1.0
FRAME_SAMPLES = 320  # the model's stride at 16 kHz: 50 frames a second
MINIMUM_WORD_SECONDS = 0.05
# Words of one lyric line are sung close together. A longer gap inside a line means
# the aligner pulled the words before it onto some earlier sound (a vocal sample in
# an intro, a breath), so those words are moved up against the rest of the line.
MAXIMUM_GAP_SECONDS = 4.0
STRAY_WORD_SECONDS = 0.4
# A word's letters are sung together. When the aligner scatters them (some on an
# earlier sound), the biggest tight group of letters is where the word really is.
LETTER_CLUSTER_GAP_SECONDS = 1.5

# A line such as "[Chorus]" or "(x2)" is structure, not lyrics.
_STRUCTURE = re.compile(r"^\s*[\[\(][^\]\)]*[\]\)]\s*$")
_LETTERS = re.compile(r"[^a-z']")


@dataclass(frozen=True)
class AlignedWord:
    text: str
    start: float
    end: float
    score: float


@dataclass(frozen=True)
class PlainAlignment:
    lines: list[list[AlignedWord]]
    skipped_words: int
    mean_score: float
    low_score_share: float


def parse_plain_lines(text: str | None) -> list[list[str]]:
    """The lyric lines as lists of words; blank and structure-only lines are dropped."""
    lines: list[list[str]] = []
    for raw in (text or "").splitlines():
        if not raw.strip() or _STRUCTURE.match(raw):
            continue
        words = raw.split()
        if words:
            lines.append(words)
    return lines


def emission_chunks(
    total_samples: int,
    chunk_samples: int,
    context_samples: int,
) -> list[tuple[int, int, int, int]]:
    """(clip_start, clip_end, keep_from, keep_to) sample ranges for each chunk.

    The model sees a little context on each side of a chunk, which is then trimmed
    off so neighbouring chunks join without a seam. Chunk edges sit on whole model
    frames.
    """
    if chunk_samples % FRAME_SAMPLES or context_samples % FRAME_SAMPLES:
        raise ValueError("chunk and context must be whole model frames")
    ranges = []
    position = 0
    while position < total_samples:
        keep_to = min(position + chunk_samples, total_samples)
        ranges.append(
            (
                max(0, position - context_samples),
                min(total_samples, keep_to + context_samples),
                position,
                keep_to,
            )
        )
        position = keep_to
    return ranges


def main_cluster(
    letters: Sequence[tuple[float, float, float]],
    *,
    gap: float = LETTER_CLUSTER_GAP_SECONDS,
) -> tuple[float, float, float]:
    """(start, end, mean score) of the largest tight group of (start, end, score) letters.

    Ties go to the group with the higher total score, then the later one.
    """
    groups: list[list[tuple[float, float, float]]] = [[letters[0]]]
    for letter in letters[1:]:
        if letter[0] - groups[-1][-1][1] > gap:
            groups.append([letter])
        else:
            groups[-1].append(letter)
    best = max(
        enumerate(groups),
        key=lambda item: (len(item[1]), sum(l[2] for l in item[1]), item[0]),
    )[1]
    return (
        best[0][0],
        best[-1][1],
        sum(letter[2] for letter in best) / len(best),
    )


def repair_stray_words(
    line: list[AlignedWord],
    *,
    maximum_gap: float = MAXIMUM_GAP_SECONDS,
    word_seconds: float = STRAY_WORD_SECONDS,
) -> list[AlignedWord]:
    """Move words stranded far before the rest of their line up against it."""
    last_gap = None
    for index in range(len(line) - 1):
        if line[index + 1].start - line[index].end > maximum_gap:
            last_gap = index
    if last_gap is None:
        return line
    anchor = line[last_gap + 1].start - 0.05
    count = last_gap + 1
    moved = []
    for position in range(count):
        end = anchor - (count - 1 - position) * word_seconds
        start = max(0.0, end - word_seconds)
        word = line[position]
        # A moved word is a guess, so it scores as one.
        moved.append(AlignedWord(word.text, start, end, min(word.score, 0.0)))
    return moved + line[count:]


def summarise(
    lines: Sequence[Sequence[AlignedWord]],
    *,
    low_score: float,
) -> tuple[float, float]:
    """Mean word score, and the share of words scoring below ``low_score``."""
    scores = [word.score for line in lines for word in line]
    if not scores:
        return 0.0, 1.0
    low = sum(1 for score in scores if score < low_score) / len(scores)
    return statistics.fmean(scores), low


def to_transcript(alignment: PlainAlignment) -> dict[str, Any]:
    """A WhisperX-shaped transcript, one segment per lyric line."""
    segments = []
    for line in alignment.lines:
        if not line:
            continue
        segments.append(
            {
                "start": round(line[0].start, 3),
                "end": round(line[-1].end, 3),
                "text": " " + " ".join(word.text for word in line),
                "words": [
                    {
                        "word": word.text,
                        "start": round(word.start, 3),
                        "end": round(word.end, 3),
                        "score": round(word.score, 3),
                    }
                    for word in line
                ],
            }
        )
    return {
        "segments": segments,
        "word_segments": [word for segment in segments for word in segment["words"]],
        "language": "aligned",
        "alignment": "mms_fa_whole_song",
        "alignment_mean_score": round(alignment.mean_score, 3),
        "alignment_low_score_share": round(alignment.low_score_share, 3),
    }


# --- the model -------------------------------------------------------------------


def align_whole_song(
    audio_path: Path,
    lines: Sequence[Sequence[str]],
    *,
    low_score: float = 0.3,
    progress: Callable[[str], None] | None = None,
) -> PlainAlignment:
    import torch
    import uroman
    from torchaudio.pipelines import MMS_FA

    from analysis.lyrics.mms_alignment import load_mono_16k

    say = progress or (lambda _message: None)
    waveform = load_mono_16k(audio_path)
    rate = MMS_FA.sample_rate
    model = MMS_FA.get_model(with_star=False).eval()
    tokenizer, aligner = MMS_FA.get_tokenizer(), MMS_FA.get_aligner()
    romanizer = uroman.Uroman()

    total = waveform.size(1)
    emissions = []
    for clip_start, clip_end, keep_from, keep_to in emission_chunks(
        total,
        int(CHUNK_SECONDS * rate) // FRAME_SAMPLES * FRAME_SAMPLES,
        int(CONTEXT_SECONDS * rate) // FRAME_SAMPLES * FRAME_SAMPLES,
    ):
        with torch.inference_mode():
            emission, _ = model(waveform[:, clip_start:clip_end])
        frames = emission.size(1)
        per_sample = frames / (clip_end - clip_start)
        first = round((keep_from - clip_start) * per_sample)
        last = round((keep_to - clip_start) * per_sample)
        emissions.append(emission[:, first:last])
        say(f"emissions up to {keep_to / rate:.0f}s")
    emission = torch.cat(emissions, dim=1)
    seconds_per_frame = total / emission.size(1) / rate

    flat: list[str] = []
    positions: list[tuple[int, int]] = []  # (line, word) for each usable word
    for line_index, words in enumerate(lines):
        for word_index, word in enumerate(words):
            romanized = _LETTERS.sub("", romanizer.romanize_string(word).lower())
            if romanized:
                flat.append(romanized)
                positions.append((line_index, word_index))
    say(f"aligning {len(flat)} words over {total / rate:.0f}s")
    spans = aligner(emission[0], tokenizer(flat))

    by_position: dict[tuple[int, int], AlignedWord] = {}
    for (line_index, word_index), word_spans in zip(positions, spans):
        start, end, score = main_cluster(
            [
                (
                    span.start * seconds_per_frame,
                    span.end * seconds_per_frame,
                    float(span.score),
                )
                for span in word_spans
            ]
        )
        by_position[(line_index, word_index)] = AlignedWord(
            lines[line_index][word_index],
            start,
            max(end, start + MINIMUM_WORD_SECONDS),
            score,
        )
    aligned_lines = [
        repair_stray_words(
            [
                by_position[(line_index, word_index)]
                for word_index in range(len(words))
                if (line_index, word_index) in by_position
            ]
        )
        for line_index, words in enumerate(lines)
    ]
    mean_score, low_share = summarise(aligned_lines, low_score=low_score)
    return PlainAlignment(
        aligned_lines,
        len(lines and [w for line in lines for w in line]) - len(flat),
        mean_score,
        low_share,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--lyrics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)

    lines = parse_plain_lines(arguments.lyrics.read_text(encoding="utf-8"))
    alignment = align_whole_song(
        arguments.audio, lines, progress=lambda m: print(m, file=sys.stderr)
    )
    arguments.output.write_text(
        json.dumps(to_transcript(alignment), ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"mean score {alignment.mean_score:.3f}, "
        f"low-score words {alignment.low_score_share:.1%}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
