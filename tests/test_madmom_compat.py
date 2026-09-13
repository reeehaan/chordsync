import collections
import collections.abc

import numpy as np

from analysis.beats import madmom_runner


def test_chordsync_applies_madmom_python_compatibility() -> None:
    assert collections.MutableSequence is collections.abc.MutableSequence
    assert madmom_runner.RNNBeatProcessor is not None
    assert madmom_runner.RNNDownBeatProcessor is not None


def test_chordsync_supports_madmom_ragged_downbeat_results() -> None:
    from madmom.features import downbeats

    results = [
        (np.array([1]), 1.0),
        (np.array([1, 2]), 2.0),
    ]

    converted = downbeats.np.asarray(results)

    assert converted.dtype == object
    assert converted[:, 1].tolist() == [1.0, 2.0]
