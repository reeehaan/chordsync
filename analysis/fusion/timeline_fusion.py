from analysis.beats.models import BeatGrid
from analysis.fusion.models import PracticeRegion, SharedTimeline
from analysis.lyrics.models import LyricTranscript
from analysis.temporal.models import Bar


def build_shared_timeline(
    beat_grid: BeatGrid,
    bars: list[Bar],
    lyrics: LyricTranscript,
    practice_regions: list[PracticeRegion] | None = None,
) -> SharedTimeline:
    return SharedTimeline(
        schema_version=1,
        bpm=beat_grid.bpm,
        beats_per_bar=beat_grid.beats_per_bar,
        beat_source=beat_grid.source,
        lyric_source=lyrics.source,
        bars=bars,
        lyrics=lyrics.segments,
        practice_regions=practice_regions or [],
    )
