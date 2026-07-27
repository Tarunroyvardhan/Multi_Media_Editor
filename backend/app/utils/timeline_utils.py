"""Renders a Project (ordered clips + transitions + music) into one output
video, using ffmpeg's xfade/acrossfade filters.

Approach:
1. Normalize every clip (photo or video) to the same resolution/fps/codec,
   always with an audio stream (silent if the source has none). This makes
   every clip "compatible" so they can be chained together.
2. Chain clips pairwise with ffmpeg's `xfade` (video) and `acrossfade`
   (audio) filters. A transition_duration of effectively 0 is a hard cut;
   any of xfade's named transitions (fade, wipeleft, slideup, ...) can be
   used per-junction, matching what the frontend lets the user pick.
3. If the project has a music track, mix it under the combined audio,
   looping/trimming it to the final duration and applying volume.
"""
import json
import os
import shutil
import subprocess
import tempfile

from app.config import settings

FFMPEG = settings.ffmpeg_path
FFPROBE = settings.ffprobe_path

WIDTH = 1280
HEIGHT = 720
FPS = 30
MIN_TRANSITION = 0.05  # ffmpeg's xfade misbehaves at exactly 0


def _probe_duration(path: str) -> float:
    cmd = [
        FFPROBE, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def _has_audio_stream(path: str) -> bool:
    cmd = [
        FFPROBE, "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return bool(result.stdout.strip())


def _atempo_chain(factor: float) -> str:
    """ffmpeg's atempo filter only accepts 0.5-2.0 per instance, so factors
    outside that range need to be chained across multiple atempo steps."""
    filters = []
    remaining = factor
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining}")
    return ",".join(filters)


def _normalize_video_clip(
    input_path: str, output_path: str, trim_start: float, trim_end: float | None, speed_factor: float = 1.0,
) -> None:
    duration_args = []
    if trim_start:
        duration_args += ["-ss", str(trim_start)]
    if trim_end is not None:
        duration_args += ["-t", str(max(0.1, trim_end - trim_start))]

    vf_parts = [
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease",
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2",
        "setsar=1",
    ]
    if speed_factor and speed_factor != 1.0:
        vf_parts.append(f"setpts={1 / speed_factor}*PTS")
    vf_parts.append(f"fps={FPS}")
    vf = ",".join(vf_parts)

    af = _atempo_chain(speed_factor) if speed_factor and speed_factor != 1.0 else None

    has_audio = _has_audio_stream(input_path)
    if has_audio:
        cmd = [
            FFMPEG, "-y", *duration_args, "-i", input_path,
            "-vf", vf,
        ]
        if af:
            cmd += ["-af", af]
        cmd += ["-c:v", "libx264", "-c:a", "aac", "-ar", "44100", "-ac", "2", output_path]
    else:
        cmd = [
            FFMPEG, "-y", *duration_args, "-i", input_path,
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-vf", vf,
            "-c:v", "libx264", "-c:a", "aac",
            "-shortest",
            output_path,
        ]
    subprocess.run(cmd, check=True, capture_output=True)


def _normalize_photo_clip(input_path: str, output_path: str, duration_seconds: float) -> None:
    vf = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS}"
    )
    cmd = [
        FFMPEG, "-y",
        "-loop", "1", "-i", input_path,
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-vf", vf,
        "-t", str(max(0.5, duration_seconds)),
        "-c:v", "libx264", "-c:a", "aac",
        "-shortest",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _mix_music(video_path: str, music_path: str, output_path: str, volume_percent: int) -> None:
    total_duration = _probe_duration(video_path)
    volume = max(0.0, volume_percent / 100.0)
    filter_complex = (
        f"[1:a]aloop=loop=-1:size=2e9,atrim=0:{total_duration},"
        f"volume={volume}[music];"
        f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    cmd = [
        FFMPEG, "-y",
        "-i", video_path,
        "-i", music_path,
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",
        "-shortest",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def render_timeline(
    clips: list[dict],
    output_path: str,
    music_path: str | None = None,
    music_volume: int = 100,
    progress_cb=None,
) -> None:
    """clips: list of dicts, in order, each with:
        - source_path: str
        - is_photo: bool
        - trim_start / trim_end: float | None (video only)
        - photo_duration: float (photo only)
        - transition_out: str (xfade transition name, or "none")
        - transition_duration: float
    """
    if not clips:
        raise ValueError("A project needs at least one clip to render")

    if shutil.which(FFMPEG) is None or shutil.which(FFPROBE) is None:
        raise RuntimeError(
            "ffmpeg/ffprobe were not found (looked for '" + FFMPEG + "' and '" + FFPROBE + "'). "
            "If they're installed but this keeps failing, PATH probably hasn't propagated to this "
            "process yet — fully close and reopen your terminal (and IDE, if it spawned the terminal), "
            "or set FFMPEG_PATH and FFPROBE_PATH to the full .exe paths in backend/.env instead."
        )

    with tempfile.TemporaryDirectory() as tmp:
        normalized_paths = []
        for i, clip in enumerate(clips):
            norm_path = os.path.join(tmp, f"clip_{i}.mp4")
            if clip["is_photo"]:
                _normalize_photo_clip(clip["source_path"], norm_path, clip["photo_duration"])
            else:
                _normalize_video_clip(
                    clip["source_path"], norm_path, clip.get("trim_start") or 0, clip.get("trim_end"),
                    clip.get("speed_factor") or 1.0,
                )
            normalized_paths.append(norm_path)
            if progress_cb:
                progress_cb(0.1 + 0.5 * (i + 1) / len(clips))

        if len(normalized_paths) == 1:
            combined_path = normalized_paths[0]
        else:
            durations = [_probe_duration(p) for p in normalized_paths]
            combined_path = os.path.join(tmp, "combined.mp4")
            _chain_with_transitions(normalized_paths, durations, clips, combined_path)
            if progress_cb:
                progress_cb(0.75)

        if music_path:
            _mix_music(combined_path, music_path, output_path, music_volume)
        else:
            if combined_path != output_path:
                subprocess.run([FFMPEG, "-y", "-i", combined_path, "-c", "copy", output_path], check=True, capture_output=True)
        if progress_cb:
            progress_cb(1.0)


def _chain_with_transitions(paths: list[str], durations: list[float], clips: list[dict], output_path: str) -> None:
    n = len(paths)
    inputs = []
    for p in paths:
        inputs += ["-i", p]

    filter_parts = []
    cumulative = durations[0]
    prev_v = "0:v"
    prev_a = "0:a"

    for i in range(1, n):
        transition_name = clips[i - 1].get("transition_out") or "none"
        t_dur = clips[i - 1].get("transition_duration") or MIN_TRANSITION
        t_dur = max(MIN_TRANSITION, min(t_dur, durations[i - 1] - 0.1, durations[i] - 0.1, t_dur))
        if transition_name == "none":
            transition_name = "fade"
            t_dur = MIN_TRANSITION

        offset = max(0.0, cumulative - t_dur)
        v_out = f"v{i}"
        a_out = f"a{i}"
        filter_parts.append(
            f"[{prev_v}][{i}:v]xfade=transition={transition_name}:duration={t_dur}:offset={offset}[{v_out}]"
        )
        filter_parts.append(f"[{prev_a}][{i}:a]acrossfade=d={t_dur}[{a_out}]")

        cumulative = offset + t_dur + (durations[i] - t_dur)
        prev_v = v_out
        prev_a = a_out

    filter_complex = ";".join(filter_parts)
    cmd = [
        FFMPEG, "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{prev_v}]", "-map", f"[{prev_a}]",
        "-c:v", "libx264", "-c:a", "aac",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)