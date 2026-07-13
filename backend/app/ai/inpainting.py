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

                # Forced to CPU: on GPUs with limited VRAM (4GB or less),
                # LaMa competing with SAM2 for the same memory during video
                # removal causes severe slowdown/thrashing, not just OOM.
                # LaMa is fast enough on CPU that this is worth the tradeoff.
                _simple_lama = SimpleLama(device="cpu")
    return _simple_lama


def remove_object_array(image_rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Core routine used by both photo and video removal. image_rgb is a
    uint8 HxWx3 RGB array, mask is a uint8 HxW array (0/255). Returns the
    result as a uint8 HxWx3 RGB array. See remove_object() below for the
    file-based version photos use, and video_inpainting.py for how video
    frames reuse this per-frame."""
    lama = _get_lama()
    image = Image.fromarray(image_rgb)
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
    orig_arr = image_rgb.astype(np.float64)

    # Feather the effective (dilated) mask for a smooth blend at the edge —
    # composite using this, not the raw under-covering mask, so leaf/edge
    # pixels the segmentation missed still get replaced.
    feathered = cv2.GaussianBlur(effective_mask.astype(np.float64), (0, 0), sigmaX=4)
    alpha = np.clip(feathered / 255.0, 0, 1)[..., None]

    final = orig_arr * (1 - alpha) + result_arr * alpha
    return final.astype(np.uint8)


def remove_object(image_path: str, mask: np.ndarray, output_path: str) -> None:
    """mask is a uint8 array (0/255) the same height/width as the image at
    image_path. The masked region is inpainted and the result written to
    output_path."""
    image_rgb = np.array(Image.open(image_path).convert("RGB"))
    final = remove_object_array(image_rgb, mask)
    Image.fromarray(final).save(output_path)