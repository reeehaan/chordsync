import collections
import collections.abc

import numpy as np


class _MadmomNumpyCompat:
    """Delegate to NumPy with madmom's legacy ragged-array fallback."""

    def __getattr__(self, name: str):
        return getattr(np, name)

    def asarray(self, value, *args, **kwargs):
        try:
            return np.asarray(value, *args, **kwargs)
        except ValueError as error:
            if "dtype" in kwargs or "inhomogeneous shape" not in str(error):
                raise
            return np.asarray(value, *args, dtype=object, **kwargs)


def apply_madmom_compatibility() -> None:
    """Provide legacy aliases required by madmom 0.16.1."""
    collections.MutableSequence = collections.abc.MutableSequence

    np.int = int
    np.float = float
    np.bool = bool
    np.complex = complex
    np.object = object

    from madmom.features import downbeats

    if downbeats.np is np:
        downbeats.np = _MadmomNumpyCompat()
