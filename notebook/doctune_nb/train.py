"""Cell 7: download data + latest checkpoint, start(), train with callbacks, report completion.

GPU path: Unsloth FastLanguageModel, fp16 (T4 has no bf16), train_mode `lora16` (16-bit LoRA) or `qlora4`
(4-bit QLoRA), non-thinking chat template, train on responses only. These code paths mirror the spike that was run
on a free T4 (notebook/spike/doctune_spike_t4.ipynb, ADR-0001).

CPU smoke path (`use_unsloth=False`): plain transformers + PEFT + TRL, used by tests/CI only.
"""

from __future__ import annotations

import dataclasses
import gc
import math
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from doctune_nb import __version__, ui
from doctune_nb import env as env_mod
from doctune_nb.api import ConflictError, DocTuneError, TokenError
from doctune_nb.callbacks import HeartbeatCallback, TimedCheckpointCallback, UploadCheckpointCallback, unzip_checkpoint
from doctune_nb.data import (
    CHAT_MARKERS,
    DatasetFiles,
    detect_chat_format,
    download_dataset,
    format_conversations,
    load_jsonl,
    text_tokenizer,
    to_hf_dataset,
)

if TYPE_CHECKING:
    from doctune_nb.api import DocTuneClient, JobConfig
    from doctune_nb.env import Env

LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

OOM_ADVICE = (
    "The GPU ran out of memory before training could start. On the DocTune project page, pick a smaller model "
    "(for example Qwen3 4B, which uses 4-bit QLoRA) or the Quick preset (shorter max length), then run the new "
    "notebook."
)


class JobCancelled(ui.StopNotebook):
    """The job was cancelled from the dashboard, its token was rejected, or it has already ended."""


class TrainingOOM(ui.StopNotebook):
    """Out of GPU memory before the first step (reported to DocTune as a fatal failure)."""


class TrainingInterrupted(ui.StopNotebook):
    """Ctrl-C / stop button (or SIGTERM in headless runs): a checkpoint was saved and DocTune told to pause."""


GATED_HINT = "the model may be gated: enter your Hugging Face token in cell 5"


@dataclass
class TrainResult:
    model: Any
    tokenizer: Any
    trainer: Any
    final_step: int
    final_loss: float | None
    runtime_s: float | None
    data: DatasetFiles
    workdir: Path
    use_unsloth: bool
    chat_format: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------------------------------- helpers


def job_dir(cfg: JobConfig, root: str | os.PathLike[str] | None = None) -> Path:
    d = Path(root) if root else env_mod.workdir()
    d = d / "jobs" / cfg.job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def checkpoint_meta(cfg: JobConfig) -> dict[str, Any]:
    return {
        "job_id": cfg.job_id,
        "base_model_id": cfg.base_model_id,
        "train_mode": cfg.train_mode,
        "seed": cfg.seed,
        "dataset_sha256_train": cfg.dataset.sha256_train,
        "lib_versions": cfg.lib_versions,
        "notebook_version": __version__,
    }


def is_oom(exc: BaseException) -> bool:
    name = type(exc).__name__
    return name == "OutOfMemoryError" or "CUDA out of memory" in str(exc) or "out of memory" in str(exc).lower()


def warmup_steps(ratio: float, max_steps: int) -> int:
    return int(math.ceil(max(0.0, ratio) * max_steps))


def make_dataclass_args(cls: Any, kwargs: dict[str, Any]) -> Any:
    """Build a TrainingArguments-like dataclass, dropping keys this library version doesn't know (with a note)."""
    known = {f.name for f in dataclasses.fields(cls)} if dataclasses.is_dataclass(cls) else None
    if known is not None:
        dropped = sorted(k for k in kwargs if k not in known)
        if dropped:
            ui.warn(f"{cls.__name__} does not support {dropped}; ignored.")
        kwargs = {k: v for k, v in kwargs.items() if k in known}
    return cls(**kwargs)


def latest_local_checkpoint(ckpt_root: Path) -> tuple[Path, int] | None:
    best: tuple[Path, int] | None = None
    for d in ckpt_root.glob("checkpoint-*"):
        try:
            step = int(d.name.split("-")[-1])
        except ValueError:
            continue
        if (d / "trainer_state.json").exists() and (best is None or step > best[1]):
            best = (d, step)
    return best


