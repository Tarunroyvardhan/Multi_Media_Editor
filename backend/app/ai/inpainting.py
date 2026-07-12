"""Object removal (inpainting) using LaMa.

The model is loaded once at import time. Its checkpoint (~196MB) is
downloaded automatically by torch on first use and cached in
~/.cache/torch/hub/checkpoints/, so the first call will be slower.
"""
import threading

import cv2
import numpy as np
from PIL import Image

_simple_lama = None
_lock = threading.Lock()


def _get_lama():
    global _simple_lama
    if _simple_lama is None:
        with _lock:
            if _simple_lama is None:
                from simple_lama_inpainting import SimpleLama

                _simple_lama = SimpleLama()
    return _simple_lama


def remove_object(image_path: str, mask: np.ndarray, output_path: str) -> None:
    """mask is a uint8 array (0/255) the same height/width as the image at
    image_path. The masked region is inpainted and the result written to
    output_path."""
    lama = _get_lama()
    image = Image.open(image_path).convert("RGB")
    h, w = mask.shape

    # Segmentation tends to under-cover thin structures (leaves, hair,
    # wispy edges) — a raw click/box mask often misses these even though
    # they're part of the object. Dilate once, generously, and use that
    # same grown mask both as LaMa's input (more context to fill from) and
    # as the basis for the final composite, so the actual replaced region
    # extends past what SAM found rather than snapping back to it.
    kernel = np.ones((31, 31), np.uint8)
    effective_mask = cv2.dilate(mask, kernel, iterations=1)

    mask_img = Image.fromarray(effective_mask).convert("L")
    if mask_img.size != image.size:
        mask_img = mask_img.resize(image.size, Image.NEAREST)

    result = lama(image, mask_img)
    result_arr = np.array(result)[:h, :w].astype(np.float64)
    orig_arr = np.array(image).astype(np.float64)

    # Feather the effective (dilated) mask for a smooth blend at the edge —
    # composite using this, not the raw under-covering mask, so leaf/edge
    # pixels the segmentation missed still get replaced.
    feathered = cv2.GaussianBlur(effective_mask.astype(np.float64), (0, 0), sigmaX=4)
    alpha = np.clip(feathered / 255.0, 0, 1)[..., None]

    final = orig_arr * (1 - alpha) + result_arr * alpha
    Image.fromarray(final.astype(np.uint8)).save(output_path)