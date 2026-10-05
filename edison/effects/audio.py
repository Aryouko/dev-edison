"""Audio effects (NumPy), CDC "Pop-up effets" > "Audio".

An audio effect receives the whole sound of a clip (see ``AudioEffect.process``).
As it can be slow, compute it in a background thread and keep the result in a cache
(sprint S5), the audio callback of the player only reads the result.

Copy the structure of ``edison/effects/video.py`` (``@register`` + ``Param``).
"""

# TODO(S5) — the audio effects of the CDC:
#
# * Réverbération ("reverb"): convolve the sound with an impulse response (random noise
#   decaying exponentially over the "taille de la pièce"); FFT convolution with
#   np.fft.rfft / irfft; mix the result with the original sound ("mélange").
# * Écho ("echo"): add copies of the sound shifted by the "retard", each one quieter
#   ("répétitions" = gain applied at each repetition).
# * Fondu entrant / sortant ("fade"): it is already stored on the clip (Clip.fade_in,
#   Clip.fade_out) and applied by mix_audio; the pop-up only has to edit these two values.
# * Modification de la hauteur ("pitch", aigu / grave) without changing the duration:
#   time-stretch the sound with a phase vocoder (STFT), then resample it to its original
#   length with np.interp.
