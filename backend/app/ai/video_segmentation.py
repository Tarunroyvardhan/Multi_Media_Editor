"""Video object segmentation and mask tracking using SAM2.

Unlike MobileSAM (single image), SAM2's video predictor can propagate a
mask given on one frame across an entire video automatically. A SAM2
"inference state" is a live in-memory object (it holds frame embeddings)
that can't be saved to disk between HTTP requests, so we keep a small
in-memory session cache here: /segment stores the state, keyed by
mask_id, and /remove-object looks it up and consumes it.
"""
import os
import threading
import uuid
from typing import List, Optional, Tuple

import numpy as np

from app.config import settings

_predictor = None
_predictor_lock = threading.Lock()

_sessions = {}
_sessions_lock = threading.Lock()

SAM2_CONFIG = "configs/sam2.1/sam2.1_hiera_t.yaml"
SAM2_CHECKPOINT_NAME = "sam2.1_hiera_tiny.pt"


def _get_predictor():
    global _predictor
    if _predictor is None:
        with _predictor_lock:
            if _predictor is None:
                import torch
                from sam2.build_sam import build_sam2_video_predictor

                checkpoint_path = os.path.join(settings.ai_models_dir, SAM2_CHECKPOINT_NAME)
                if not os.path.exists(checkpoint_path):
                    raise RuntimeError(
                        f"SAM2 checkpoint not found at {checkpoint_path}. "
                        "Run `python download_video_ai_models.py` in the backend folder first."
                    )
                device = "cuda" if torch.cuda.is_available() else "cpu"
                _predictor = build_sam2_video_predictor(SAM2_CONFIG, checkpoint_path, device=device)
    return _predictor


def segment_first_frame(
    frames_dir: str,
    owner_id: int,
    media_id: int,
    points: Optional[List[Tuple[int, int]]] = None,
    box: Optional[Tuple[int, int, int, int]] = None,
) -> Tuple[str, np.ndarray, float]:
    """Prompts SAM2 on frame 0 of the extracted frame sequence in
    frames_dir. Stores the live inference state in the session cache and
    returns (mask_id, mask, score) for the caller to preview / later
    trigger propagate_and_store()."""
    predictor = _get_predictor()
    inference_state = predictor.init_state(video_path=frames_dir)
    predictor.reset_state(inference_state)

    kwargs = {"inference_state": inference_state, "frame_idx": 0, "obj_id": 1}
    if points:
        kwargs["points"] = np.array(points, dtype=np.float32)
        kwargs["labels"] = np.ones(len(points), dtype=np.int32)
    if box:
        kwargs["box"] = np.array(box, dtype=np.float32)

    _, _, out_mask_logits = predictor.add_new_points_or_box(**kwargs)
    mask_bool = np.squeeze((out_mask_logits[0] > 0.0).cpu().numpy())
    mask = mask_bool.astype(np.uint8) * 255
    score = float(mask_bool.mean())  # rough confidence proxy: fraction of frame selected

    mask_id = uuid.uuid4().hex
    with _sessions_lock:
        _sessions[mask_id] = {
            "owner_id": owner_id,
            "media_id": media_id,
            "inference_state": inference_state,
            "frames_dir": frames_dir,
        }
    return mask_id, mask, score


def get_session(mask_id: str, owner_id: int, media_id: int):
    with _sessions_lock:
        session = _sessions.get(mask_id)
    if not session or session["owner_id"] != owner_id or session["media_id"] != media_id:
        return None
    return session


def discard_session(mask_id: str):
    with _sessions_lock:
        _sessions.pop(mask_id, None)


def propagate_masks(inference_state, num_frames: int, progress_cb=None):
    """Propagates the frame-0 prompt across the whole video. Returns a dict
    {frame_idx: mask (uint8 0/255)}. Calls progress_cb(fraction) if given."""
    predictor = _get_predictor()
    masks = {}
    for out_frame_idx, out_obj_ids, out_mask_logits in predictor.propagate_in_video(inference_state):
        mask_bool = np.squeeze((out_mask_logits[0] > 0.0).cpu().numpy())
        masks[out_frame_idx] = mask_bool.astype(np.uint8) * 255
        if progress_cb:
            progress_cb(min(1.0, (out_frame_idx + 1) / max(1, num_frames)))
    return masks