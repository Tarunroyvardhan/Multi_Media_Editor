"""Object segmentation using MobileSAM.

The model is loaded once at import time (a few hundred ms) and reused
across requests. Each call to generate_mask() re-encodes the input image
(~1-3s on CPU) before running the prompt, since MobileSAM's predictor
needs a fresh image embedding per image.
"""
import os
import threading
from typing import List, Optional, Tuple

import cv2
import numpy as np
import torch

from app.config import settings

_predictor = None
_lock = threading.Lock()


def _get_predictor():
    global _predictor
    if _predictor is None:
        with _lock:
            if _predictor is None:
                from mobile_sam import sam_model_registry, SamPredictor

                checkpoint_path = os.path.join(settings.ai_models_dir, "mobile_sam.pt")
                if not os.path.exists(checkpoint_path):
                    raise RuntimeError(
                        f"MobileSAM checkpoint not found at {checkpoint_path}. "
                        "Run `python download_ai_models.py` in the backend folder first."
                    )
                sam = sam_model_registry["vit_t"](checkpoint=checkpoint_path)
                device = "cuda" if torch.cuda.is_available() else "cpu"
                sam.to(device=device)
                sam.eval()
                _predictor = SamPredictor(sam)
    return _predictor


def generate_mask(
    image_path: str,
    points: Optional[List[Tuple[int, int]]] = None,
    box: Optional[Tuple[int, int, int, int]] = None,
) -> Tuple[np.ndarray, float]:
    """Returns (binary_mask, score). binary_mask is a uint8 array of 0/255
    the same height/width as the input image. Exactly one of points or box
    should be provided."""
    predictor = _get_predictor()

    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        raise ValueError(f"Could not read image at {image_path}")
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    predictor.set_image(img_rgb)

    kwargs = {"multimask_output": True}
    if points:
        kwargs["point_coords"] = np.array(points)
        kwargs["point_labels"] = np.ones(len(points), dtype=np.int32)
    if box:
        kwargs["box"] = np.array(box)

    masks, scores, _ = predictor.predict(**kwargs)
    areas = masks.reshape(masks.shape[0], -1).sum(axis=1)
    total_pixels = masks.shape[1] * masks.shape[2]
    fractions = areas / total_pixels

    # Prefer the largest mask, but only among candidates that look like a
    # plausible single object (not a tiny fragment, not most of the frame —
    # which usually means "background" got selected instead of the object).
    valid = np.where((fractions >= 0.002) & (fractions <= 0.5))[0]
    if len(valid) > 0:
        best_idx = int(valid[np.argmax(areas[valid])])
    else:
        best_idx = int(np.argmax(areas))

   

    mask = (masks[best_idx].astype(np.uint8)) * 255
    return mask, float(scores[best_idx])


def mask_to_overlay_png_bytes(mask: np.ndarray) -> bytes:
    """Encodes a translucent red PNG overlay (same size as mask) highlighting
    the masked region, for previewing on top of the original image."""
    h, w = mask.shape
    overlay = np.zeros((h, w, 4), dtype=np.uint8)
    overlay[..., 0] = 80    # B
    overlay[..., 1] = 40    # G
    overlay[..., 2] = 255   # R
    overlay[..., 3] = (mask > 0).astype(np.uint8) * 140  # alpha where masked

    success, buf = cv2.imencode(".png", overlay)
    if not success:
        raise RuntimeError("Failed to encode mask overlay")
    return buf.tobytes()