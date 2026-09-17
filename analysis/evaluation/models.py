from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class EvaluationTrack(BaseModel):
    model_config = ConfigDict(frozen=True)

    track_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    audio_path: Path
    reference_lab_path: Path
    metadata: dict[str, str] | None = None


class NoChordEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True)

    reference_duration: float
    estimated_duration: float
    correct_duration: float
    precision: float
    recall: float


class EstimatorEvaluationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    estimator: str
    version: str
    duration: float
    root_score: float
    majmin_score: float
    triad_score: float
    no_chord: NoChordEvaluation
    runtime_seconds: float
    runtime_scope: str
    segment_count: int
    checkpoint_sha256: str | None = None


class TrackComparisonResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    track_id: str
    duration: float
    preprocessing_seconds: float
    normalization: str
    chordino: EstimatorEvaluationResult
    btc: EstimatorEvaluationResult
