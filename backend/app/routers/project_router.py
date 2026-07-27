import os
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_user_from_query
from app.config import settings
from app.database import get_db
from app.jobs import create_job, get_job, run_in_background
from app.models import MediaFile, MediaType, Project, ProjectClip, TransitionType, User
from app.schemas import (
    CutOutRequest,
    MusicRequest,
    ProjectClipIn,
    ProjectClipInsert,
    ProjectCreate,
    ProjectOut,
    ReorderRequest,
    RenderJobOut,
    SplitClipRequest,
)
from app.utils.timeline_utils import render_timeline
from app.utils.ffmpeg_utils import probe_duration

router = APIRouter(prefix="/projects", tags=["projects"])


def _get_owned_project(project_id: int, db: Session, user: User) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not your project")
    return project


def _get_owned_media(media_id: int, db: Session, user: User) -> MediaFile:
    media = db.query(MediaFile).filter(MediaFile.id == media_id).first()
    if not media or media.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Media not found")
    return media


def _resolve_path(media: MediaFile) -> str:
    for directory in (settings.processed_dir, settings.upload_dir):
        candidate = os.path.join(directory, media.current_filename)
        if os.path.exists(candidate):
            return candidate
    raise HTTPException(status_code=404, detail=f"File for media {media.id} missing on disk")


def _concrete_trim_end(media: MediaFile, requested_trim_end, db: Session):
    """Video clips should always land in the project with a real trim_end —
    never null — so the timeline's duration math is exact from the start
    instead of drifting until something else happens to probe it. Uses the
    duration captured at upload time, probing it now (and saving it back)
    as a one-time fallback for files uploaded before that existed."""
    if media.media_type != MediaType.video or requested_trim_end is not None:
        return requested_trim_end
    if media.duration_seconds is None:
        try:
            media.duration_seconds = probe_duration(_resolve_path(media))
            db.flush()
        except Exception:
            return requested_trim_end
    return media.duration_seconds


