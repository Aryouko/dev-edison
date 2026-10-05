"""Video effects (OpenCV + NumPy), CDC "Pop-up effets" > "Vidéo".

``Negative`` below is a complete example to copy. The other effects of the CDC are
listed at the end of the file, with implementation hints.

Performance: the preview calls the effects for every frame (~30 per second).
Keep the pictures in uint8 and prefer OpenCV functions (``cv2.GaussianBlur``,
``cv2.addWeighted``, ``cv2.LUT``, ``cv2.warpAffine``...) to float NumPy computations.
"""

from edison.effects.base import VideoEffect, register


@register
class Negative(VideoEffect):
    """Example of a complete effect: no parameter, one line of computation."""

    type_id = "negative"
    label = "Couleurs négatives"
    description = "Inverse les couleurs de l'image."

    def apply(self, frame, t, values, duration):
        return 255 - frame


# TODO(S5) — the other video effects of the CDC. For each one: a class like ``Negative``,
# its parameters in ``params = (Param(...), ...)`` and the computation in ``apply``.
#
# * Flou ("blur"): Param intensité 0-100 %; cv2.GaussianBlur(frame, (0, 0), sigma) with a
#   sigma proportional to the width (e.g. intensité / 100 * width * 0.02).
# * Paillettes ("sparkles"): small bright crosses at fixed random positions
#   (np.random.default_rng(seed)) whose brightness blinks with t; draw them on a black
#   layer (cv2.line, cv2.circle), blur the layer for a glow, add it with cv2.add.
# * Étoile filante ("shooting_star"): a head moving across the screen during a period,
#   followed by a trail that fades out (several cv2.line of decreasing brightness).
# * Boing boing ("boing"): the camera zooms in while going up and zooms out while going
#   down: wave = sin(2π f t); scale = 1 + amplitude * (wave + 1) / 2; vertical shift
#   = (scale - 1) * height / 2 * wave; apply with cv2.warpAffine.
# * Noir et blanc ("black_and_white"): cv2.cvtColor to grey and back to 3 channels,
#   mixed with the original by cv2.addWeighted (intensité).
# * Effet trou noir ("black_hole"): to define (cv2.remap with a spiral distortion?).
# * Saturation ("saturation"): cv2.addWeighted(frame, k, grey, 1 - k, 0) with k = 1 + amount.
# * Correction de couleur ("color_correction"): luminosité, contraste, température;
#   build a lookup table of 256 values per channel and apply it with cv2.LUT.