def prepare_resume(client: DocTuneClient, cfg: JobConfig, jdir: Path) -> tuple[Path | None, int]:
    """Fetch the server's latest checkpoint (or reuse an equal/newer local one). Returns (path, step)."""
    ckpt_root = jdir / "ckpt"
    ckpt_root.mkdir(parents=True, exist_ok=True)
    latest = client.checkpoint_latest()
    local = latest_local_checkpoint(ckpt_root)
    server_step = int(latest.get("step") or 0) if latest.get("exists") else -1
    if local and local[1] > 0 and local[1] >= server_step:  # same session, possibly newer than the last upload
        ui.info(f"Using the checkpoint from this session at step {local[1]}.")
        return local
    if server_step < 0:
        return None, 0
    ui.info(f"Downloading your checkpoint from step {server_step}...")
    zip_path = client.download_checkpoint(jdir / "downloads" / "checkpoint.zip", latest)
    assert zip_path is not None
    for old in ckpt_root.glob("checkpoint-*"):
        shutil.rmtree(old, ignore_errors=True)
    target, meta = unzip_checkpoint(zip_path, ckpt_root / f"checkpoint-{server_step}")
    zip_path.unlink(missing_ok=True)
    if meta.get("dataset_sha256_train") and meta["dataset_sha256_train"] != cfg.dataset.sha256_train:
        raise ui.StopNotebook(
            "The saved checkpoint was trained on a different dataset than this job. Start a new training run from "
            "the project page."
        )
    if meta.get("seed") is not None and meta["seed"] != cfg.seed:
        ui.warn("The checkpoint was saved with a different seed; results may differ slightly.")
    if meta.get("lib_versions") and meta["lib_versions"] != cfg.lib_versions:
        ui.warn("The checkpoint was saved with different library versions; results may differ slightly.")
    return target, server_step


# ----------------------------------------------------------------------------------------------- model


def load_model(cfg: JobConfig, *, hf_token: str | None, use_unsloth: bool, fp16: bool) -> tuple[Any, Any]:
    hp = cfg.hyperparams
    if use_unsloth:
        import torch
        import unsloth  # noqa: F401  (must be imported before transformers / trl / peft)
        from unsloth import FastLanguageModel

        kwargs = dict(
            model_name=cfg.base_model_id,
            max_seq_length=hp.max_seq_len,
            dtype=torch.float16,  # T4: no bf16
            load_in_4bit=(cfg.train_mode == "qlora4"),
            token=hf_token or None,
        )
        try:
            model, tok = FastLanguageModel.from_pretrained(**kwargs)
        except Exception as exc:
            if isinstance(exc, (KeyboardInterrupt, TokenError)) or is_oom(exc) or _looks_gated(exc):
                raise
            ui.warn(f"FastLanguageModel could not load the model ({type(exc).__name__}); trying FastModel.")
            from unsloth import FastModel

            model, tok = FastModel.from_pretrained(**kwargs)
        model = FastLanguageModel.get_peft_model(
            model,
            r=hp.lora_r,
            lora_alpha=hp.lora_alpha,
            target_modules=LORA_TARGETS,
            lora_dropout=0,
            bias="none",
            use_gradient_checkpointing="unsloth",
            random_state=cfg.seed,
        )
        return model, tok

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(cfg.seed)
    tok = AutoTokenizer.from_pretrained(cfg.base_model_id, token=hf_token or None)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        cfg.base_model_id, token=hf_token or None, dtype=torch.float16 if fp16 else torch.float32
    )
    names = {n.split(".")[-1] for n, _ in model.named_modules()}
    targets = [t for t in LORA_TARGETS if t in names] or "all-linear"
    lora = LoraConfig(
        r=cfg.hyperparams.lora_r,
        lora_alpha=cfg.hyperparams.lora_alpha,
        target_modules=targets,
        lora_dropout=0.0,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora)
    for p in model.parameters():  # fp16 AMP needs fp32 trainable weights
        if p.requires_grad:
            p.data = p.data.float()
    return model, tok


def _looks_gated(exc: BaseException) -> bool:
    s = str(exc).lower()
    return "gated" in s or "401" in s or "403" in s or "access to model" in s


