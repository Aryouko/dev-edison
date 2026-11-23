"""Audio effects (NumPy).

An audio effect processes the whole sound of a clip at once (a reverberation
or an echo needs what came before), then the result is kept in a cache
(see :mod:`edison.render.audio_effects`).
"""

import numpy as np

from edison.effects.base import AudioEffect, Param, register

FADE = "fade"  # stored as the fade_in / fade_out of the clip, not in its effect list


def _mix(dry: np.ndarray, wet: np.ndarray, amount: float) -> np.ndarray:
    return (dry * (1 - amount) + wet * amount).astype(np.float32)


def _fft_convolve(signal: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Convolution of each channel, truncated to the length of ``signal``."""
    size = 1 << (len(signal) + len(kernel) - 1).bit_length()
    spectrum = np.fft.rfft(signal, size, axis=0) * np.fft.rfft(kernel, size, axis=0)
    return np.fft.irfft(spectrum, size, axis=0)[:len(signal)]


def _rms(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(samples ** 2))) if len(samples) else 0.0


@register
class Reverb(AudioEffect):
    type_id = "reverb"
    label = "Réverbération"
    description = "Donne l'impression que le son résonne dans une pièce."
    params = (
        Param("size", "Taille de la pièce", 1.5, 0.2, 4.0, 0.1, suffix=" s"),
        Param("mix", "Mélange", 35, 0, 100, suffix=" %"),
    )

    def process(self, samples, values, sample_rate):
        length = int(values["size"] * sample_rate)
        if len(samples) == 0 or length < 2:
            return samples
        time = np.arange(length) / sample_rate
        rng = np.random.default_rng(7)
        # Impulse response: noise decaying by 60 dB over the size of the room
        response = rng.standard_normal((length, samples.shape[1])) * np.exp(-6.9 * time / values["size"])[:, None]
        wet = _fft_convolve(samples, response)
        level = _rms(wet)
        if level > 0:
            wet *= _rms(samples) / level
        return _mix(samples, wet, values["mix"] / 100)


@register
class Echo(AudioEffect):
    type_id = "echo"
    label = "Écho"
    description = "Répète le son avec un léger retard."
    params = (
        Param("delay", "Retard", 0.35, 0.05, 1.5, 0.05, suffix=" s"),
        Param("feedback", "Répétitions", 45, 0, 90, suffix=" %"),
        Param("mix", "Mélange", 50, 0, 100, suffix=" %"),
    )

    def process(self, samples, values, sample_rate):
        delay = int(values["delay"] * sample_rate)
        feedback = values["feedback"] / 100
        wet = np.zeros_like(samples)
        gain, offset = 1.0, delay
        while gain > 0.01 and 0 < offset < len(samples):  # each repetition is quieter
            wet[offset:] += samples[:len(samples) - offset] * gain
            gain *= feedback
            offset += delay
        return np.clip(samples + wet * values["mix"] / 100, -1, 1).astype(np.float32)


@register
class Pitch(AudioEffect):
    type_id = "pitch"
    label = "Hauteur (aigu / grave)"
    description = "Rend la voix plus aiguë ou plus grave sans changer la durée."
    params = (Param("semitones", "Demi-tons", 5, -12, 12),)

    FRAME = 2048
    HOP = 512

    def process(self, samples, values, sample_rate):
        ratio = 2 ** (values["semitones"] / 12)
        if abs(ratio - 1) < 1e-3 or len(samples) < self.FRAME * 2:
            return samples
        if np.array_equal(samples[:, 0], samples[:, 1]):  # mono sound: process one channel only
            return np.repeat(self._shift(samples[:, 0], ratio)[:, None], 2, axis=1)
        return np.stack([self._shift(channel, ratio) for channel in samples.T], axis=1)

    def _shift(self, channel: np.ndarray, ratio: float) -> np.ndarray:
        # Stretch the duration by ``ratio`` keeping the pitch, then replay faster/slower
        # to get back the original duration: only the pitch changes.
        stretched = self._time_stretch(channel, ratio)
        positions = np.linspace(0, len(stretched) - 1, len(channel))
        return np.clip(np.interp(positions, np.arange(len(stretched)), stretched), -1, 1).astype(np.float32)

    def _time_stretch(self, signal: np.ndarray, ratio: float) -> np.ndarray:
        """Phase vocoder: make ``signal`` ``ratio`` times longer without changing its pitch."""
        window = np.hanning(self.FRAME).astype(np.float32)
        padded = np.pad(signal.astype(np.float32), (self.FRAME, self.FRAME))
        count = (len(padded) - self.FRAME) // self.HOP
        frames = np.lib.stride_tricks.sliding_window_view(padded, self.FRAME)[::self.HOP][:count]
        spectra = np.fft.rfft(frames * window, axis=1)
        magnitudes = np.abs(spectra).astype(np.float32)  # computed once, then indexed
        phases = np.angle(spectra).astype(np.float32)
        steps = np.arange(0, count - 1, 1 / ratio)
        index = steps.astype(int)
        fraction = (steps - index).astype(np.float32)[:, None]
        magnitude = (1 - fraction) * magnitudes[index] + fraction * magnitudes[index + 1]
        expected = (2 * np.pi * self.HOP * np.arange(spectra.shape[1]) / self.FRAME).astype(np.float32)
        delta = phases[index + 1] - phases[index] - expected
        delta -= np.float32(2 * np.pi) * np.round(delta / np.float32(2 * np.pi))
        increments = np.vstack([np.zeros_like(expected), (expected + delta)[:-1]])
        phase = phases[0] + np.cumsum(increments, axis=0)
        output_frames = np.fft.irfft(magnitude * np.exp(1j * phase), self.FRAME, axis=1) * window
        output = np.zeros(len(steps) * self.HOP + self.FRAME)
        weights = np.zeros_like(output)
        for position, frame in enumerate(output_frames):  # overlap-add
            start = position * self.HOP
            output[start:start + self.FRAME] += frame
            weights[start:start + self.FRAME] += window ** 2
        output /= np.maximum(weights, 1e-6)
        return output[self.FRAME:len(output) - self.FRAME]


@register
class Fade(AudioEffect):
    """Fade in / fade out. Its values are stored on the clip (``fade_in``, ``fade_out``)."""

    type_id = FADE
    label = "Fondu entrant / sortant"
    description = "Le son apparaît et disparaît progressivement (0 s désactive le fondu)."
    params = (
        Param("fade_in", "Fondu entrant", 1.0, 0.0, 10.0, 0.1, suffix=" s"),
        Param("fade_out", "Fondu sortant", 1.0, 0.0, 10.0, 0.1, suffix=" s"),
    )

    def process(self, samples, values, sample_rate):
        return samples  # applied by the mixer through the clip fades
