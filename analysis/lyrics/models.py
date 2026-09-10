from pydantic import BaseModel


class LyricWord(BaseModel):
    start: float
    end: float
    text: str


class LyricSegment(BaseModel):
    start: float
    end: float
    text: str
    words: list[LyricWord]


class LyricTranscript(BaseModel):
    language: str
    segments: list[LyricSegment]
    source: str