def build_trainer(
    model: Any,
    tok: Any,
    train_ds: Any,
    cfg: JobConfig,
    out_dir: Path,
    callbacks: list[Any],
    *,
    use_unsloth: bool,
    fp16: bool,
    batch_size: int,
    grad_accum: int,
    chat_format: str | None,
) -> Any:
    from trl import SFTConfig, SFTTrainer

    hp = cfg.hyperparams
    report_to = "none"
    if os.environ.get("WANDB_API_KEY"):
        try:
            import wandb  # noqa: F401

            report_to = "wandb"
        except ImportError:
            pass
    has_cuda = fp16
    args = make_dataclass_args(
        SFTConfig,
        dict(
            output_dir=str(out_dir),
            dataset_text_field="text",
            max_length=hp.max_seq_len,
            packing=False,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=grad_accum,
            max_steps=cfg.max_steps,
            learning_rate=hp.learning_rate,
            warmup_steps=warmup_steps(hp.warmup_ratio, cfg.max_steps),
            lr_scheduler_type=hp.lr_scheduler,
            optim=hp.optim if has_cuda else "adamw_torch",
            weight_decay=hp.weight_decay,
            logging_steps=1 if cfg.max_steps <= 50 else 5,
            fp16=fp16,
            bf16=False,
            seed=cfg.seed,
            data_seed=cfg.seed,
            report_to=report_to,
            # time-based saves come from TimedCheckpointCallback; save_steps=max_steps adds a final checkpoint
            save_strategy="steps",
            save_steps=cfg.max_steps,
            save_total_limit=1,
            use_cpu=not has_cuda,
            dataloader_pin_memory=has_cuda,
        ),
    )
    ttok = text_tokenizer(tok)
    try:
        trainer = SFTTrainer(model=model, processing_class=ttok, train_dataset=train_ds, args=args, callbacks=callbacks)
    except TypeError:
        trainer = SFTTrainer(model=model, tokenizer=ttok, train_dataset=train_ds, args=args, callbacks=callbacks)
    if use_unsloth:
        if chat_format:
            from unsloth.chat_templates import train_on_responses_only

            inst, resp = CHAT_MARKERS[chat_format]
            trainer = train_on_responses_only(trainer, instruction_part=inst, response_part=resp)
        else:
            ui.warn("Unknown chat format: training on the full conversation text instead of answers only.")
    return trainer


def _save_now(trainer: Any, uploader: UploadCheckpointCallback) -> bool:
    """Write a full checkpoint (adapter + optimizer + scheduler + RNG + state) right now and upload it."""
    step = trainer.state.global_step
    if step <= 0:
        return False
    try:
        trainer._save_checkpoint(trainer.model, trial=None)
    except Exception as exc:
        ui.warn(f"Could not write a checkpoint now ({type(exc).__name__}); the last saved one will be used.")
        return False
    return uploader.upload_dir(Path(trainer.args.output_dir) / f"checkpoint-{step}", step)


def _free_gpu() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


# ----------------------------------------------------------------------------------------------- run


