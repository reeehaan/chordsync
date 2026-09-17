from pathlib import Path
from typing import Protocol

from analysis.fusion.models import SharedTimeline


class AnalysisProcessor(Protocol):
    def process(self, input_path: Path) -> SharedTimeline: ...


class AnalysisProcessorUnavailableError(RuntimeError):
    pass


class UnavailableAnalysisProcessor:
    """Safe placeholder until the real isolated pipeline adapter is available."""

    def process(self, input_path: Path) -> SharedTimeline:
        raise AnalysisProcessorUnavailableError(
            "No real analysis processor is configured."
        )
