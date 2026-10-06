from pathlib import Path

from pydantic_settings import BaseSettings
from pathlib import Path
from dotenv import load_dotenv
from typing import ClassVar

load_dotenv(Path(__file__).parents[1] / ".env")

class Settings(BaseSettings):
    BASE_PATH : ClassVar[Path]= Path(__file__).resolve().parents[1]
    gemini_api_key: str
    character_id: str

    class Config:
        env_file = Path(__file__).parents[1] / ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

settings = Settings()


