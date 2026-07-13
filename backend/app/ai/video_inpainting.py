"""Video object removal: LaMa inpainting applied per-frame (reusing the
exact same model/logic as photo removal), plus a lightweight temporal
smoothing pass to reduce frame-to-frame flicker in the reconstructed
region — LaMa has no awareness of neighbouring frames on its own, so
consecutive frames can independently invent slightly different fills for
the same hole, which looks like flickering in the final video.
"""
import os

import cv2
import numpy as np

from app.ai.inpainting import remove_object_array


def _warp_by_flow(img: np.ndarray, flow: np.ndarray) -> np.ndarray:
    h, w = flow.shape[:2]
    grid_x, grid_y = np.meshgrid(np.arange(w), np.arange(h))
    map_x = (grid_x + flow[..., 0]).astype(np.float32)
    map_y = (grid_y + flow[..., 1]).astype(np.float32)
    return cv2.remap(img, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _inpaint_downscaled(frame_rgb, mask, max_dimension):
    h, w = frame_rgb.shape[:2]
    scale = min(1.0, max_dimension / max(h, w))
    if scale >= 1.0:
        return remove_object_array(frame_rgb, mask)

    small_w, small_h = int(w * scale), int(h * scale)
    small_frame = cv2.resize(frame_rgb, (small_w, small_h), interpolation=cv2.INTER_AREA)
    small_mask = cv2.resize(mask, (small_w, small_h), interpolation=cv2.INTER_NEAREST)
    small_result = remove_object_array(small_frame, small_mask)
    return cv2.resize(small_result, (w, h), interpolation=cv2.INTER_LINEAR)


def _compute_flow_downscaled(prev_gray, curr_gray, max_dimension):
    h, w = prev_gray.shape[:2]
    scale = min(1.0, max_dimension / max(h, w)) if max_dimension else 1.0
    if scale >= 1.0:
        return cv2.calcOpticalFlowFarneback(prev_gray, curr_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)

    small_w, small_h = int(w * scale), int(h * scale)
    small_prev = cv2.resize(prev_gray, (small_w, small_h), interpolation=cv2.INTER_AREA)
    small_curr = cv2.resize(curr_gray, (small_w, small_h), interpolation=cv2.INTER_AREA)
    small_flow = cv2.calcOpticalFlowFarneback(small_prev, small_curr, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    flow = cv2.resize(small_flow, (w, h), interpolation=cv2.INTER_LINEAR)
    flow[..., 0] *= w / small_w
    flow[..., 1] *= h / small_h
    return flow


def process_video_frames(
    frames_dir: str,
    masks: dict,
    output_dir: str,
    smoothing_weight: float = 0.4,
    frame_skip: int = 6,
    max_dimension: int = 384,
    progress_cb=None,
) -> None:
    """Inpaints frames in frames_dir according to masks (a dict of
    {frame_idx: uint8 0/255 mask array}) and writes results to output_dir
    using the same 00001.jpg, 00002.jpg, ... naming ffmpeg expects.

    frame_skip: only run the (slow) LaMa model every Nth frame; frames in
    between reuse the last LaMa result, warped forward with optical flow.
    max_dimension: both LaMa and optical flow run on the frame downscaled
    to this size (longest side, in px), then results are upscaled back —
    this is the main speed lever. Set to 0 to disable (full resolution).
    """
    os.makedirs(output_dir, exist_ok=True)
    frame_files = sorted(f for f in os.listdir(frames_dir) if f.endswith(".jpg"))
    num_frames = len(frame_files)

    prev_orig_gray = None
    prev_result_rgb = None
    prev_mask = None
    last_lama_result_rgb = None

    def inpaint(frame_rgb, mask):
        if max_dimension and max_dimension > 0:
            return _inpaint_downscaled(frame_rgb, mask, max_dimension)
        return remove_object_array(frame_rgb, mask)

    for i, filename in enumerate(frame_files):
        frame_path = os.path.join(frames_dir, filename)
        frame_bgr = cv2.imread(frame_path)
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mask = masks.get(i)

        if mask is None or mask.max() == 0:
            result_rgb = frame_rgb
            last_lama_result_rgb = None
        else:
            if mask.shape[:2] != frame_rgb.shape[:2]:
                mask = cv2.resize(mask, (frame_rgb.shape[1], frame_rgb.shape[0]), interpolation=cv2.INTER_NEAREST)

            is_keyframe = (i % frame_skip == 0) or last_lama_result_rgb is None
            curr_gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)

            # Compute optical flow at most once per frame (only when we
            # actually need it), reused below for both warping and
            # smoothing instead of computing it twice at full resolution.
            flow = None
            need_flow = (not is_keyframe and prev_orig_gray is not None) or (
                smoothing_weight > 0 and prev_result_rgb is not None and prev_mask is not None
            )
            if need_flow and prev_orig_gray is not None:
                flow = _compute_flow_downscaled(prev_orig_gray, curr_gray, max_dimension)

            if is_keyframe:
                result_rgb = inpaint(frame_rgb, mask)
                last_lama_result_rgb = result_rgb
            elif flow is not None:
                warped = _warp_by_flow(last_lama_result_rgb, flow)
                feathered = cv2.GaussianBlur(mask.astype(np.float64), (0, 0), sigmaX=4) / 255.0
                alpha = np.clip(feathered, 0, 1)[..., None]
                result_rgb = (
                    frame_rgb.astype(np.float64) * (1 - alpha) + warped.astype(np.float64) * alpha
                ).astype(np.uint8)
                last_lama_result_rgb = result_rgb
            else:
                result_rgb = inpaint(frame_rgb, mask)
                last_lama_result_rgb = result_rgb

            if smoothing_weight > 0 and prev_result_rgb is not None and prev_mask is not None and flow is not None:
                warped_prev = _warp_by_flow(prev_result_rgb, flow)
                blend_alpha = cv2.GaussianBlur(mask.astype(np.float64), (0, 0), sigmaX=4) / 255.0
                blend_alpha = np.clip(blend_alpha, 0, 1)[..., None] * smoothing_weight
                result_rgb = (
                    result_rgb.astype(np.float64) * (1 - blend_alpha)
                    + warped_prev.astype(np.float64) * blend_alpha
                ).astype(np.uint8)

        out_path = os.path.join(output_dir, f"{i + 1:05d}.jpg")
        cv2.imwrite(out_path, cv2.cvtColor(result_rgb, cv2.COLOR_RGB2BGR))

        prev_orig_gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
        prev_result_rgb = result_rgb
        prev_mask = mask

        if progress_cb:
            progress_cb(min(1.0, (i + 1) / max(1, num_frames)))