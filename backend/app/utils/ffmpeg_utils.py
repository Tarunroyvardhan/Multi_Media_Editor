import subprocess


def trim_video(input_path: str, output_path: str, start_seconds: float, end_seconds: float) -> None:
    """Cut a video between start_seconds and end_seconds, re-encoding for frame-accurate cuts."""
    duration = max(0.0, end_seconds - start_seconds)
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ss", str(start_seconds),
        "-t", str(duration),
        "-c:v", "libx264",
        "-c:a", "aac",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def crop_video(input_path: str, output_path: str, x: int, y: int, width: int, height: int) -> None:
    """Crop a video to the given rectangle."""
    crop_filter = f"crop={width}:{height}:{x}:{y}"
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", crop_filter,
        "-c:a", "copy",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def rotate_video(input_path: str, output_path: str, degrees: int) -> None:
    """Rotates by a multiple of 90 degrees (clockwise)."""
    # ffmpeg's transpose filter handles clean 90-degree steps without the
    # quality loss / black-bar padding that the general-purpose rotate
    # filter needs for arbitrary angles.
    normalized = degrees % 360
    if normalized == 90:
        vf = "transpose=1"
    elif normalized == 180:
        vf = "transpose=1,transpose=1"
    elif normalized == 270:
        vf = "transpose=2"
    else:
        raise ValueError("degrees must be a multiple of 90 (90, 180, or 270)")

    cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", vf, "-c:a", "copy", output_path]
    subprocess.run(cmd, check=True, capture_output=True)


def flip_video(input_path: str, output_path: str, direction: str) -> None:
    vf = "hflip" if direction == "horizontal" else "vflip"
    cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", vf, "-c:a", "copy", output_path]
    subprocess.run(cmd, check=True, capture_output=True)


def resize_video(input_path: str, output_path: str, width: int, height: int) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", f"scale={width}:{height}",
        "-c:a", "copy",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _has_audio_stream(input_path: str) -> bool:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return bool(result.stdout.strip())


def change_speed_video(input_path: str, output_path: str, factor: float) -> None:
    """factor > 1 speeds up, < 1 slows down. e.g. 2.0 = double speed."""
    if factor <= 0:
        raise ValueError("factor must be positive")

    setpts = f"setpts={1 / factor}*PTS"

    if not _has_audio_stream(input_path):
        cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", setpts, "-an", output_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return

    # ffmpeg's atempo filter only accepts 0.5-2.0 per instance, so factors
    # outside that range need to be chained across multiple atempo steps.
    atempo_filters = []
    remaining = factor
    while remaining > 2.0:
        atempo_filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        atempo_filters.append("atempo=0.5")
        remaining /= 0.5
    atempo_filters.append(f"atempo={remaining}")
    atempo_chain = ",".join(atempo_filters)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-filter_complex", f"[0:v]{setpts}[v];[0:a]{atempo_chain}[a]",
        "-map", "[v]", "-map", "[a]",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def set_volume_video(input_path: str, output_path: str, level: float, mute: bool = False) -> None:
    if not _has_audio_stream(input_path):
        raise ValueError("This video has no audio track to adjust")
    af = "volume=0" if mute else f"volume={level}"
    cmd = ["ffmpeg", "-y", "-i", input_path, "-af", af, "-c:v", "copy", output_path]
    subprocess.run(cmd, check=True, capture_output=True)


def add_text_overlay_video(
    input_path: str,
    output_path: str,
    text: str,
    x: int,
    y: int,
    font_size: int = 32,
    color: str = "white",
    font_file: str = None,
) -> None:
    """font_file is optional but sometimes required on Windows builds of
    ffmpeg that lack fontconfig — if drawtext fails with a font-related
    error, pass an explicit .ttf path (e.g. C:/Windows/Fonts/arial.ttf)."""
    escaped = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    drawtext = f"drawtext=text='{escaped}':x={x}:y={y}:fontsize={font_size}:fontcolor={color}"
    if font_file:
        escaped_font = font_file.replace("\\", "/").replace(":", "\\:")
        drawtext += f":fontfile='{escaped_font}'"

    cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", drawtext, "-c:a", "copy", output_path]
    subprocess.run(cmd, check=True, capture_output=True)