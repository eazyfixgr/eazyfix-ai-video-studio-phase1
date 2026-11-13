"""Prepare user-approved image copies for vision requests without changing originals."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import base64

from PIL import Image, ImageOps


MAX_IMAGE_DATA_BYTES = 4 * 1024 * 1024
MAX_EDGE = 1600


def image_data_url(path: str | Path) -> str:
    file_path = Path(path)
    if not file_path.is_file():
        raise ValueError(f"An approved image is missing: {file_path.name}")
    if file_path.suffix.casefold() == ".svg":
        from ..renderer import _load_image

        image = _load_image(str(file_path)).copy()
        source_format = "PNG"
    else:
        with Image.open(file_path) as opened:
            opened.seek(0)
            image = ImageOps.exif_transpose(opened).copy()
            source_format = (opened.format or file_path.suffix.lstrip(".")).upper()
    image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
    has_alpha = image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info)
    keep_png = has_alpha and source_format in {"PNG", "GIF", "WEBP"}
    for edge, quality in ((MAX_EDGE, 84), (1200, 76), (900, 66)):
        prepared = image.copy()
        prepared.thumbnail((edge, edge), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        if keep_png:
            prepared.convert("RGBA").save(buffer, format="PNG", optimize=True)
            mime = "image/png"
        else:
            if prepared.mode in {"RGBA", "LA"} or (prepared.mode == "P" and "transparency" in prepared.info):
                rgba = prepared.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                prepared = background
            else:
                prepared = prepared.convert("RGB")
            prepared.save(buffer, format="JPEG", quality=quality, optimize=True)
            mime = "image/jpeg"
        encoded = buffer.getvalue()
        if len(encoded) <= MAX_IMAGE_DATA_BYTES:
            return f"data:{mime};base64,{base64.b64encode(encoded).decode('ascii')}"
    raise ValueError(f"{file_path.name} is too large for inline image analysis.")
