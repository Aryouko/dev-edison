"""Video effects (OpenCV + NumPy).

Every size is relative to the picture width, so the preview (small pictures)
and the export (full size pictures) look the same. The pictures stay in uint8
and use OpenCV functions: they are much faster than float NumPy computations,
which matters for a smooth preview.
"""

import math

import cv2
import numpy as np

from edison.effects.base import Param, VideoEffect, register

COLORS = (("gold", "Or"), ("white", "Blanc"), ("lime", "Citron"), ("purple", "Violet"))
RGB = {"gold": (255, 214, 120), "white": (255, 255, 255), "lime": (225, 248, 37), "purple": (160, 90, 255)}


def _gray(frame: np.ndarray) -> np.ndarray:
    """Grey version of the picture, still with 3 channels."""
    return cv2.cvtColor(cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)


def _add_light(frame: np.ndarray, light: np.ndarray) -> np.ndarray:
    """Add a light layer (uint8 picture, black = no light) with a soft glow around it."""
    sigma = max(1.0, frame.shape[1] * 0.004)
    glow = cv2.GaussianBlur(light, (0, 0), sigma)
    return cv2.add(frame, cv2.addWeighted(light, 1.0, glow, 1.5, 0))


@register
class Blur(VideoEffect):
    type_id = "blur"
    label = "Flou"
    description = "Adoucit l'image."
    params = (Param("strength", "Intensité", 40, 0, 100, suffix=" %"),)

    def apply(self, frame, t, values, duration):
        sigma = values["strength"] / 100 * frame.shape[1] * 0.02
        return frame if sigma < 0.3 else cv2.GaussianBlur(frame, (0, 0), sigma)


@register
class Sparkles(VideoEffect):
    type_id = "sparkles"
    label = "Paillettes"
    description = "Des paillettes scintillent sur l'image."
    params = (
        Param("density", "Quantité", 40, 5, 150),
        Param("size", "Taille", 50, 10, 100, suffix=" %"),
        Param("color", "Couleur", "gold", choices=COLORS),
    )

    def apply(self, frame, t, values, duration):
        height, width = frame.shape[:2]
        rng = np.random.default_rng(2026)  # same sparkles on every frame, only their brightness changes
        count = int(values["density"])
        xs, ys = rng.random(count) * width, rng.random(count) * height
        phases, speeds, sizes = rng.random(count), 0.6 + rng.random(count) * 1.4, 0.5 + rng.random(count)
        brightness = np.clip(np.sin(2 * math.pi * (t * speeds + phases)), 0, 1) ** 2
        color = RGB[values["color"]]
        light = np.zeros((height, width, 3), dtype=np.uint8)
        base = width * 0.018 * values["size"] / 100
        for x, y, size, shine in zip(xs, ys, sizes, brightness):
            if shine < 0.05:
                continue
            radius = base * size * shine
            tone = tuple(float(c * shine) for c in color)
            thickness = max(1, int(radius / 5))
            center = (int(x), int(y))
            cv2.line(light, (int(x - radius), int(y)), (int(x + radius), int(y)), tone, thickness, cv2.LINE_AA)
            cv2.line(light, (int(x), int(y - radius)), (int(x), int(y + radius)), tone, thickness, cv2.LINE_AA)
            cv2.circle(light, center, max(1, int(radius / 3)), tone, -1, cv2.LINE_AA)
        return _add_light(frame, light)


