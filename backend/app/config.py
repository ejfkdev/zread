# -*- coding: utf-8 -*-
"""Settings via pydantic-settings (env > .env file > defaults)."""

from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Override any field via an env var of the
    same (upper-cased) name, or via a ``.env`` file next to the backend.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Server ---------------------------------------------------------
    host: str = "0.0.0.0"
    port: int = 8709
    cors_origins: List[str] = ["*"]
    # Shared secret required on every /api/v1 request (Authorization: Bearer).
    # When unset the API is open — log a warning so operators notice.
    backend_api_key: str = ""

    # --- GitHub (the backend fetches repos itself) ----------------------
    github_token: str = ""
    github_api_url: str = "https://api.github.com"
    github_raw_url: str = "https://raw.githubusercontent.com"

    # --- OpenAI-compatible LLM / embeddings -----------------------------
    # Any OpenAI-compatible endpoint: OpenAI, Azure, OpenRouter, Ollama, LiteLLM...
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    embed_model: str = "text-embedding-3-small"
    embed_dim: int = 1536
    embed_batch_size: int = 100
    llm_timeout: float = 120.0

    # --- Storage --------------------------------------------------------
    db_path: str = "data/zread-ai.db"

    # --- Indexing tuning ------------------------------------------------
    chunk_max_tokens: int = 800
    chunk_overlap_tokens: int = 100
    index_concurrency: int = 8
    index_max_files: int = 2000
    index_max_file_bytes: int = 512 * 1024  # 512 KiB per file
    doc_extensions: List[str] = [".md", ".mdx", ".markdown", ".rst"]
    doc_globs: List[str] = ["README*"]

    # --- Retrieval ------------------------------------------------------
    retrieval_top_k: int = 8
    talk_max_history: int = 12  # prior messages fed to the LLM

    @field_validator("cors_origins", "doc_extensions", "doc_globs", mode="before")
    @classmethod
    def _split_csv(cls, v):
        """Allow comma-separated env values: CORS_ORIGINS=a,b -> ["a","b"]."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    def db_file(self) -> Path:
        p = Path(self.db_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def github_headers(self) -> dict:
        h = {"Accept": "application/vnd.github+json"}
        if self.github_token:
            h["Authorization"] = f"Bearer {self.github_token}"
        return h


settings = Settings()
