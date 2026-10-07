from pathlib import Path
from typing import ClassVar, Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv(Path(__file__).parents[1] / ".env")


class Settings(BaseSettings):
    BASE_PATH: ClassVar[Path] = Path(__file__).resolve().parents[1]
    gemini_api_key: str
    character_ids: str
    model_fallbacks: str = ""
    interface: Literal["cli", "api"] = "cli"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # Long-term memory: archive a thread once it holds more than `trigger` rounds, keeping the last `keep`.
    memory_model: str = ""  # empty = same model as the player agents
    memory_trigger_rounds: int = 30
    memory_keep_rounds: int = 10
    memory_max_episodes: int = 6

    @property
    def party(self) -> tuple[str, ...]:
        return tuple(part.strip() for part in self.character_ids.split(",") if part.strip())

    @property
    def fallbacks(self) -> tuple[str, ...]:
        return tuple(part.strip() for part in self.model_fallbacks.split(",") if part.strip())

    class Config:
        env_file = Path(__file__).parents[1] / ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
