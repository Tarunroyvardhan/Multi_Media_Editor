import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = "insecure-dev-key-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    database_url: str = "sqlite:///./mediaeditor.db"
    upload_dir: str = "storage/uploads"
    processed_dir: str = "storage/processed"
    masks_dir: str = "storage/masks"
    video_work_dir: str = "storage/video_work"
    ai_models_dir: str = "ai_models"
    frontend_origin: str = "http://localhost:5173"

    class Config:
        env_file = ".env"


settings = Settings()

os.makedirs(settings.upload_dir, exist_ok=True)
os.makedirs(settings.processed_dir, exist_ok=True)
os.makedirs(settings.masks_dir, exist_ok=True)
os.makedirs(settings.video_work_dir, exist_ok=True)