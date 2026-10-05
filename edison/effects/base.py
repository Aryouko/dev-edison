"""Base classes of the effect plugins and their registry (CDC "Effets = plugins").

An effect declares its parameters with :class:`Param`; the settings panel of the
effects pop-up is generated from these declarations. To add an effect, write a
subclass of :class:`VideoEffect` or :class:`AudioEffect` decorated with
:func:`register` in ``video.py`` or ``audio.py``: nothing else has to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

VIDEO = "video"
AUDIO = "audio"


@dataclass(frozen=True)
class Param:
    """Declaration of an effect parameter.

    Parameters
    ----------
    name : str
        Key in the saved parameters.
    label : str
        Name shown to the user.
    default : float or str
        Default value.
    minimum, maximum, step : float
        Range of a numeric parameter (shown as a slider).
    suffix : str
        Unit shown after the value (" %", " s"...).
    choices : tuple of (str, str)
        ``(value, label)`` pairs: the parameter becomes a list of choices instead of a number.
    """

    name: str
    label: str
    default: float | str
    minimum: float = 0.0
    maximum: float = 100.0
    step: float = 1.0
    suffix: str = ""
    choices: tuple = field(default_factory=tuple)

    def clamp(self, value):
        """Return a valid value (the default if ``value`` is unusable)."""
        if self.choices:
            return value if value in {choice for choice, _ in self.choices} else self.default
        try:
            return min(max(float(value), self.minimum), self.maximum)
        except (TypeError, ValueError):
            return self.default


class Effect:
    """Base class of every effect.

    Attributes
    ----------
    type_id : str
        Identifier saved in the project files (never change it once used).
    label : str
        Name shown in the effects pop-up.
    description : str
        One sentence shown in the effects pop-up.
    kind : str
        ``VIDEO`` or ``AUDIO``.
    params : tuple of Param
        Settings of the effect.
    """

    type_id = ""
    label = ""
    description = ""
    kind = VIDEO
    params: tuple[Param, ...] = ()

    def values(self, params: dict) -> dict:
        """Complete saved parameters with the defaults and clamp them to their range."""
        return {param.name: param.clamp(params.get(param.name, param.default)) for param in self.params}

    def defaults(self) -> dict:
        """Default parameters."""
        return {param.name: param.default for param in self.params}


class VideoEffect(Effect):
    """Effect applied to the pictures."""

    kind = VIDEO

    def apply(self, frame: np.ndarray, t: float, values: dict, duration: float) -> np.ndarray:
        """Transform a picture.

        Parameters
        ----------
        frame : numpy.ndarray
            RGB picture ``(height, width, 3)``, uint8. Express every size relative to the
            picture width: the preview (small pictures) and the export (full size) then match.
        t : float
            Time since the beginning of the clip, in seconds (for animated effects).
        values : dict
            Parameters returned by :meth:`values`.
        duration : float
            Length of the clip, in seconds.

        Returns
        -------
        numpy.ndarray
            Transformed RGB picture of the same size, uint8.
        """
        raise NotImplementedError


class AudioEffect(Effect):
    """Effect applied to the sound of a whole clip."""

    kind = AUDIO

    def process(self, samples: np.ndarray, values: dict, sample_rate: int) -> np.ndarray:
        """Transform the samples of a clip.

        Parameters
        ----------
        samples : numpy.ndarray
            Float samples ``(count, channels)`` of the WHOLE clip: a reverberation or an echo
            needs what came before, so the sound cannot be processed block by block.
        values : dict
            Parameters returned by :meth:`values`.
        sample_rate : int
            Samples per second.

        Returns
        -------
        numpy.ndarray
            Transformed samples of the same shape.
        """
        raise NotImplementedError


_REGISTRY: dict[str, Effect] = {}


def register(cls):
    """Class decorator adding an effect to the registry (Factory)."""
    _REGISTRY[cls.type_id] = cls()
    return cls


def get_effect(type_id: str) -> Effect | None:
    """Return the effect of this identifier (None if unknown, e.g. a file from a newer version)."""
    return _REGISTRY.get(type_id)


def effects_of(kind: str) -> list[Effect]:
    """Return the effects of a kind, in declaration order (order of the pop-up list)."""
    return [effect for effect in _REGISTRY.values() if effect.kind == kind]
