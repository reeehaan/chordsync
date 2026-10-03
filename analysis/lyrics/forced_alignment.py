from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Sequence

from analysis.lyrics.lyrics_verification import (
    AlignedToken,
    AlignmentOperation,
    VerificationState,
    VerifiedToken,
)


@dataclass(frozen=True)
class ReferenceAlignmentSegment:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class ForcedAlignmentContext:
    segment: ReferenceAlignmentSegment
    candidate_offset: int


def select_forced_alignment_context(
    alignment: Sequence[AlignedToken],
    verified_tokens: Sequence[VerifiedToken],
    candidate_index: int,
    *,
    context_words_per_side: int = 2,
    maximum_window_seconds: float = 8.0,
) -> ForcedAlignmentContext | None:
    """Choose a small unambiguous matched window around one verified mismatch."""
    if len(alignment) != len(verified_tokens):
        raise ValueError("Alignment and verification token counts must match.")
    if candidate_index < 0 or candidate_index >= len(alignment):
        raise IndexError("Candidate index is outside the alignment.")
    candidate = alignment[candidate_index]
    verified = verified_tokens[candidate_index]
    if (
        candidate.operation is not AlignmentOperation.SUBSTITUTION
        or verified.verification is not VerificationState.VERIFIED_REFERENCE
        or candidate.asr_word is None
        or candidate.reference_word is None
    ):
        return None

    start_index = candidate_index
    for _ in range(context_words_per_side):
        previous_index = start_index - 1
        if previous_index < 0 or not _stable_match(alignment[previous_index]):
            break
        start_index = previous_index
    end_index = candidate_index
    for _ in range(context_words_per_side):
        following_index = end_index + 1
        if following_index >= len(alignment) or not _stable_match(
            alignment[following_index]
        ):
            break
        end_index = following_index
    if start_index == candidate_index or end_index == candidate_index:
        return None

    window = alignment[start_index : end_index + 1]
    if any(
        item.operation not in {AlignmentOperation.MATCH, AlignmentOperation.SUBSTITUTION}
        for item in window
    ):
        return None
    if any(item.asr_word is None or item.reference_word is None for item in window):
        return None
    start = window[0].asr_word.start
    end = window[-1].asr_word.end
    if end <= start or end - start > maximum_window_seconds:
        return None
    if any(
        current.asr_word.start < previous.asr_word.end
        for previous, current in zip(window, window[1:])
    ):
        return None

    signature = tuple(item.reference_word.normalized for item in window)
    reference_sequence = tuple(
        item.reference_word.normalized
        for item in alignment
        if item.reference_word is not None
    )
    occurrences = sum(
        reference_sequence[index : index + len(signature)] == signature
        for index in range(len(reference_sequence) - len(signature) + 1)
    )
    if occurrences != 1:
        return None

    text = " ".join(item.reference_word.display for item in window)
    return ForcedAlignmentContext(
        segment=ReferenceAlignmentSegment(text=text, start=start, end=end),
        candidate_offset=candidate_index - start_index,
    )


def _stable_match(token: AlignedToken) -> bool:
    return (
        token.operation is AlignmentOperation.MATCH
        and token.asr_word is not None
        and token.reference_word is not None
    )


class WhisperXReferenceAligner:
    """Offline forced alignment for already verified reference text.

    It returns only timestamps calculated by WhisperX's alignment model;
    callers must never copy timestamps from a substituted ASR word.
    """

    def __init__(
        self,
        *,
        language_code: str = "en",
        device: str = "cpu",
        python_executable: Path | None = None,
        repo_root: Path | None = None,
        timeout_seconds: float = 300.0,
    ) -> None:
        self._language_code = language_code
        self._device = device
        self._python_executable = python_executable
        self._repo_root = repo_root
        self._timeout_seconds = timeout_seconds
        self._model = None
        self._metadata = None

    def align(
        self,
        audio_path: Path,
        segments: Sequence[ReferenceAlignmentSegment],
    ) -> dict:
        if not audio_path.is_file():
            raise FileNotFoundError(f"Alignment audio not found: {audio_path}")
        if not segments:
            raise ValueError("At least one verified reference segment is required.")
        for segment in segments:
            if not segment.text.strip() or segment.end <= segment.start:
                raise ValueError("Reference alignment segments must be non-empty and timed.")

        if self._python_executable is not None:
            return self._align_in_subprocess(audio_path, segments)

        import whisperx

        if self._model is None or self._metadata is None:
            self._model, self._metadata = whisperx.load_align_model(
                language_code=self._language_code,
                device=self._device,
            )
        transcript = [
            {"text": segment.text, "start": segment.start, "end": segment.end}
            for segment in segments
        ]
        return whisperx.align(
            transcript,
            self._model,
            self._metadata,
            str(audio_path),
            self._device,
            return_char_alignments=False,
        )

    def _align_in_subprocess(
        self,
        audio_path: Path,
        segments: Sequence[ReferenceAlignmentSegment],
    ) -> dict:
        if self._repo_root is None:
            raise ValueError("Repository root is required for external alignment.")
        with tempfile.TemporaryDirectory(prefix="chordsync-alignment-") as directory:
            temporary_directory = Path(directory)
            request_path = temporary_directory / "request.json"
            output_path = temporary_directory / "result.json"
            request_path.write_text(
                json.dumps(
                    {
                        "audio_path": str(audio_path),
                        "language_code": self._language_code,
                        "device": self._device,
                        "segments": [
                            {
                                "text": segment.text,
                                "start": segment.start,
                                "end": segment.end,
                            }
                            for segment in segments
                        ],
                    }
                ),
                encoding="utf-8",
            )
            try:
                completed = subprocess.run(
                    [
                        str(self._python_executable),
                        "-m",
                        "analysis.lyrics.reference_alignment_cli",
                        "--request",
                        str(request_path),
                        "--output",
                        str(output_path),
                    ],
                    cwd=self._repo_root,
                    timeout=self._timeout_seconds,
                    capture_output=True,
                    text=True,
                    shell=False,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise RuntimeError("Reference alignment subprocess failed.") from error
            if completed.returncode != 0 or not output_path.is_file():
                raise RuntimeError("Reference alignment subprocess failed.")
            try:
                result = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise RuntimeError("Reference alignment result is malformed.") from error
            if not isinstance(result, dict):
                raise RuntimeError("Reference alignment result is malformed.")
            return result
