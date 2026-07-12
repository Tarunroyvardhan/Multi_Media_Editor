import os
import shutil
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_user_from_query
from app.config import settings
from app.database import get_db
from app.models import MediaFile, MediaType, User
from app.schemas import CropRequest, FilterRequest, MediaOut, TrimRequest
from app.utils.ffmpeg_utils import crop_video, trim_video
from app.utils.image_utils import apply_filter, crop_image

router = APIRouter(prefix="/media", tags=["media"])

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _detect_media_type(filename: str) -> MediaType:
    ext = os.path.splitext(filename)[1].lower()
    if ext in VIDEO_EXTENSIONS:
        return MediaType.video
    if ext in IMAGE_EXTENSIONS:
        return MediaType.photo
    raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")


def _get_owned_media(media_id: int, db: Session, user: User) -> MediaFile:
    media = db.query(MediaFile).filter(MediaFile.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    if media.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not your file")
    return media


@router.post("/upload", response_model=MediaOut)
def upload_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media_type = _detect_media_type(file.filename)
    ext = os.path.splitext(file.filename)[1].lower()
    stored_name = f"{uuid.uuid4().hex}{ext}"
    stored_path = os.path.join(settings.upload_dir, stored_name)

    with open(stored_path, "wb") as out_file:
        shutil.copyfileobj(file.file, out_file)

    media = MediaFile(
        owner_id=current_user.id,
        media_type=media_type,
        original_filename=file.filename,
        stored_filename=stored_name,
        current_filename=stored_name,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


@router.get("/list", response_model=List[MediaOut])
def list_media(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(MediaFile).filter(MediaFile.owner_id == current_user.id).order_by(MediaFile.created_at.desc()).all()


@router.get("/{media_id}/file")
def get_media_file(
    media_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_query),
):
    media = _get_owned_media(media_id, db, current_user)
    path = os.path.join(settings.upload_dir, media.current_filename)
    if not os.path.exists(path):
        path = os.path.join(settings.processed_dir, media.current_filename)
    return FileResponse(path, headers={"Cache-Control": "no-store, must-revalidate"})


def _resolve_current_path(media: MediaFile) -> str:
    for directory in (settings.processed_dir, settings.upload_dir):
        candidate = os.path.join(directory, media.current_filename)
        if os.path.exists(candidate):
            return candidate
    raise HTTPException(status_code=404, detail="Underlying file missing on disk")


@router.post("/{media_id}/trim", response_model=MediaOut)
def trim_media(
    media_id: int,
    payload: TrimRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media = _get_owned_media(media_id, db, current_user)
    if media.media_type != MediaType.video:
        raise HTTPException(status_code=400, detail="Trim only applies to video files")

    input_path = _resolve_current_path(media)
    ext = os.path.splitext(media.stored_filename)[1]
    output_name = f"{uuid.uuid4().hex}{ext}"
    output_path = os.path.join(settings.processed_dir, output_name)

    trim_video(input_path, output_path, payload.start_seconds, payload.end_seconds)

    media.current_filename = output_name
    db.commit()
    db.refresh(media)
    return media


@router.post("/{media_id}/crop", response_model=MediaOut)
def crop_media(
    media_id: int,
    payload: CropRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media = _get_owned_media(media_id, db, current_user)
    input_path = _resolve_current_path(media)
    ext = os.path.splitext(media.stored_filename)[1]
    output_name = f"{uuid.uuid4().hex}{ext}"
    output_path = os.path.join(settings.processed_dir, output_name)

    if media.media_type == MediaType.video:
        crop_video(input_path, output_path, payload.x, payload.y, payload.width, payload.height)
    else:
        crop_image(input_path, output_path, payload.x, payload.y, payload.width, payload.height)

    media.current_filename = output_name
    db.commit()
    db.refresh(media)
    return media


@router.post("/{media_id}/filter", response_model=MediaOut)
def filter_media(
    media_id: int,
    payload: FilterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media = _get_owned_media(media_id, db, current_user)
    if media.media_type != MediaType.photo:
        raise HTTPException(status_code=400, detail="Filters currently apply to photos only")

    input_path = _resolve_current_path(media)
    ext = os.path.splitext(media.stored_filename)[1]
    output_name = f"{uuid.uuid4().hex}{ext}"
    output_path = os.path.join(settings.processed_dir, output_name)

    apply_filter(input_path, output_path, payload.filter_name, payload.intensity)

    media.current_filename = output_name
    db.commit()
    db.refresh(media)
    return media


@router.delete("/{media_id}")
def delete_media(media_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    media = _get_owned_media(media_id, db, current_user)
    db.delete(media)
    db.commit()
    return {"detail": "Deleted"}
