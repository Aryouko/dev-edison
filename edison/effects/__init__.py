"""Effect plugins. Importing this package registers every effect."""

from edison.effects import audio, video  # imported to register the effects
from edison.effects.base import AUDIO, VIDEO, AudioEffect, Effect, Param, VideoEffect, effects_of, get_effect

__all__ = ["audio", "video", "AUDIO", "VIDEO", "AudioEffect", "Effect", "Param", "VideoEffect", "effects_of", "get_effect"]
