"""Storage of uploaded field photographs and generated image chips.

Files live under MEDIA_DIR/<kind>/ with random UUID names; no user-supplied names or paths are used.
Photos are decoded and re-encoded with Pillow, which validates the real format and drops EXIF data
(including GPS location).
"""

import io
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import get_settings

KINDS = ("photos", "chips", "heat")
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_PHOTO_EDGE = 2048
THUMB_EDGE = 480

Image.MAX_IMAGE_PIXELS = 40_000_000  # refuse decompression bombs


class PhotoError(ValueError):
    """Upload rejected; the message is suitable for display."""


def media_path(kind: str, name: str) -> Path:
    if kind not in KINDS:
        raise ValueError(kind)
    # Only plain generated names are valid ("<uuid>.<ext>"), never paths.
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError(name)
    folder = Path(get_settings().media_dir) / kind
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name


@dataclass
class SavedPhoto:
    file_name: str
    thumb_name: str
    width: int
    height: int
    size_bytes: int


def save_photo(data: bytes, original_name: str | None = None) -> SavedPhoto:
    s = get_settings()
    if not data:
        raise PhotoError(f"{original_name or 'The file'} is empty.")
    if len(data) > s.max_photo_bytes:
        raise PhotoError(f"{original_name or 'The photo'} is larger than {s.max_photo_bytes // (1024 * 1024)} MB.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            probe.verify()
        if fmt not in ALLOWED_FORMATS:
            raise PhotoError(f"{original_name or 'The file'} is not a JPEG, PNG or WebP image.")
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)  # honour camera orientation before dropping EXIF
        img = img.convert("RGB")
    except PhotoError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise PhotoError(f"{original_name or 'The file'} is not a readable image.") from exc

    img.thumbnail((MAX_PHOTO_EDGE, MAX_PHOTO_EDGE))
    stem = uuid.uuid4().hex
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85, optimize=True)  # no exif= argument: metadata is not written
    file_name = f"{stem}.jpg"
    media_path("photos", file_name).write_bytes(out.getvalue())

    thumb = img.copy()
    thumb.thumbnail((THUMB_EDGE, THUMB_EDGE))
    thumb_name = f"{stem}_t.jpg"
    tb = io.BytesIO()
    thumb.save(tb, "JPEG", quality=80)
    media_path("photos", thumb_name).write_bytes(tb.getvalue())
    return SavedPhoto(file_name, thumb_name, img.width, img.height, out.tell())


def delete_photo_files(*names: str) -> None:
    for n in names:
        try:
            media_path("photos", n).unlink(missing_ok=True)
        except ValueError:
            pass
