"""Backend-only environment configuration; never expose credentials."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Explicit backend file, with process environment taking precedence.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    gemini_enabled: bool = False
    gemini_api_key: str = field(default="", repr=False)
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_ms: int = 45_000
    gemini_max_input_bytes: int = 60_000
    gemini_max_output_bytes: int = 100_000
    gemini_max_output_tokens: int = 12_000
    gemini_max_attempts: int = 1
    artifact_ttl_seconds: int = 3600
    artifact_max_records: int = 32
    artifact_max_bytes: int = 64 * 1024 * 1024
    frontend_origins: tuple[str, ...] = ("http://127.0.0.1:5173", "http://localhost:5173")

    @classmethod
    def from_env(cls):
        def bounded(name, default, low, high):
            try:
                return min(high, max(low, int(os.getenv(name, str(default)))))
            except ValueError:
                return default

        origins = tuple(origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",") if origin.strip())
        return cls(
            gemini_enabled=os.getenv("GEMINI_ASSESSMENT_ENABLED", "false").lower() == "true",
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash",
            gemini_timeout_ms=bounded("GEMINI_TIMEOUT_SECONDS", 45, 5, 120) * 1000,
            artifact_ttl_seconds=bounded("ASSESSMENT_RETENTION_SECONDS", 3600, 60, 86400),
            frontend_origins=origins or cls.frontend_origins,
        )
