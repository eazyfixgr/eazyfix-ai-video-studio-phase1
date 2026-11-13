"""Small reusable motion primitives shared by the preview and final renderer."""

from __future__ import annotations

import math


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def eased(value: float, curve: str = "ease_out") -> float:
    t = clamp(value)
    if curve == "linear":
        return t
    if curve == "ease_in":
        return t * t * t
    if curve == "ease_in_out":
        return t * t * (3 - 2 * t)
    if curve == "spring":
        return 1 + (2.1 ** (-10 * t)) * math.sin((t - 0.11) * math.pi * 3.5) * 0.42 if t < 1 else 1
    return 1 - (1 - t) ** 3


def layer_state(animation: str, local_time: float, duration: float) -> tuple[float, float, float, float]:
    """Return alpha, x-offset, y-offset, and scale for an entering layer."""
    if local_time < 0:
        return 0.0, 0.0, 0.0, 1.0
    progress = eased(local_time / max(0.05, duration), "spring" if animation == "spring" else "ease_out")
    alpha = clamp(local_time / max(0.1, duration * 0.6))
    if animation == "fade":
        return alpha, 0.0, 0.0, 1.0
    if animation == "fade_up":
        return alpha, 0.0, (1.0 - progress) * 0.055, 1.0
    if animation == "slide_left":
        return alpha, (1.0 - progress) * 0.09, 0.0, 1.0
    if animation == "zoom":
        return alpha, 0.0, 0.0, 0.82 + 0.18 * progress
    if animation == "spring":
        return alpha, 0.0, (1.0 - progress) * 0.04, 0.85 + 0.15 * progress
    return 1.0, 0.0, 0.0, 1.0
