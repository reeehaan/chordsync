from pydantic import BaseModel

from analysis.lyrics.models import LyricSegment
from analysis.temporal.models import Bar


class SharedTimeline(BaseModel):
    schema_version: int
    bpm: float
    beats_per_bar: int
    beat_source: str
    lyric_source: str
    bars: list[Bar]
    lyrics: list[LyricSegment]
