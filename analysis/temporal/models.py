from pydantic import BaseModel


class TimelineEvent(BaseModel):
    time: float
    beat_number: int | None = None
    is_downbeat: bool = False
    chord: str


class Bar(BaseModel):
    bar_number: int
    start_time: float
    end_time: float
    beats: list[TimelineEvent]
