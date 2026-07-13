"""Run once after installing requirements-video-ai.txt:

    python download_video_ai_models.py

Downloads the SAM2 "tiny" checkpoint (~150MB) into ai_models/. This is
the fastest/smallest option, chosen to fit comfortably in limited VRAM.

The config YAML files come bundled with the `sam2` pip package itself, so
only the checkpoint needs downloading here.
"""
import os
import urllib.request

CHECKPOINT_URL = (
    "https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_tiny.pt"
)
DEST_DIR = os.path.join(os.path.dirname(__file__), "ai_models")
DEST_PATH = os.path.join(DEST_DIR, "sam2_hiera_tiny.pt")


def main():
    os.makedirs(DEST_DIR, exist_ok=True)
    if os.path.exists(DEST_PATH):
        print(f"Already downloaded: {DEST_PATH}")
        return
    print(f"Downloading SAM2 checkpoint to {DEST_PATH} ...")
    try:
        urllib.request.urlretrieve(CHECKPOINT_URL, DEST_PATH)
        print("Done.")
    except Exception as exc:
        print(f"Download failed: {exc}")
        print(
            "If this URL has moved, get the checkpoint manually from "
            "https://github.com/facebookresearch/sam2#model-checkpoints "
            f"and save it as {DEST_PATH}"
        )
        raise


if __name__ == "__main__":
    main()