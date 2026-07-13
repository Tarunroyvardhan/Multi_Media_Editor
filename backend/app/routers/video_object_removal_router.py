import base64
import hashlib
import os
import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.ai import segmentation, video_inpainting, video_segmentation
from app.auth import get_current_user, get_current_user_from_query
from app.config import settings
from app.database import SessionLocal, get_db
from app.jobs import create_job, get_job, run_in_background, update_job
from app.models import MediaFile, MediaType, User
from app.routers.media_router import _get_owned_media, _resolve_current_path
from app.schemas import (
    JobStatus,
    RemoveObjectRequest,
    SegmentRequest,
    VideoRemoveObjectResponse,
    VideoSegmentResponse,
)
from app.utils.video_frames import extract_frames, reassemble_video

router = APIRouter(prefix="/media", tags=["video-object-removal"])


def _frames_dir_for(owner_id: int, media_id: int, current_filename: str) -> str:
    version_hash = hashlib.sha1(current_filename.encode()).hexdigest()[:10]
    return os.path.join(settings.video_work_dir, f"{owner_id}_{media_id}_{version_hash}")


def _ensure_frames_extracted(media: MediaFile, owner_id: int) -> str:
    frames_dir = _frames_dir_for(owner_id, media.id, media.current_filename)
    marker = os.path.join(frames_dir, ".done")
    if os.path.exists(marker):
        return frames_dir

    if os.path.exists(frames_dir):
        shutil.rmtree(frames_dir)

    input_path = _resolve_current_path(media)
    extracted_fps, _ = extract_frames(input_path, frames_dir)
    with open(os.path.join(frames_dir, "fps.txt"), "w") as f:
        f.write(str(extracted_fps))
    with open(marker, "w") as f:
        f.write("ok")
    return frames_dir


@router.get("/{media_id}/first-frame")
def get_first_frame(
    media_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_query),
):
    media = _get_owned_media(media_id, db, current_user)
    if media.media_type != MediaType.video:
        raise HTTPException(status_code=400, detail="first-frame is only for videos")

    frames_dir = _ensure_frames_extracted(media, current_user.id)
    first_frame_path = os.path.join(frames_dir, "00001.jpg")
    if not os.path.exists(first_frame_path):
        raise HTTPException(status_code=500, detail="Could not extract video frames")

    return FileResponse(first_frame_path, headers={"Cache-Control": "no-store, must-revalidate"})


@router.post("/{media_id}/video-segment", response_model=VideoSegmentResponse)
def video_segment_object(
    media_id: int,
    payload: SegmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media = _get_owned_media(media_id, db, current_user)
    if media.media_type != MediaType.video:
        raise HTTPException(status_code=400, detail="video-segment is only for videos")

    points = [tuple(p) for p in payload.points] if payload.points else None
    box = tuple(payload.box) if payload.box else None
    if not points and not box:
        raise HTTPException(status_code=400, detail="Provide either points or a box")

    frames_dir = _ensure_frames_extracted(media, current_user.id)

    try:
        mask_id, mask, score = video_segmentation.segment_first_frame(
            frames_dir, current_user.id, media_id, points=points, box=box
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    overlay_bytes = segmentation.mask_to_overlay_png_bytes(mask)
    overlay_b64 = base64.b64encode(overlay_bytes).decode("utf-8")
    h, w = mask.shape

    return VideoSegmentResponse(
        mask_id=mask_id,
        score=score,
        overlay_png_base64=overlay_b64,
        first_frame_width=w,
        first_frame_height=h,
    )


def _run_video_removal(job_id: str, media_id: int, owner_id: int, mask_id: str):
    session = video_segmentation.get_session(mask_id, owner_id, media_id)
    if session is None:
        raise RuntimeError("Segmentation session expired — select the object again")

    frames_dir = session["frames_dir"]
    inference_state = session["inference_state"]

    db = SessionLocal()
    try:
        media = db.query(MediaFile).filter(MediaFile.id == media_id).first()
        if media is None:
            raise RuntimeError("Media not found")

        input_path = _resolve_current_path(media)
        from app.utils.video_frames import get_video_info

        original_fps, _ = get_video_info(input_path)
        with open(os.path.join(frames_dir, "fps.txt")) as f:
            extracted_fps = float(f.read().strip())
        num_frames = len([f for f in os.listdir(frames_dir) if f.endswith(".jpg")])

        masks = video_segmentation.propagate_masks(
            inference_state, num_frames, progress_cb=lambda f: update_job(job_id, progress=0.5 * f)
        )

        output_frames_dir = frames_dir + "_output"
        video_inpainting.process_video_frames(
            frames_dir,
            masks,
            output_frames_dir,
            smoothing_weight=0,
            progress_cb=lambda f: update_job(job_id, progress=0.5 + 0.5 * f),
        )

        ext = os.path.splitext(media.stored_filename)[1]
        output_name = f"{uuid.uuid4().hex}{ext}"
        output_path = os.path.join(settings.processed_dir, output_name)
        reassemble_video(output_frames_dir, extracted_fps, original_fps, input_path, output_path)

        media.current_filename = output_name
        db.commit()

        shutil.rmtree(output_frames_dir, ignore_errors=True)
        shutil.rmtree(frames_dir, ignore_errors=True)
    finally:
        db.close()
        video_segmentation.discard_session(mask_id)


@router.post("/{media_id}/video-remove-object", response_model=VideoRemoveObjectResponse)
def video_remove_object(
    media_id: int,
    payload: RemoveObjectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media = _get_owned_media(media_id, db, current_user)
    if media.media_type != MediaType.video:
        raise HTTPException(status_code=400, detail="video-remove-object is only for videos")

    session = video_segmentation.get_session(payload.mask_id, current_user.id, media_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Mask not found or expired — select the object again")

    job_id = create_job()
    run_in_background(job_id, _run_video_removal, media_id, current_user.id, payload.mask_id)
    return VideoRemoveObjectResponse(job_id=job_id)


@router.get("/{media_id}/video-remove-object/jobs/{job_id}", response_model=JobStatus)
def get_video_removal_job(
    media_id: int,
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_media(media_id, db, current_user)  # ownership check
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatus(**job)