from pydantic import BaseModel


class ChordSegment(BaseModel):
    start: float
    end: float
    raw_label: str
    normalized_label: str
    source: str
