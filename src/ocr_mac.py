"""Text recognition with Apple's Vision (macOS). See ocr_win for Windows.

recognize() returns each text line as (distance of its centre from the image
centre as a fraction of the height, text, span box, line box, other readings).
The span box is the box of the characters span_of(text) names, or None.
"""
from __future__ import annotations

from collections.abc import Callable

import cv2
import numpy as np
import objc

# Bound at import: PyObjC's lazy first load is not thread-safe (see focus_mac).
from Foundation import NSData, NSDictionary, NSMakeRange
from Vision import VNImageRequestHandler, VNRecognizeTextRequest, VNRequestTextRecognitionLevelAccurate

Box = tuple[int, int, int, int]  # x0, y0, x1, y1 in image pixels
RawLine = tuple[float, str, "Box | None", Box, tuple[str, ...]]

# Vision's next-best readings of a line, tried when the best one has no count.
TEXT_CANDIDATES = 3


def recognize(image: np.ndarray, span_of: Callable[[str], tuple[int, int] | None]) -> list[RawLine]:
    """Each text line Vision finds in the image.

    Vision can only give a substring's box while its results are alive, so
    the span box is found here.
    """
    # No upscaling: on 2026-10-24 the panel strip read correctly at 0.5x, 0.75x
    # and 1x, but not at 1.2x or 2x.
    ok, png = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("could not encode the image for text recognition")
    raw = png.tobytes()
    H, W = image.shape[:2]
    out = []
    with objc.autorelease_pool():
        data = NSData.dataWithBytes_length_(raw, len(raw))
        # A Python {} raises "key does not exist" with pyobjc 12 on macOS 27.
        handler = VNImageRequestHandler.alloc().initWithData_options_(data, NSDictionary.dictionary())
        req = VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(VNRequestTextRecognitionLevelAccurate)
        req.setUsesLanguageCorrection_(False)
        # English only: with the default, digits came back as Cyrillic letters.
        req.setRecognitionLanguages_(["en-US"])
        ok, err = handler.performRequests_error_([req], None)
        if not ok:
            # 2026-11-08: Vision failed every read with an e5rtError until the Mac restarted.
            why = err.localizedDescription() if err else "no reason given"
            raise RuntimeError(f"macOS text recognition failed ({why}); restart the Mac if it keeps failing")
        for obs in req.results() or []:
            top = obs.topCandidates_(TEXT_CANDIDATES)
            if not top:
                continue
            text = str(top[0].string())
            alts = tuple(str(c.string()) for c in list(top)[1:])
            box = obs.boundingBox()  # normalised, origin at the bottom left
            centre = box.origin.y + box.size.height / 2
            line_box = (int(box.origin.x * W), int((1 - box.origin.y - box.size.height) * H),
                        int((box.origin.x + box.size.width) * W), int((1 - box.origin.y) * H))
            span_box = None
            span = span_of(text)
            if span is not None:
                sub, _ = top[0].boundingBoxForRange_error_(NSMakeRange(span[0], span[1] - span[0]), None)
                if sub is not None:
                    b = sub.boundingBox()  # normalised, origin at the bottom left
                    span_box = (int(b.origin.x * W), int((1 - b.origin.y - b.size.height) * H),
                                int((b.origin.x + b.size.width) * W), int((1 - b.origin.y) * H))
            out.append((abs(centre - 0.5), text, span_box, line_box, alts))
    return out
