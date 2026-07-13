"""Frame extraction and video reassembly for the video object-removal
pipeline. Frames are extracted to numbered JPEGs (00000.jpg, 00001.jpg,
...) since that's the format SAM2's video predictor expects.
"""
import json
import os
import subprocess
from typing import Tuple


def get_video_info(video_path: str) -> Tuple[float, int]:
    """Returns (fps, frame_count) using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate,nb_frames",
        "-of", "json",
        video_path,
    ]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(out.stdout)
    stream = data["streams"][0]

    num, den = stream["r_frame_rate"].split("/")
    fps = float(num) / float(den)

    frame_count = stream.get("nb_frames")
    if frame_count is None or frame_count == "N/A":
        # Some containers don't report nb_frames directly; fall back to
        # counting via duration * fps using ffprobe's format section.
        cmd2 = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            video_path,
        ]
        out2 = subprocess.run(cmd2, check=True, capture_output=True, text=True)
        duration = float(json.loads(out2.stdout)["format"]["duration"])
        frame_count = int(duration * fps)
    else:
        frame_count = int(frame_count)

    return fps, frame_count


def extract_frames(video_path: str, frames_dir: str, max_dimension: int = 640) -> Tuple[float, int]:
    """Extracts every frame of video_path into frames_dir as 00000.jpg,
    00001.jpg, etc, downscaled so the longest side is at most
    max_dimension (SAM2's per-frame memory cost scales with resolution —
    on limited VRAM, full-res frames can cause severe slowdowns). Returns
    (fps, frame_count)."""
    os.makedirs(frames_dir, exist_ok=True)
    fps, _ = get_video_info(video_path)

    scale_filter = f"scale='min({max_dimension},iw)':'min({max_dimension},ih)':force_original_aspect_ratio=decrease"
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", scale_filter,
        "-qscale:v", "2",
        os.path.join(frames_dir, "%05d.jpg"),
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    frame_count = len([f for f in os.listdir(frames_dir) if f.endswith(".jpg")])
    return fps, frame_count


def reassemble_video(frames_dir: str, fps: float, original_video_path: str, output_path: str) -> None:
    """Encodes the (possibly edited) frames in frames_dir back into a video
    at the given fps, and copies the audio track from original_video_path."""
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", os.path.join(frames_dir, "%05d.jpg"),
        "-i", original_video_path,
        "-map", "0:v:0",
        "-map", "1:a?",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-shortest",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)