@register
class ShootingStar(VideoEffect):
    type_id = "shooting_star"
    label = "Étoile filante"
    description = "Une étoile traverse l'écran en laissant une traînée."
    params = (
        Param("period", "Durée d'un passage", 2.0, 0.5, 6.0, 0.1, suffix=" s"),
        Param("direction", "Direction", "ltr", choices=(("ltr", "De gauche à droite"), ("rtl", "De droite à gauche"))),
        Param("color", "Couleur", "white", choices=COLORS),
    )

    TRAIL_SEGMENTS = 24

    def apply(self, frame, t, values, duration):
        height, width = frame.shape[:2]
        progress = (t % values["period"]) / values["period"]
        start, end = np.array([-0.1 * width, 0.12 * height]), np.array([1.1 * width, 0.55 * height])
        if values["direction"] == "rtl":
            start[0], end[0] = width - start[0], width - end[0]
        head = start + (end - start) * progress
        backward = (start - end) / np.linalg.norm(end - start)
        trail = width * 0.28
        color = RGB[values["color"]]
        light = np.zeros((height, width, 3), dtype=np.uint8)
        for index in range(self.TRAIL_SEGMENTS):  # the trail fades and thins out behind the head
            fade = 1 - index / self.TRAIL_SEGMENTS
            first = head + backward * trail * index / self.TRAIL_SEGMENTS
            second = head + backward * trail * (index + 1) / self.TRAIL_SEGMENTS
            thickness = max(1, int(width * 0.006 * fade))
            cv2.line(light, tuple(int(v) for v in first), tuple(int(v) for v in second),
                     tuple(float(c * fade ** 2) for c in color), thickness, cv2.LINE_AA)
        cv2.circle(light, tuple(int(v) for v in head), max(2, int(width * 0.007)), (255, 255, 255), -1, cv2.LINE_AA)
        return _add_light(frame, light)


@register
class Boing(VideoEffect):
    type_id = "boing"
    label = "Boing boing"
    description = "La caméra zoome en montant puis dézoome en redescendant, comme un rebond."
    params = (
        Param("amplitude", "Amplitude", 15, 2, 40, suffix=" %"),
        Param("frequency", "Rebonds par seconde", 1.5, 0.2, 5.0, 0.1),
    )

    def apply(self, frame, t, values, duration):
        height, width = frame.shape[:2]
        wave = math.sin(2 * math.pi * values["frequency"] * t)  # -1 (bas) .. 1 (haut)
        scale = 1 + values["amplitude"] / 100 * (wave + 1) / 2
        # The camera goes up while zooming in; the shift stays inside the zoom margin (no black edge).
        shift = (scale - 1) * height / 2 * wave
        matrix = np.array([[scale, 0, (1 - scale) * width / 2],
                           [0, scale, (1 - scale) * height / 2 + shift]], dtype=np.float32)
        return cv2.warpAffine(frame, matrix, (width, height), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REFLECT)


@register
class BlackAndWhite(VideoEffect):
    type_id = "black_and_white"
    label = "Noir et blanc"
    description = "Retire les couleurs."
    params = (Param("strength", "Intensité", 100, 0, 100, suffix=" %"),)

    def apply(self, frame, t, values, duration):
        mix = values["strength"] / 100
        return cv2.addWeighted(frame, 1 - mix, _gray(frame), mix, 0)


@register
class Saturation(VideoEffect):
    type_id = "saturation"
    label = "Saturation"
    description = "Rend les couleurs plus vives ou plus ternes."
    params = (Param("amount", "Saturation", 40, -100, 100, suffix=" %"),)

    def apply(self, frame, t, values, duration):
        # colour = grey + (colour - grey) x factor, computed with saturation to [0, 255]
        factor = 1 + values["amount"] / 100
        return cv2.addWeighted(frame, factor, _gray(frame), 1 - factor, 0)


@register
class ColorCorrection(VideoEffect):
    type_id = "color_correction"
    label = "Correction de couleur"
    description = "Règle la luminosité, le contraste et la température de l'image."
    params = (
        Param("brightness", "Luminosité", 0, -100, 100, suffix=" %"),
        Param("contrast", "Contraste", 0, -100, 100, suffix=" %"),
        Param("temperature", "Température", 0, -100, 100, suffix=" %"),
    )

    def apply(self, frame, t, values, duration):
        # One lookup table per channel: every pixel value is replaced by its corrected value.
        levels = np.arange(256, dtype=np.float32)
        levels = (levels - 128) * (1 + values["contrast"] / 100) + 128 + values["brightness"] / 100 * 128
        warmth = values["temperature"] / 100 * 40  # warm = more red, less blue
        table = np.stack([levels + warmth, levels, levels - warmth], axis=1)
        table = np.clip(table, 0, 255).astype(np.uint8).reshape(1, 256, 3)
        return cv2.LUT(frame, table)


@register
class Negative(VideoEffect):
    type_id = "negative"
    label = "Couleurs négatives"
    description = "Inverse les couleurs de l'image."

    def apply(self, frame, t, values, duration):
        return 255 - frame
