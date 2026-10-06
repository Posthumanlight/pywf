from pathlib import Path

from pydantic_settings import BaseSettings
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

class Settings(BaseSettings):
    BASE_PATH = Path(__file__).resolve().parents[1]
    gemini_api_key: str
    
    class Config:
        env_file = Path(__file__).parent / ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

settings = Settings()
print("Loading env file from:", settings.Config.env_file)


