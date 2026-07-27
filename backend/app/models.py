import datetime
import enum

from sqlalchemy import Column, Integer, Float, String, DateTime, Enum, ForeignKey, event
from sqlalchemy.orm import relationship, object_session
from sqlalchemy.orm.attributes import NO_VALUE

from app.database import Base


class MediaType(str, enum.Enum):
    photo = "photo"
    video = "video"
    audio = "audio"


class TransitionType(str, enum.Enum):
    """Transition applied between this clip and the NEXT one in a project's
    timeline. 'none' is a hard cut. The rest map directly to ffmpeg's xfade
    filter's built-in transition names."""
    none = "none"
    fade = "fade"
    fadeblack = "fadeblack"
    wipeleft = "wipeleft"
    wiperight = "wiperight"
    slideup = "slideup"
    slidedown = "slidedown"
    circleopen = "circleopen"
    circleclose = "circleclose"
    dissolve = "dissolve"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    media_files = relationship("MediaFile", back_populates="owner", cascade="all, delete-orphan")


class MediaFile(Base):
    __tablename__ = "media_files"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    media_type = Column(Enum(MediaType), nullable=False)
    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=False)
    current_filename = Column(String, nullable=False)  # points to latest edited version
    thumbnail_filename = Column(String, nullable=True)  # video only; photos are their own thumbnail
    duration_seconds = Column(Float, nullable=True)  # video/audio only; probed via ffprobe at upload time
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="media_files")
    versions = relationship(
        "MediaVersion", back_populates="media", cascade="all, delete-orphan",
        order_by="MediaVersion.created_at",
    )


class MediaVersion(Base):
    __tablename__ = "media_versions"

    id = Column(Integer, primary_key=True, index=True)
    media_id = Column(Integer, ForeignKey("media_files.id"), nullable=False)
    filename = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    media = relationship("MediaFile", back_populates="versions")


@event.listens_for(MediaFile.current_filename, "set")
def _record_version_on_change(target, value, oldvalue, initiator):
    """Every time current_filename changes (i.e. any edit is applied), stash
    the filename it's about to stop pointing at as a restorable version.
    This runs centrally here rather than in every router endpoint, so no
    edit endpoint needs to remember to call it. The very first time
    current_filename is set (on upload), oldvalue is NO_VALUE, so nothing
    is recorded — there's nothing to restore to yet."""
    if oldvalue in (None, NO_VALUE) or oldvalue == value:
        return
    session = object_session(target)
    if session is None or target.id is None:
        return
    session.add(MediaVersion(media_id=target.id, filename=oldvalue))


class Project(Base):
    """A CapCut-style timeline: an ordered sequence of clips (photos and/or
    videos) with transitions between them, plus an optional background
    music track. Rendering combines everything into one output MediaFile-
    style video on disk."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False, default="Untitled project")
    music_media_id = Column(Integer, ForeignKey("media_files.id"), nullable=True)
    music_volume = Column(Integer, nullable=False, default=100)  # percent, 0-200
    rendered_filename = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("User")
    music = relationship("MediaFile", foreign_keys=[music_media_id])
    clips = relationship(
        "ProjectClip", back_populates="project", cascade="all, delete-orphan",
        order_by="ProjectClip.position",
    )


class ProjectClip(Base):
    __tablename__ = "project_clips"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    media_id = Column(Integer, ForeignKey("media_files.id"), nullable=False)
    position = Column(Integer, nullable=False)  # 0-based order in the timeline
    trim_start = Column(Float, nullable=False, default=0)  # seconds; video clips only
    trim_end = Column(Float, nullable=True)  # seconds; null = to end of video
    photo_duration_seconds = Column(Integer, nullable=False, default=3)  # photos only
    transition_out = Column(Enum(TransitionType), nullable=False, default=TransitionType.none)
    transition_duration = Column(Float, nullable=False, default=1)  # seconds
    speed_factor = Column(Float, nullable=False, default=1.0)  # 1.0 = normal speed; video clips only

    project = relationship("Project", back_populates="clips")
    media = relationship("MediaFile")