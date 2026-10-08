"""Load ``proofline.toml`` + environment variables into one frozen settings object."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "proofline.toml"


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Tiny .env reader (no extra dependency). Real env vars always win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    raw: dict
    github_token: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    weights: dict = field(default_factory=dict)

    def section(self, name: str) -> dict:
        return self.raw.get(name, {})


def load_settings(path: str | Path | None = None) -> Settings:
    _load_dotenv()
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    with open(cfg_path, "rb") as fh:
        raw = tomllib.load(fh)
    return Settings(
        raw=raw,
        github_token=os.getenv("GITHUB_TOKEN") or None,
        llm_api_key=os.getenv("LLM_API_KEY") or None,
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        weights=raw["weights"],
    )
