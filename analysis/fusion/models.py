from enum import Enum

from pydantic import BaseModel, Field

from analysis.lyrics.models import LyricSegment
from analysis.temporal.models import Bar


class PracticeMode(str, Enum):
    MUSIC_ONLY = "music_only"


class PracticeRegion(BaseModel):
    start: float
    end: float
    mode: PracticeMode


class SharedTimeline(BaseModel):
    schema_version: int
    bpm: float
    beats_per_bar: int
    beat_source: str
    lyric_source: str
    bars: list[Bar]
    lyrics: list[LyricSegment]
    practice_regions: list[PracticeRegion] = Field(default_factory=list)
