"""Text recognition with Windows OCR (Windows.Media.Ocr). See ocr_mac for macOS.

recognize() returns lines in the same form as ocr_mac.recognize. Windows OCR
gives one reading per line (no alternatives) and a box per word; a line box
is the union of its word boxes.

The winrt packages load on first use, so this module imports on any system
(the tests check words_to_line everywhere).

Every WinRT call runs on one worker thread. A blocking .get() fails on a
single-threaded COM apartment, which the Tk thread may be ("Test detection"
reads text there); the worker is in the multi-threaded one that pywinrt sets
up when it loads. One thread also keeps calls to the engine from overlapping.
"""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

Box = tuple[int, int, int, int]  # x0, y0, x1, y1 in image pixels
RawLine = tuple[float, str, "Box | None", Box, tuple[str, ...]]
Word = tuple[str, tuple[float, float, float, float]]  # text, (x, y, width, height)

# NOT MEASURED YET: Windows OCR misses small text more than Vision does, so
# images shorter than this are scaled up first. A bait strip is 6% of the
# window height: 43 px at 720p, so it is read at about 2.8x there.
MIN_HEIGHT_PX = 120

_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")
_engine = None


class OcrUnavailable(Exception):
    """Windows has no text recognition for a usable language. Ends the run."""


def _load_engine():
    """The OCR engine, made on first use. Runs on the worker thread only."""
    global _engine
    if _engine is None:
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine

        engine = OcrEngine.try_create_from_language(Language("en-US"))
        if engine is None:
            engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            raise OcrUnavailable(
                "Windows text recognition is not installed. Add English (United States) under "
                "Settings > Time & language > Language & region, then start the macro again.")
        _engine = engine
    return _engine


def words_to_line(words: list[Word], span_of: Callable[[str], tuple[int, int] | None],
                  height: float, scale: float) -> RawLine | None:
    """One recognised line from its words, boxes mapped back by 1/scale."""
    if not words:
        return None
    text = " ".join(t for t, _ in words)
    spans = []
    pos = 0
    for t, (x, y, w, h) in words:
        spans.append((pos, pos + len(t), (x, y, x + w, y + h)))
        pos += len(t) + 1

    def union(boxes) -> Box:
        x0 = min(b[0] for b in boxes) / scale
        y0 = min(b[1] for b in boxes) / scale
        x1 = max(b[2] for b in boxes) / scale
        y1 = max(b[3] for b in boxes) / scale
        return int(x0), int(y0), int(x1), int(y1)

    line_box = union([b for _, _, b in spans])
    span_box = None
    span = span_of(text)
    if span is not None:
        hit = [b for s, e, b in spans if s < span[1] and e > span[0]]
        if hit:
            span_box = union(hit)
    centre = (line_box[1] + line_box[3]) / 2
    return abs(centre / max(1.0, height) - 0.5), text, span_box, line_box, ()


def recognize(image: np.ndarray, span_of: Callable[[str], tuple[int, int] | None]) -> list[RawLine]:
    """Each text line Windows OCR finds in the image."""
    return _worker.submit(_recognize, image, span_of).result()


def _recognize(image: np.ndarray, span_of: Callable[[str], tuple[int, int] | None]) -> list[RawLine]:
    engine = _load_engine()
    from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter

    H, W = image.shape[:2]
    scale = max(1.0, MIN_HEIGHT_PX / max(1, H))
    limit = float(OcrEngine.max_image_dimension)
    scale = min(scale, limit / max(W, H))
    img = image if scale == 1.0 else cv2.resize(
        image, (max(1, round(W * scale)), max(1, round(H * scale))),
        interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)
    bgra = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2BGRA))
    h, w = bgra.shape[:2]
    writer = DataWriter()
    writer.write_bytes(bgra.tobytes())
    bitmap = SoftwareBitmap.create_copy_from_buffer(
        writer.detach_buffer(), BitmapPixelFormat.BGRA8, w, h, BitmapAlphaMode.PREMULTIPLIED)
    result = engine.recognize_async(bitmap).get()
    out = []
    for line in result.lines:
        words = []
        for word in line.words:
            r = word.bounding_rect
            words.append((str(word.text), (float(r.x), float(r.y), float(r.width), float(r.height))))
        raw = words_to_line(words, span_of, H, scale)
        if raw is not None:
            out.append(raw)
    return out
