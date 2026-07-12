"""Run once after installing requirements-ai.txt:

    python download_ai_models.py

Downloads the MobileSAM checkpoint (~41MB) into ai_models/.
The LaMa inpainting checkpoint (~196MB) is downloaded automatically by
torch on first use of the remove-object endpoint, so it doesn't need a
separate step here.
"""
import os
import urllib.request

CHECKPOINT_URL = "https://github.com/ChaoningZhang/MobileSAM/raw/master/weights/mobile_sam.pt"
DEST_DIR = os.path.join(os.path.dirname(__file__), "ai_models")
DEST_PATH = os.path.join(DEST_DIR, "mobile_sam.pt")


def main():
    os.makedirs(DEST_DIR, exist_ok=True)
    if os.path.exists(DEST_PATH):
        print(f"Already downloaded: {DEST_PATH}")
        return
    print(f"Downloading MobileSAM checkpoint to {DEST_PATH} ...")
    urllib.request.urlretrieve(CHECKPOINT_URL, DEST_PATH)
    print("Done.")


if __name__ == "__main__":
    main()