@router.post("", response_model=ProjectOut)
def create_project(body: ProjectCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = Project(owner_id=current_user.id, name=body.name or "Untitled project")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=List[ProjectOut])
def list_projects(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Project).filter(Project.owner_id == current_user.id).order_by(Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _get_owned_project(project_id, db, current_user)


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = _get_owned_project(project_id, db, current_user)
    db.delete(project)
    db.commit()
    return {"ok": True}


@router.post("/{project_id}/clips", response_model=ProjectOut)
def add_clip(project_id: int, body: ProjectClipIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = _get_owned_project(project_id, db, current_user)
    media = _get_owned_media(body.media_id, db, current_user)

    next_position = len(project.clips)
    clip = ProjectClip(
        project_id=project.id,
        media_id=body.media_id,
        position=next_position,
        trim_start=body.trim_start or 0,
        trim_end=_concrete_trim_end(media, body.trim_end, db),
        photo_duration_seconds=body.photo_duration_seconds or 3,
        transition_out=body.transition_out,
        transition_duration=body.transition_duration or 1,
        speed_factor=body.speed_factor or 1.0,
    )
    db.add(clip)
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/clips/insert", response_model=ProjectOut)
def insert_clip(project_id: int, body: ProjectClipInsert, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Like add_clip, but drops the new clip at a specific position in the
    timeline instead of always appending to the end — used for "insert
    between these two clips" from the frontend."""
    project = _get_owned_project(project_id, db, current_user)
    media = _get_owned_media(body.media_id, db, current_user)

    position = max(0, min(body.position, len(project.clips)))
    for c in project.clips:
        if c.position >= position:
            c.position += 1

    clip = ProjectClip(
        project_id=project.id,
        media_id=body.media_id,
        position=position,
        trim_start=body.trim_start or 0,
        trim_end=_concrete_trim_end(media, body.trim_end, db),
        photo_duration_seconds=body.photo_duration_seconds or 3,
        transition_out=body.transition_out,
        transition_duration=body.transition_duration or 1,
        speed_factor=body.speed_factor or 1.0,
    )
    db.add(clip)
    db.commit()
    db.refresh(project)
    return project


@router.put("/{project_id}/clips/{clip_id}", response_model=ProjectOut)
def update_clip(project_id: int, clip_id: int, body: ProjectClipIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = _get_owned_project(project_id, db, current_user)
    clip = next((c for c in project.clips if c.id == clip_id), None)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    clip.trim_start = body.trim_start or 0
    clip.trim_end = body.trim_end
    clip.photo_duration_seconds = body.photo_duration_seconds or 3
    clip.transition_out = body.transition_out
    clip.transition_duration = body.transition_duration or 1
    clip.speed_factor = body.speed_factor or 1.0
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}/clips/{clip_id}", response_model=ProjectOut)
def remove_clip(project_id: int, clip_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = _get_owned_project(project_id, db, current_user)
    clip = next((c for c in project.clips if c.id == clip_id), None)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    db.delete(clip)
    db.flush()

    remaining = db.query(ProjectClip).filter(ProjectClip.project_id == project.id).order_by(ProjectClip.position).all()
    for i, c in enumerate(remaining):
        c.position = i
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/clips/{clip_id}/split", response_model=ProjectOut)
def split_clip(project_id: int, clip_id: int, body: SplitClipRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Cuts one video clip into two at split_at_seconds (measured within
    the clip's current trimmed range, i.e. 0 = the clip's current start).
    The new second half is inserted immediately after."""
    project = _get_owned_project(project_id, db, current_user)
    clip = next((c for c in project.clips if c.id == clip_id), None)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    if clip.media.media_type.value != "video":
        raise HTTPException(status_code=400, detail="Only video clips can be split")
    if clip.trim_end is None:
        raise HTTPException(status_code=400, detail="Set an explicit trim range on this clip before splitting it")

    local_length = clip.trim_end - clip.trim_start
    split_at = body.split_at_seconds
    if split_at <= 0.05 or split_at >= local_length - 0.05:
        raise HTTPException(status_code=400, detail="Split point must be inside the clip, not at its very start or end")

    split_point_in_source = clip.trim_start + split_at

    for c in project.clips:
        if c.position > clip.position:
            c.position += 1

    second_half = ProjectClip(
        project_id=project.id,
        media_id=clip.media_id,
        position=clip.position + 1,
        trim_start=split_point_in_source,
        trim_end=clip.trim_end,
        photo_duration_seconds=clip.photo_duration_seconds,
        transition_out=clip.transition_out,
        transition_duration=clip.transition_duration,
        speed_factor=clip.speed_factor,
    )
    clip.trim_end = split_point_in_source
    clip.transition_out = TransitionType.none  # hard cut between the two new pieces by default

    db.add(second_half)
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/clips/{clip_id}/cut-out", response_model=ProjectOut)
def cut_out_section(project_id: int, clip_id: int, body: CutOutRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Removes the [start_seconds, end_seconds] section from a video clip
    (measured within its current trimmed range) — a ripple delete. What's
    left before and after the removed section becomes one or two clips."""
    project = _get_owned_project(project_id, db, current_user)
    clip = next((c for c in project.clips if c.id == clip_id), None)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    if clip.media.media_type.value != "video":
        raise HTTPException(status_code=400, detail="Only video clips support cutting out a section")
    if clip.trim_end is None:
        raise HTTPException(status_code=400, detail="Set an explicit trim range on this clip before cutting a section out")

    local_length = clip.trim_end - clip.trim_start
    start_local = max(0.0, body.start_seconds)
    end_local = min(local_length, body.end_seconds)
    if start_local >= end_local:
        raise HTTPException(status_code=400, detail="Invalid section — start must be before end")

    keep_before = start_local > 0.05
    keep_after = end_local < local_length - 0.05
    if not keep_before and not keep_after:
        raise HTTPException(status_code=400, detail="That section is the whole clip — delete the clip instead")

    original_trim_start = clip.trim_start
    original_trim_end = clip.trim_end

    if keep_before and keep_after:
        for c in project.clips:
            if c.position > clip.position:
                c.position += 1
        after_clip = ProjectClip(
            project_id=project.id,
            media_id=clip.media_id,
            position=clip.position + 1,
            trim_start=original_trim_start + end_local,
            trim_end=original_trim_end,
            photo_duration_seconds=clip.photo_duration_seconds,
            transition_out=clip.transition_out,
            transition_duration=clip.transition_duration,
            speed_factor=clip.speed_factor,
        )
        clip.trim_end = original_trim_start + start_local
        clip.transition_out = TransitionType.none
        db.add(after_clip)
    elif keep_before:
        clip.trim_end = original_trim_start + start_local
    else:
        clip.trim_start = original_trim_start + end_local

    db.commit()
    db.refresh(project)
    return project


@router.put("/{project_id}/clips/reorder/apply", response_model=ProjectOut)
def reorder_clips(project_id: int, body: ReorderRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = _get_owned_project(project_id, db, current_user)
    clips_by_id = {c.id: c for c in project.clips}
    if set(body.clip_ids) != set(clips_by_id.keys()):
        raise HTTPException(status_code=400, detail="clip_ids must include every clip in the project exactly once")
    for position, clip_id in enumerate(body.clip_ids):
        clips_by_id[clip_id].position = position
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/music", response_model=ProjectOut)
def set_music(project_id: int, body: MusicRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = _get_owned_project(project_id, db, current_user)
    _get_owned_media(body.media_id, db, current_user)
    project.music_media_id = body.media_id
    project.music_volume = body.volume if body.volume is not None else 100
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}/music", response_model=ProjectOut)
def remove_music(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = _get_owned_project(project_id, db, current_user)
    project.music_media_id = None
    db.commit()
    db.refresh(project)
    return project


def _do_render(job_id: str, project_id: int):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        clips_data = []
        for clip in sorted(project.clips, key=lambda c: c.position):
            clips_data.append({
                "source_path": _resolve_path(clip.media),
                "is_photo": clip.media.media_type.value == "photo",
                "trim_start": clip.trim_start,
                "trim_end": clip.trim_end,
                "photo_duration": clip.photo_duration_seconds,
                "transition_out": clip.transition_out.value,
                "transition_duration": clip.transition_duration,
                "speed_factor": clip.speed_factor,
            })

        music_path = None
        if project.music_media_id:
            music_path = _resolve_path(project.music)

        output_name = f"project_{project.id}_{uuid.uuid4().hex}.mp4"
        output_path = os.path.join(settings.processed_dir, output_name)

        def progress_cb(p):
            from app.jobs import update_job
            update_job(job_id, progress=p)

        render_timeline(clips_data, output_path, music_path=music_path, music_volume=project.music_volume, progress_cb=progress_cb)

        project.rendered_filename = output_name
        db.commit()
    finally:
        db.close()


@router.post("/{project_id}/render", response_model=RenderJobOut)
def render_project(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = _get_owned_project(project_id, db, current_user)
    if not project.clips:
        raise HTTPException(status_code=400, detail="Add at least one clip before rendering")

    job_id = create_job()
    run_in_background(job_id, _do_render, project_id)
    return {"job_id": job_id}


@router.get("/render-status/{job_id}")
def render_status(job_id: str, current_user: User = Depends(get_current_user)):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{project_id}/download")
def download_rendered(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_from_query)):
    project = _get_owned_project(project_id, db, current_user)
    if not project.rendered_filename:
        raise HTTPException(status_code=404, detail="Project hasn't been rendered yet")
    path = os.path.join(settings.processed_dir, project.rendered_filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Rendered file missing on disk")
    return FileResponse(path, media_type="video/mp4", headers={"Cache-Control": "no-store, must-revalidate"})