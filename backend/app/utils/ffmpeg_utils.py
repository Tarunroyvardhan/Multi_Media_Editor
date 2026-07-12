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
