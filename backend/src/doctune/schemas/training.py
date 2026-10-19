import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from doctune.models.training import ArtifactKind, EvalState, JobState, PauseReason
from doctune.training.presets import Advanced, Hyperparams


class BaseModelOut(BaseModel):
    id: str
    display_name: str
    params_b: float
    license: str
    train_mode: Literal["lora16", "qlora4"]
    fits_t4: Literal["yes", "unconfirmed"]
    vram_gb: float
    recommended: bool
    playground_supported: bool
    note: str | None
    est_minutes: dict[str, float]  # per preset, for the user's current dataset size (or 500 pairs)


class ModelCheckIn(BaseModel):
    hf_id: str = Field(min_length=3, max_length=200)


class PresetOut(BaseModel):
    key: str
    name: str
    description: str
    hyperparams: Hyperparams


class TrainingCreate(BaseModel):
    base_model_id: str = Field(min_length=3, max_length=200)
    preset: Literal["quick", "balanced", "thorough"] = "balanced"
    advanced: Advanced | None = None
    license_ack: bool = False
    backend: Literal["kaggle", "colab"] = "colab"


class TrainingJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    state: JobState
    backend: Literal["kaggle", "colab"]
    external_url: str | None
    launch_attempts: int
    base_model_id: str
    base_model_license: str | None
    is_llama: bool
    train_mode: str
    preset: str
    hyperparams: dict[str, Any]
    current_step: int
    max_steps: int
    last_loss: float | None
    last_heartbeat_at: datetime | None
    pause_reason: PauseReason | None
    runtime_info: dict[str, Any] | None
    exports: dict[str, Any] | None
    metrics: dict[str, Any] | None
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    token_prefix: str | None = None
    token_expires_at: datetime | None = None
    checkpoint_step: int | None = None
    checkpoint_uploaded_at: datetime | None = None
    est_minutes: float | None = None


class TrainingSwitch(BaseModel):
    backend: Literal["kaggle"] = "kaggle"


class TrainingCreated(BaseModel):
    job: TrainingJobOut
    token: str | None = None  # Colab only, shown once
    notebook_url: str | None = None  # Colab only


class TokenOut(BaseModel):
    token: str
    expires_at: datetime


class MetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step: int
    loss: float | None
    lr: float | None
    at: datetime


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ArtifactKind
    size_bytes: int
    meta: dict[str, Any] | None
    expires_at: datetime | None


class DownloadOut(BaseModel):
    url: str
    expires_at: int


class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    state: EvalState
    n_items: int
    base_scores: dict[str, float] | None
    tuned_scores: dict[str, float] | None
    samples: list[dict[str, Any]] | None
    metrics: dict[str, Any] | None
    error: str | None


# ---------------- notebook side ----------------


class DatasetRef(BaseModel):
    train_url: str
    eval_url: str
    sha256_train: str
    sha256_eval: str
    train_count: int
    eval_count: int
    system_prompt: str | None


class JobConfig(BaseModel):
    job_id: uuid.UUID
    project_name: str
    base_model_id: str
    base_model_license: str | None
    is_llama: bool
    train_mode: Literal["lora16", "qlora4"]
    hyperparams: Hyperparams
    seed: int
    max_steps: int
    lib_versions: dict[str, str]
    dataset: DatasetRef
    checkpoint_every_minutes: int
    heartbeat_every_seconds: int
    eval_max_items: int
    notebook_min_version: str
    project_url: str


class RuntimeInfo(BaseModel):
    gpu_name: str | None = Field(default=None, max_length=100)
    vram_gb: float | None = None
    platform: str | None = Field(default=None, max_length=50)
    python: str | None = Field(default=None, max_length=20)
    torch: str | None = Field(default=None, max_length=40)
    cuda: str | None = Field(default=None, max_length=20)
    notebook_version: str | None = Field(default=None, max_length=20)


class StartIn(BaseModel):
    runtime: RuntimeInfo
    resumed_from_step: int | None = Field(default=None, ge=0)


class HeartbeatIn(BaseModel):
    step: int = Field(ge=0)
    max_steps: int = Field(ge=1)
    loss: float | None = None
    lr: float | None = None
    epoch: float | None = None


class HeartbeatOut(BaseModel):
    ok: bool = True
    cancel_requested: bool = False


class CheckpointLatest(BaseModel):
    exists: bool
    step: int | None = None
    url: str | None = None
    sha256: str | None = None


class UploadRequest(BaseModel):
    size_bytes: int = Field(gt=0)
    step: int | None = Field(default=None, ge=0)


class UploadComplete(BaseModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)
    step: int | None = Field(default=None, ge=0)


class ArtifactUploadRequest(UploadRequest):
    kind: Literal["adapter_safetensors", "eval_generations"]


class ArtifactUploadComplete(UploadComplete):
    kind: Literal["adapter_safetensors", "eval_generations"]


class UploadUrl(BaseModel):
    url: str
    headers: dict[str, str]
    expires_at: int


class PauseIn(BaseModel):
    reason: Literal["session_ended", "idle_timeout", "no_gpu", "stopped", "user_stopped"]
    step: int | None = Field(default=None, ge=0)


class TrainingCompleteIn(BaseModel):
    final_step: int = Field(ge=0)
    final_loss: float | None = None
    train_runtime_s: float | None = None


class FinishIn(BaseModel):
    metrics: dict[str, float | None] = Field(default_factory=dict)
    exports: dict[str, str | None] = Field(default_factory=dict)


class FailIn(BaseModel):
    error: str = Field(max_length=2000)
    step: int | None = None
    fatal: bool = False


class Ok(BaseModel):
    ok: bool = True
    project_url: str | None = None
