from pathlib import Path
from typing import Protocol

from analysis.fusion.models import SharedTimeline


class AnalysisProcessor(Protocol):
    def process(
        self, input_path: Path, *, source_title: str | None = None
    ) -> SharedTimeline: ...


class AnalysisProcessorUnavailableError(RuntimeError):
    pass


class UnavailableAnalysisProcessor:
    """Safe placeholder until the real isolated pipeline adapter is available."""

    def process(
        self, input_path: Path, *, source_title: str | None = None
    ) -> SharedTimeline:
        raise AnalysisProcessorUnavailableError(
            "No real analysis processor is configured."
        )
