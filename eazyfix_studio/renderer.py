"""Pillow motion-graphics renderer used by both the interactive preview and export."""

from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .animations import clamp, eased, layer_state
from .models import Layer, Project, Scene


FONT_CANDIDATES = {
    "regular": [
        r"C:\Windows\Fonts\segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ],
    "bold": [
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ],
}


def _rgb(value: str, fallback: tuple[int, int, int] = (20, 24, 45)) -> tuple[int, int, int]:
    try:
        value = value.lstrip("#")
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))
    except (ValueError, AttributeError):
        return fallback


@lru_cache(maxsize=128)
def _font(size: int, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = FONT_CANDIDATES["bold" if bold else "regular"]
    for candidate in candidates:
        if os.path.isfile(candidate):
            try:
                return ImageFont.truetype(candidate, max(1, size))
            except OSError:
                continue
    return ImageFont.load_default()


@lru_cache(maxsize=64)
def _load_image(path: str) -> Image.Image:
    file_path = Path(path)
    if file_path.suffix.lower() == ".svg":
        try:
            from PySide6.QtCore import QSize
            from PySide6.QtGui import QImage, QPainter
            from PySide6.QtSvg import QSvgRenderer

            renderer = QSvgRenderer(str(file_path))
            if not renderer.isValid():
                raise RuntimeError("This SVG file could not be read.")
            original = renderer.defaultSize()
            ratio = original.width() / max(1, original.height())
            width = 1200 if ratio >= 1 else max(1, round(1200 * ratio))
            height = max(1, round(width / max(0.01, ratio)))
            image = QImage(QSize(width, height), QImage.Format.Format_ARGB32)
            image.fill(0)
            painter = QPainter(image)
            renderer.render(painter)
            painter.end()
            bits = image.bits()
            if hasattr(bits, "setsize"):
                bits.setsize(image.sizeInBytes())
            return Image.frombytes("RGBA", (width, height), bytes(bits), "raw", "BGRA")
        except ImportError as error:
            raise RuntimeError("SVG support needs the QtSvg component from PySide6.") from error
    return Image.open(file_path).convert("RGBA")


def _gradient(size: tuple[int, int], top: str, bottom: str, time: float) -> Image.Image:
    width, height = size
    first, last = _rgb(top, (9, 12, 30)), _rgb(bottom, (22, 27, 55))
    strip = Image.new("RGB", (1, max(1, height)))
    pixels = []
    for y in range(max(1, height)):
        t = y / max(1, height - 1)
        pixels.append(tuple(round(first[i] + (last[i] - first[i]) * t) for i in range(3)))
    strip.putdata(pixels)
    image = strip.resize(size, Image.Resampling.BILINEAR).convert("RGBA")

    # Soft animated indigo/cyan light blooms, calculated at quarter resolution.
    small_size = (max(1, width // 4), max(1, height // 4))
    glow = Image.new("RGBA", small_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    gx = int((0.72 + 0.12 * math.sin(time * 0.31)) * small_size[0])
    gy = int((0.17 + 0.08 * math.cos(time * 0.4)) * small_size[1])
    radius = max(10, int(min(small_size) * 0.55))
    draw.ellipse((gx - radius, gy - radius, gx + radius, gy + radius), fill=(82, 65, 240, 62))
    gx2 = int((0.08 + 0.08 * math.cos(time * 0.27)) * small_size[0])
    gy2 = int(0.76 * small_size[1])
    draw.ellipse((gx2 - radius, gy2 - radius, gx2 + radius, gy2 + radius), fill=(40, 166, 206, 28))
    glow = glow.filter(ImageFilter.GaussianBlur(max(3, radius // 2))).resize(size, Image.Resampling.BICUBIC)
    image.alpha_composite(glow)
    return image


def _draw_rounded(draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float], radius: int, color: str, outline: str = "") -> None:
    draw.rounded_rectangle(tuple(round(value) for value in box), radius=max(0, radius), fill=_rgb(color), outline=_rgb(outline) if outline else None, width=2 if outline else 1)


def _composite_clipped(canvas: Image.Image, layer: Image.Image, x: int, y: int) -> None:
    left, top = max(0, x), max(0, y)
    right, bottom = min(canvas.width, x + layer.width), min(canvas.height, y + layer.height)
    if right <= left or bottom <= top:
        return
    crop = layer.crop((left - x, top - y, right - x, bottom - y))
    canvas.alpha_composite(crop, (left, top))


def _draw_mockup(canvas: Image.Image, layer: Layer, box: tuple[float, float, float, float]) -> None:
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    pad = max(8, int(width * 0.04))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((left + 4, top + 12, right + 4, bottom + 12), radius=max(12, int(width * 0.04)), fill=(0, 0, 0))
    _draw_rounded(draw, box, int(width * 0.04), layer.background or "#F7F8FD")
    header_height = height * 0.16
    draw.rounded_rectangle((left, top, right, top + header_height * 1.4), radius=max(12, int(width * 0.04)), fill=(231, 234, 245))
    draw.rectangle((left, top + header_height, right, top + header_height * 1.4), fill=(231, 234, 245))
    for index, color in enumerate(((255, 105, 124), (255, 196, 83), (87, 213, 170))):
        center = (left + pad + index * pad * 0.8, top + header_height * 0.53)
        dot = max(4, int(width * 0.009))
        draw.ellipse((center[0] - dot, center[1] - dot, center[0] + dot, center[1] + dot), fill=color)
    text_left = left + pad * 1.1
    headline_font = _font(max(14, int(height * 0.12)), True)
    sub_font = _font(max(11, int(height * 0.052)), False)
    draw.text((text_left, top + header_height * 1.9), "YOUR BRAND", font=headline_font, fill=(32, 38, 59))
    lines = layer.text.splitlines() or ["Your digital experience"]
    for index, line in enumerate(lines[:2]):
        draw.text((text_left, top + header_height * (3.25 + index * 0.55)), line, font=sub_font, fill=(91, 102, 127))
    button_y = top + height * 0.68
    draw.rounded_rectangle((text_left, button_y, text_left + width * 0.32, button_y + height * 0.13), radius=max(6, int(width * 0.015)), fill=_rgb(layer.accent_color))
    # Decorative website cards and a small motion-inspired chart.
    card_y = top + height * 0.80
    card_w = (width - pad * 2 - pad) / 3
    for index in range(3):
        x = left + pad + index * (card_w + pad / 2)
        draw.rounded_rectangle((x, card_y, x + card_w, bottom - pad), radius=max(6, int(width * 0.014)), fill=((216, 227, 240), (242, 221, 207), (224, 225, 206))[index])
        draw.ellipse((x + card_w * 0.3, card_y + height * 0.035, x + card_w * 0.7, card_y + height * 0.12), fill=(107, 132, 164))


def _draw_layer(canvas: Image.Image, project: Project, layer: Layer, local_time: float, scale_x: float, scale_y: float) -> None:
    alpha, offset_x, offset_y, scale = layer_state(layer.animation, local_time - layer.start, layer.animation_duration)
    alpha *= clamp(layer.opacity)
    if alpha <= 0:
        return
    width, height = canvas.size
    center_x = (layer.x + offset_x) * width
    center_y = (layer.y + offset_y) * height
    box_width = layer.width * width * scale
    box_height = layer.height * height * scale
    box = (center_x - box_width / 2, center_y - box_height / 2, center_x + box_width / 2, center_y + box_height / 2)

    if layer.kind == "image":
        asset = next((item for item in project.assets if item.id == layer.asset_id), None)
        if not asset or not asset.use_in_video or not Path(asset.path).is_file():
            return
        try:
            image = _load_image(asset.path).copy()
        except (OSError, RuntimeError):
            return
        target_size = (max(1, int(box_width)), max(1, int(box_height)))
        if layer.fit == "contain":
            image.thumbnail(target_size, Image.Resampling.LANCZOS)
            frame = Image.new("RGBA", target_size, (0, 0, 0, 0))
            frame.alpha_composite(image, ((target_size[0] - image.width) // 2, (target_size[1] - image.height) // 2))
        else:
            ratio = max(target_size[0] / image.width, target_size[1] / image.height)
            resized = image.resize((max(1, round(image.width * ratio)), max(1, round(image.height * ratio))), Image.Resampling.LANCZOS)
            left = (resized.width - target_size[0]) // 2
            top = (resized.height - target_size[1]) // 2
            frame = resized.crop((left, top, left + target_size[0], top + target_size[1]))
        if alpha < 1:
            frame.putalpha(frame.getchannel("A").point(lambda value: round(value * alpha)))
        _composite_clipped(canvas, frame, round(box[0]), round(box[1]))
        return

    if layer.kind == "mockup":
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        _draw_mockup(overlay, layer, tuple(round(value) for value in box))
        if alpha < 1:
            overlay.putalpha(overlay.getchannel("A").point(lambda value: round(value * alpha)))
        canvas.alpha_composite(overlay)
        return

    if layer.kind == "shape":
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        radius = int(min(box_width, box_height) * layer.radius)
        draw.rounded_rectangle(tuple(round(value) for value in box), radius=radius, fill=(*_rgb(layer.background or layer.color), round(255 * alpha)))
        canvas.alpha_composite(overlay)
        return

    if layer.kind != "text":
        return
    font_size = max(12, int(layer.font_size * scale_y * scale))
    bold = True
    text = layer.text
    if layer.animation == "word_reveal" and text:
        words = text.split()
        visible = max(1, math.ceil(len(words) * clamp((local_time - layer.start) / max(0.1, layer.animation_duration))))
        text = " ".join(words[:visible])
    font = _font(font_size, bold)
    lines = text.splitlines() or [""]
    draw_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(draw_layer)
    line_height = font_size * 1.2
    total_height = line_height * len(lines)
    y = center_y - total_height / 2
    if layer.background:
        padding_x = max(8, int(width * 0.022))
        padding_y = max(6, int(height * 0.009))
        pill = (box[0] - padding_x, box[1] - padding_y, box[2] + padding_x, box[3] + padding_y)
        draw.rounded_rectangle(tuple(round(value) for value in pill), radius=max(8, int(height * layer.radius)), fill=(*_rgb(layer.background), round(225 * alpha)))
    for line in lines:
        while font_size > 10 and draw.textbbox((0, 0), line, font=font, stroke_width=1)[2] > box_width:
            font_size -= 1
            font = _font(font_size, bold)
        bounds = draw.textbbox((0, 0), line, font=font, stroke_width=max(0, int(font_size * 0.018)))
        text_width = bounds[2] - bounds[0]
        if layer.align == "left":
            x = box[0]
        elif layer.align == "right":
            x = box[2] - text_width
        else:
            x = center_x - text_width / 2
        fill = (*_rgb(layer.color, (247, 248, 255)), round(255 * alpha))
        stroke = (*_rgb("#070A16"), round(135 * alpha))
        draw.text((round(x - bounds[0]), round(y - bounds[1])), line, font=font, fill=fill, stroke_width=max(0, int(font_size * 0.018)), stroke_fill=stroke)
        y += line_height
    canvas.alpha_composite(draw_layer)


def _render_scene(project: Project, scene: Scene, local_time: float, size: tuple[int, int], absolute_time: float) -> Image.Image:
    canvas = _gradient(size, scene.background_top, scene.background_bottom, absolute_time)
    draw = ImageDraw.Draw(canvas, "RGBA")
    width, height = size
    # Subtle grid and small motes add depth without competing with typography.
    grid_spacing = max(32, int(width * 0.075))
    for x in range(-height, width + height, grid_spacing):
        draw.line((x, 0, x + int(height * 0.35), height), fill=(156, 167, 241, 10), width=1)
    for index in range(18):
        x = (index * 211 + int(18 * absolute_time)) % width
        y = (index * 379 + int(25 * absolute_time)) % height
        draw.ellipse((x, y, x + 2, y + 2), fill=(205, 221, 255, 60))
    for layer in scene.layers:
        _draw_layer(canvas, project, layer, local_time, width / project.width, height / project.height)
    return canvas.convert("RGB")


def render_frame(project: Project, time_seconds: float, size: tuple[int, int] | None = None) -> Image.Image:
    """Render a project frame for both live preview and encoded video."""
    project.validate()
    target_size = size or (project.width, project.height)
    if target_size[0] < 1 or target_size[1] < 1:
        raise ValueError("Render size must be positive.")
    time_seconds = clamp(time_seconds, 0.0, max(0.0, project.duration - 1 / project.fps))
    cursor = 0.0
    scene_index = len(project.scenes) - 1
    local_time = 0.0
    for index, scene in enumerate(project.scenes):
        if time_seconds < cursor + scene.duration or index == len(project.scenes) - 1:
            scene_index = index
            local_time = time_seconds - cursor
            break
        cursor += scene.duration
    current = project.scenes[scene_index]
    frame = _render_scene(project, current, local_time, target_size, time_seconds)
    transition = min(current.transition_duration, 0.8, current.duration * 0.35)
    if scene_index == 0 or current.transition == "cut" or transition <= 0 or local_time >= transition:
        return frame
    previous = project.scenes[scene_index - 1]
    previous_frame = _render_scene(project, previous, previous.duration, target_size, max(0, time_seconds - local_time))
    progress = eased(local_time / transition, "ease_in_out")
    if current.transition == "fade":
        return Image.blend(previous_frame, frame, progress)
    if current.transition == "push":
        shift = int(target_size[0] * progress)
        combined = Image.new("RGB", target_size)
        if shift < target_size[0]:
            combined.paste(previous_frame.crop((shift, 0, target_size[0], target_size[1])), (0, 0))
        if shift > 0:
            combined.paste(frame.crop((0, 0, shift, target_size[1])), (target_size[0] - shift, 0))
        return combined
    if current.transition == "wipe":
        combined = previous_frame.copy()
        edge = int(target_size[0] * progress)
        if edge:
            combined.paste(frame.crop((0, 0, edge, target_size[1])), (0, 0))
        return combined
    return frame
