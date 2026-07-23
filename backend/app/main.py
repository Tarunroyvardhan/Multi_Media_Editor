from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.config import settings
from app.database import Base, engine
from app.routers import auth_router, media_router, object_removal_router, video_object_removal_router

Base.metadata.create_all(bind=engine)


def _run_startup_migrations():
    """Base.metadata.create_all only creates missing TABLES, not new
    columns on tables that already exist — so a column added to a model
    after someone already has a database file needs a manual ALTER TABLE
    here. This project has no migration framework (Alembic etc.) since
    it's a small dev app, so this lightweight check is the pragmatic
    equivalent for the one column that's been added so far."""
    inspector = inspect(engine)
    if "media_files" not in inspector.get_table_names():
        return
    columns = [c["name"] for c in inspector.get_columns("media_files")]
    if "thumbnail_filename" not in columns:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE media_files ADD COLUMN thumbnail_filename VARCHAR"))
            conn.commit()


_run_startup_migrations()

app = FastAPI(title="Media Editor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(media_router.router)
app.include_router(object_removal_router.router)
app.include_router(video_object_removal_router.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}