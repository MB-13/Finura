import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[3]
DEV_FERNET_KEY = "dev-only-key-do-not-use-in-prod-AAAAAAAAAAA="


class Settings(BaseSettings):
    # the test suite (ENV=test) never reads backend/.env, so local settings can't leak into tests
    model_config = SettingsConfigDict(
        env_file=None if os.environ.get("ENV") == "test" else BACKEND_DIR / ".env", extra="ignore"
    )

    env: Literal["local", "test", "staging", "prod"] = "local"
    app_version: str = "0.1.0"

    # database: async URL for the API, sync URL for Celery and Alembic
    database_url: str = "postgresql+asyncpg://doctune:doctune@localhost:55432/doctune"
    database_url_sync: str = "postgresql+psycopg://doctune:doctune@localhost:55432/doctune"
    redis_url: str = "redis://localhost:56379/0"

    # auth: Supabase issues JWTs. Asymmetric keys come from JWKS; the legacy HS256 secret is optional.
    supabase_url: str = "http://localhost:54321"
    supabase_jwt_aud: str = "authenticated"
    supabase_jwt_secret: SecretStr | None = None
    jwt_jwks_json: str | None = None
    # server-side only: lets account deletion remove the Supabase login too
    supabase_service_role_key: SecretStr | None = (
        None  # static JWKS (tests / offline dev) instead of fetching from Supabase
    )

    # storage: "local" serves signed URLs from this API; "r2" comes later
    storage_backend: Literal["local"] = "local"
    storage_local_dir: Path = BACKEND_DIR / ".data" / "storage"
    storage_signing_key: SecretStr = SecretStr("dev-only-storage-signing-key-change-me")

    # embeddings: "e5" (real model, needs the `ml` extra) or "hash" (tests / laptops)
    embedding_backend: Literal["e5", "hash"] = "e5"

    # encryption for users' LLM keys: comma-separated Fernet keys, first one encrypts.
    # The default is a PUBLIC dev-only key; production refuses to start with it.
    key_encryption_keys: SecretStr = SecretStr(DEV_FERNET_KEY)

    # email: "console" logs, "smtp" (Mailpit in dev), "resend" (production)
    email_backend: Literal["console", "smtp", "resend"] = "console"
    email_from: str = "DocTune <noreply@doctune.local>"
    smtp_host: str = "localhost"
    smtp_port: int = 51025
    resend_api_key: SecretStr | None = None

    # optional read-only HF token: higher rate limits for model metadata checks (never used for weights)
    hf_token_readonly: SecretStr | None = None

    # llama.cpp checkout (convert_lora_to_gguf.py) and llama-server binary for the playground
    llama_cpp_dir: Path | None = None
    # Python with torch + transformers for convert_lora_to_gguf.py; kept out of the API venv (default: this one)
    llama_convert_python: str | None = None
    llama_server_bin: str = "llama-server"
    # largest base model (billions of params) the playground will load: 4B fits the 12 GB free VM next to the
    # API and workers (D19); a machine with more RAM (e.g. local dev) can raise it to 8 for Qwen3 8B
    playground_max_params_b: float = 4.5
    llama_models_dir: Path = BACKEND_DIR / ".data" / "models"
    llama_threads: int = 2
    llama_host: str = "127.0.0.1"  # where the API reaches the inference worker's llama-server

    web_origin: str = "http://localhost:5173"
    public_api_url: str = "http://localhost:8000"

    sentry_dsn: str | None = None
    log_level: str = "INFO"
    log_json: bool = False

    notebook_url: str = (
        "https://colab.research.google.com/github/doctune/doctune/blob/main/notebook/doctune_train.ipynb"
    )
    notebook_version: str = "0.0.0"
    # the notebook package (pyproject.toml + doctune_nb/) that is embedded in Kaggle kernels
    notebook_src_dir: Path = BACKEND_DIR.parent / "notebook"

    # product limits (design doc)
    max_file_mb: int = 20
    max_project_mb: int = 50
    max_pairs: int = 2000

    cors_extra_origins: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_dev_secrets_in_prod(self) -> "Settings":
        if self.env in ("staging", "prod"):
            if self.key_encryption_keys.get_secret_value() == DEV_FERNET_KEY:
                raise ValueError("KEY_ENCRYPTION_KEYS must be set outside local/test")
            if "dev-only" in self.storage_signing_key.get_secret_value():
                raise ValueError("STORAGE_SIGNING_KEY must be set outside local/test")
        return self

    @property
    def jwt_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def jwks_url(self) -> str:
        return f"{self.jwt_issuer}/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
