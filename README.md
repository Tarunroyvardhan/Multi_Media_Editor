# Media Editor — v1

A web app for editing photos and videos, with user accounts.

**Stack:** FastAPI (Python) backend + React (Vite) frontend.

**Features:**
- Register / log in (JWT auth)
- Upload a photo or video
- Trim a video (start/end seconds)
- Crop a photo or video (x, y, width, height)
- Apply a filter to a photo (grayscale, brightness, contrast, blur, sepia)
- **Remove an object from a photo** — click it or draw a box around it, and it's segmented (MobileSAM) and erased with AI inpainting (LaMa), all running locally on CPU
- View and delete your files

---

## Prerequisites

- Python 3.10+
- Node.js 18+
- **ffmpeg** installed and on your PATH (needed for video trim/crop)
  - Mac: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - Windows: download from ffmpeg.org and add to PATH

## 1. Backend setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env          # then edit SECRET_KEY to something random

uvicorn app.main:app --reload --port 8000
```

The API is now running at `http://localhost:8000`. Interactive docs at
`http://localhost:8000/docs`.

Generate a real secret key with:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## 2. Object removal setup (optional but recommended)

The object-removal feature needs a few extra, heavier packages (PyTorch,
MobileSAM, LaMa). These are kept separate from `requirements.txt` so the
rest of the app stays lightweight if you don't need this feature yet.

```bash
cd backend
pip install -r requirements-ai.txt
pip install --no-deps simple-lama-inpainting==0.1.2
python download_ai_models.py
```

- `download_ai_models.py` fetches the MobileSAM checkpoint (~41MB) into
  `ai_models/`.
- The LaMa inpainting checkpoint (~196MB) downloads automatically the
  first time you actually remove an object — that first request will be
  slower while it downloads.
- Everything runs on CPU. No GPU is required, though the code will use
  one automatically if you install a CUDA build of PyTorch instead (see
  the comments in `requirements-ai.txt`).
- If you skip this step, every other feature still works — only the
  Remove Object tool will return an error until it's set up.

Restart uvicorn after installing these.

To confirm your GPU is actually being used, run this in your activated venv
after installing:
```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```
It should print `True` and your GPU's name. If it prints `False`, your
NVIDIA driver likely needs installing/updating — torch will still work, just
on CPU (slower, but functionally identical).

## 3. Frontend setup

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Register an account, log in, upload a photo
or video, and use the Editor page to trim/crop/filter/remove objects.

## How it fits together

```
frontend (React, :5173)
    │  JWT in Authorization header
    ▼
backend (FastAPI, :8000)
    │
    ├─ /auth/*   → register, login, current user (SQLite via SQLAlchemy)
    ├─ /media/*  → upload, list, trim, crop, filter, delete
    ├─ /media/{id}/segment       → MobileSAM: point/box click → mask
    ├─ /media/{id}/remove-object → LaMa: mask → inpainted photo
    │
    ├─ app/utils/ffmpeg_utils.py  → shells out to ffmpeg for video trim/crop
    ├─ app/utils/image_utils.py   → Pillow for photo crop/filters
    └─ app/ai/
        ├─ segmentation.py  → MobileSAM, loaded once, reused per request
        └─ inpainting.py    → LaMa, loaded once, reused per request
```

**How object removal works, end to end:**
1. In the Editor, pick Point or Box mode and click/drag on the photo.
2. The frontend converts your screen click into the photo's actual pixel
   coordinates and calls `POST /media/{id}/segment`.
3. MobileSAM segments the object and the backend returns a translucent
   red mask overlay (as a base64 PNG) plus a `mask_id` — the mask itself
   is saved to `storage/masks/` under a filename scoped to your user and
   file, so it can't be reused by or on someone else's file.
4. You review the highlighted region, then click "Remove selected
   object", which calls `POST /media/{id}/remove-object` with that
   `mask_id`. LaMa inpaints the masked region and the result becomes the
   new current version of the file — the mask file is deleted afterward.

Files are stored on disk: originals in `backend/storage/uploads/`,
edited outputs in `backend/storage/processed/`. Each edit creates a new
file and repoints `current_filename`, so the original is never
overwritten (basic non-destructive editing / undo path if you want to
extend it to version history later).

## Suggested next steps (roadmap)

1. **Video object removal**: the segmentation/inpainting groundwork is
   in place — extending it to video means propagating the mask across
   frames (MobileSAM doesn't track across frames on its own; you'd need
   optical flow or a video-specific tracker) and swapping LaMa for a
   temporal video-inpainting model (ProPainter, E2FGVI) as described in
   the original pipeline document. This is meaningfully heavier — a
   good candidate to eventually split into its own service.
2. **More video edits**: rotate, speed change, volume, watermark/text
   overlay, thumbnail generation (all straightforward ffmpeg calls to
   add in `ffmpeg_utils.py`).
3. **More photo edits**: rotate/flip, saturation, sharpen, resize —
   add to `image_utils.py`.
4. **Background/async processing**: trim/crop/filter/segment/remove all
   run synchronously in the request right now. For larger files, move
   these into a background task queue (Celery + Redis, or FastAPI
   `BackgroundTasks` for a lighter start) and poll/return job status
   instead of blocking.
5. **Cloud storage**: swap local disk for S3-compatible storage when
   you need multi-server deployment.
6. **Undo/version history**: you already keep every intermediate file
   on disk — add a `versions` table to let users step back through
   edits instead of only seeing the latest.
7. **Multi-point / negative points for segmentation**: MobileSAM
   supports multiple positive and negative points to refine a mask —
   the backend endpoint already accepts a `points` list, so this is
   mostly frontend work (shift-click to add a negative point, for
   example).

