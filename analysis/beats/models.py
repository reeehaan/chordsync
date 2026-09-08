from pydantic import BaseModel


class BeatEvent(BaseModel):
    time: float
    beat_number: int | None = None
    is_downbeat: bool = False
    source: str


class BeatGrid(BaseModel):
    bpm: float
    beats_per_bar: int
    beats: list[BeatEvent]
    source: str