def run(
    client: DocTuneClient,
    cfg: JobConfig,
    env: Env | None = None,
    *,
    hf_token: str | None = None,
    workdir: str | os.PathLike[str] | None = None,
    use_unsloth: bool | None = None,
    extra_callbacks: list[Any] | None = None,
    interrupt_reason: str = "user_stopped",
    gated_hint: str = GATED_HINT,
) -> TrainResult:
    """`interrupt_reason`: pause reason sent when training is interrupted (KeyboardInterrupt). The notebook's stop
    button is "user_stopped"; headless runs translate SIGTERM (session ending) into "session_ended".
    `gated_hint`: appended to the error when the base model looks gated (headless runs have no HF token)."""
    env = env or env_mod.detect()
    use_unsloth = env.has_gpu if use_unsloth is None else use_unsloth
    fp16 = env.has_gpu
    ui.step("Training")
    if cfg.lib_versions and use_unsloth:
        env_mod.warn_version_mismatches(cfg.lib_versions)
    jdir = job_dir(cfg, workdir)
    files = download_dataset(client, cfg, jdir)
    resume_path, start_step = prepare_resume(client, cfg, jdir)

    try:
        client.start(env.runtime(), resumed_from_step=start_step if resume_path else None)
    except ConflictError as exc:
        if exc.code == "job_ended":
            raise JobCancelled(f"This training job has already ended. Open {cfg.project_url}") from None
        raise
    if resume_path:
        ui.info(f"Resuming from step {start_step} of {cfg.max_steps} ({ui.percent(start_step, cfg.max_steps)}%).")

    hb = HeartbeatCallback(client, cfg.max_steps, every_s=cfg.heartbeat_every_seconds)
    timed = TimedCheckpointCallback(cfg.checkpoint_every_minutes)
    uploader = UploadCheckpointCallback(client, checkpoint_meta(cfg), jdir / "upload")
    callbacks = [hb, timed, uploader, *(extra_callbacks or [])]

    trainer = None
    try:
        mode = "16-bit LoRA" if cfg.train_mode == "lora16" else "4-bit QLoRA"
        precision = "fp16" if fp16 else "fp32 on CPU, smoke test"
        ui.info(f"Loading {cfg.base_model_id} ({mode}, {precision}). This takes a few minutes.")
        t_load = time.monotonic()
        model, tok = load_model(cfg, hf_token=hf_token, use_unsloth=use_unsloth, fp16=fp16)
        ui.info(f"Model loaded in {time.monotonic() - t_load:.0f} s.")
        chat_format = detect_chat_format(tok)
        texts = format_conversations(tok, load_jsonl(files.train))
        train_ds = to_hf_dataset(texts)
        if use_unsloth and "qwen3.5" in cfg.base_model_id.lower():
            ui.info(ui.QWEN35_COMPILE_NOTE)

        batch, accum = cfg.hyperparams.batch_size, cfg.hyperparams.grad_accum
        oom_retried = False
        while True:
            trainer = build_trainer(
                model,
                tok,
                train_ds,
                cfg,
                jdir / "ckpt",
                callbacks,
                use_unsloth=use_unsloth,
                fp16=fp16,
                batch_size=batch,
                grad_accum=accum,
                chat_format=chat_format,
            )
            try:
                out = trainer.train(resume_from_checkpoint=str(resume_path) if resume_path else None)
                break
            except Exception as exc:
                if not is_oom(exc):
                    raise
                step = trainer.state.global_step
                if step == 0 and start_step == 0:
                    _report(client.fail, f"out_of_memory: {OOM_ADVICE}", step=0, fatal=True)
                    raise TrainingOOM(OOM_ADVICE) from None
                local = latest_local_checkpoint(jdir / "ckpt")
                if oom_retried or batch <= 1 or local is None:
                    raise
                oom_retried = True
                batch, accum = batch // 2, accum * 2
                resume_path, start_step = local
                ui.warn(
                    f"Out of GPU memory at step {step}. Retrying from step {start_step} with batch {batch} x "
                    f"{accum} (same effective batch)."
                )
                del trainer
                _free_gpu()
    except KeyboardInterrupt:
        step = trainer.state.global_step if trainer is not None else start_step
        ui.warn("Stopping - saving a checkpoint first...")
        if trainer is not None:
            _save_now(trainer, uploader)
        _report(client.pause, interrupt_reason, step)
        raise TrainingInterrupted(ui.pause_message(interrupt_reason, step, cfg.max_steps)) from None
    except ui.StopNotebook:
        raise
    except Exception as exc:
        step = trainer.state.global_step if trainer is not None else start_step
        msg = f"{type(exc).__name__}: {str(exc)[:500]}"
        if _looks_gated(exc) and trainer is None:
            msg += f" ({gated_hint})"
        _report(client.fail, msg, step=step, fatal=False)
        ui.error(f"Training stopped with an error at step {step}: {msg}")
        ui.error(ui.pause_message("stopped", step, cfg.max_steps))
        raise

    if hb.cancelled:
        raise JobCancelled("Training was cancelled from the DocTune dashboard. Nothing more to do here.")

    final_step = int(trainer.state.global_step)
    final_loss = hb.loss if hb.loss is not None else getattr(out, "training_loss", None)
    runtime = (getattr(out, "metrics", None) or {}).get("train_runtime")
    if hb.nan_steps and final_loss is None:
        ui.warn("The final loss is not a number. The model may be unusable; consider the Qwen3 4B (QLoRA) option.")
    try:
        client.training_complete(final_step, final_loss, runtime)
    except DocTuneError as exc:
        ui.warn(f"Could not report completion ({exc}); evaluation will report it.")
    ui.info(
        f"Training finished at step {final_step}/{cfg.max_steps}"
        + (f", final loss {final_loss:.4f}." if final_loss is not None else ".")
    )
    return TrainResult(
        model=trainer.model,
        tokenizer=tok,
        trainer=trainer,
        final_step=final_step,
        final_loss=final_loss,
        runtime_s=runtime,
        data=files,
        workdir=jdir,
        use_unsloth=use_unsloth,
        chat_format=chat_format,
        extra={"uploaded_steps": list(uploader.uploaded_steps)},
    )


def _report(fn: Any, *args: Any, **kwargs: Any) -> None:
    try:
        fn(*args, **kwargs)
    except Exception as exc:
        ui.warn(f"Could not reach DocTune ({exc}).")
