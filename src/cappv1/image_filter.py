import io

import imagehash
from PIL import Image


def image_size_px(image_bytes: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(image_bytes)) as img:
        return img.size


def is_too_small(image_bytes: bytes, min_size_px: int) -> bool:
    try:
        width, height = image_size_px(image_bytes)
    except Exception:
        # unreadable/corrupt image data - treat as non-captionable
        return True
    return width < min_size_px or height < min_size_px


def perceptual_hash(image_bytes: bytes) -> str | None:
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            return str(imagehash.phash(img))
    except Exception:
        return None
