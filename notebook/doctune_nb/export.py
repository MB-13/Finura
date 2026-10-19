"""Cells 9-10: adapter -> DocTune (R2) first and finish (project becomes `ready`); then optional exports.

Optional exports (ADR-0001):
- GGUF Q4_K_M (~2.8 GB for 4B, ~22 min on Colab, peak RAM ~10 GB) -> the user's Google Drive or Hugging Face.
- Merged 16-bit weights (~9.3 GB for 4B) -> Hugging Face only (opt-in; too big for a free 15 GB Drive).
- 8B+ GGUF/merged are experimental (untested on Colab RAM) and need `allow_experimental=True`.
Every export folder gets a README (base model, license, how to run in Ollama), a Modelfile with the same
non-thinking chat template used in training, and the base model license (+ NOTICE / "Built with Llama" for Llama).

Hugging Face tokens are only used here, in the notebook, and are never sent to DocTune.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from doctune_nb import __version__, ui
from doctune_nb import env as env_mod
from doctune_nb.api import DocTuneError

if TYPE_CHECKING:
    from doctune_nb.api import DocTuneClient, JobConfig
    from doctune_nb.evaluate import EvalResult
    from doctune_nb.train import TrainResult

GB = 1024**3
GGUF_GB_PER_B = 0.7  # measured: Qwen3.5 4B Q4_K_M = 2.78 GB
MERGED_GB_PER_B = 2.35  # measured: Qwen3.5 4B merged 16-bit = 9.34 GB
EXPERIMENTAL_PARAMS_B = 7.0
DEFAULT_DRIVE_ROOT = "/content/drive/MyDrive/DocTune"

LicenseFetcher = Callable[[str, str | None], str | None]


# ----------------------------------------------------------------------------------------------- naming


def slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")
    return s[:max_len].strip("-") or "model"


def model_name(cfg: JobConfig) -> str:
    """`{base}-{project}`; Llama derivatives must start with "Llama-" (Llama license, section 1.b.i)."""
    base = cfg.base_model_id.split("/")[-1]
    base = re.sub(r"(?i)-(unsloth-)?bnb-4bit$", "", base)
    name = f"{base}-{slug(cfg.project_name)}"
    if cfg.is_llama:
        name = re.sub(r"(?i)^meta-", "", name)
        name = re.sub(r"(?i)^llama-?", "", name)
        name = f"Llama-{name}"
    return name


def params_b(cfg: JobConfig, model: Any = None) -> float:
    """Billions of parameters: from the model id (e.g. "Qwen3.5-4B") or by counting (4-bit packs 2 per element)."""
    m = re.search(r"(\d+(?:\.\d+)?)[bB](?![a-zA-Z])", cfg.base_model_id.split("/")[-1])
    if m:
        return float(m.group(1))
    if model is not None:
        try:
            n = sum(p.numel() for p in model.parameters())
            return round(n * (2 if cfg.train_mode == "qlora4" else 1) / 1e9, 2)
        except Exception:
            pass
    return 4.0


# ----------------------------------------------------------------------------------------------- templates


def chat_family(cfg: JobConfig, chat_format: str | None = None) -> str | None:
    bid = cfg.base_model_id.lower()
    if chat_format in ("chatml", "llama3", "gemma") and chat_format:
        return chat_format
    if "qwen" in bid:
        return "chatml"
    if "llama-3" in bid or "llama3" in bid:
        return "llama3"
    if "gemma" in bid:
        return "gemma"
    return None


def is_thinking_model(cfg: JobConfig) -> bool:
    """Qwen3 / Qwen3.5 are hybrid thinking models: DocTune trains and serves them in non-thinking mode."""
    return bool(re.search(r"qwen3", cfg.base_model_id.lower()))


OLLAMA_TEMPLATES = {
    # ChatML with an empty <think> block for the assistant turn = Qwen3/3.5 non-thinking mode (as trained).
    "chatml": (
        "{{- if .System }}<|im_start|>system\n{{ .System }}<|im_end|>\n{{ end }}"
        "{{- range $i, $_ := .Messages }}"
        "{{- $last := eq (len (slice $.Messages $i)) 1 }}"
        '{{- if eq .Role "user" }}<|im_start|>user\n{{ .Content }}<|im_end|>\n'
        '{{ else if eq .Role "assistant" }}<|im_start|>assistant\n{{ .Content }}'
        "{{ if not $last }}<|im_end|>\n{{ end }}"
        "{{ end }}"
        '{{- if and (ne .Role "assistant") $last }}<|im_start|>assistant\n{{ THINK }}{{ end }}'
        "{{- end }}"
    ),
    "llama3": (
        "<|begin_of_text|>"
        "{{- if .System }}<|start_header_id|>system<|end_header_id|>\n\n{{ .System }}<|eot_id|>{{ end }}"
        "{{- range $i, $_ := .Messages }}"
        "{{- $last := eq (len (slice $.Messages $i)) 1 }}"
        "<|start_header_id|>{{ .Role }}<|end_header_id|>\n\n{{ .Content }}{{ if not $last }}<|eot_id|>{{ end }}"
        '{{- if and (ne .Role "assistant") $last }}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n'
        "{{ end }}"
        "{{- end }}"
    ),
    "gemma": (
        "{{- range $i, $_ := .Messages }}"
        "{{- $last := eq (len (slice $.Messages $i)) 1 }}"
        '{{- if eq .Role "user" }}<start_of_turn>user\n{{ if and $.System (eq $i 0) }}{{ $.System }}\n\n{{ end }}'
        "{{ .Content }}<end_of_turn>\n"
        '{{ else if eq .Role "assistant" }}<start_of_turn>model\n{{ .Content }}'
        "{{ if not $last }}<end_of_turn>\n{{ end }}{{ end }}"
        '{{- if and (ne .Role "assistant") $last }}<start_of_turn>model\n{{ end }}'
        "{{- end }}"
    ),
}
OLLAMA_STOPS = {
    "chatml": ["<|im_end|>", "<|im_start|>"],
    "llama3": ["<|eot_id|>", "<|start_header_id|>"],
    "gemma": ["<end_of_turn>"],
}


def modelfile(gguf_file: str, cfg: JobConfig, chat_format: str | None = None) -> str:
    family = chat_family(cfg, chat_format)
    lines = [
        f"# Ollama Modelfile for {model_name(cfg)} (made by DocTune notebook {__version__})",
        f"FROM ./{gguf_file}",
    ]
    if family:
        tmpl = OLLAMA_TEMPLATES[family].replace(
            "{{ THINK }}", "<think>\n\n</think>\n\n" if is_thinking_model(cfg) else ""
        )
        lines.append(f'TEMPLATE """{tmpl}"""')
        lines += [f'PARAMETER stop "{s}"' for s in OLLAMA_STOPS[family]]
    else:
        lines.append("# Chat template: Ollama uses the template embedded in the GGUF file.")
    if is_thinking_model(cfg):  # Qwen's recommended non-thinking sampling
        lines += ["PARAMETER temperature 0.7", "PARAMETER top_p 0.8", "PARAMETER top_k 20"]
    if cfg.dataset.system_prompt:
        sp = cfg.dataset.system_prompt.replace('"""', '"')
        lines.append(f'SYSTEM """{sp}"""')
    return "\n".join(lines) + "\n"


def readme(
    cfg: JobConfig,
    *,
    kind: str,
    final_step: int | None = None,
    final_loss: float | None = None,
    metrics: dict[str, Any] | None = None,
    gguf_file: str | None = None,
) -> str:
    name = model_name(cfg)
    hp = cfg.hyperparams
    lic = cfg.base_model_license or "unknown (check the base model page)"
    out = [
        f"# {name}",
        "",
        f"Fine-tuned with [DocTune]({cfg.project_url}) from **{cfg.base_model_id}** "
        f"({'16-bit LoRA' if cfg.train_mode == 'lora16' else '4-bit QLoRA'}, fp16).",
        "",
    ]
    if cfg.is_llama:
        out += ["**Built with Llama**", ""]
    out += [
        f"- Contents: {kind}",
        f"- Base model: https://huggingface.co/{cfg.base_model_id}",
        f"- License: {lic} (inherited from the base model; see LICENSE" + (" and NOTICE" if cfg.is_llama else "") + ")",
        f"- Training data: {cfg.dataset.train_count} question/answer pairs generated from your documents "
        f"({cfg.dataset.eval_count} held out for evaluation)",
        f"- Training: {final_step if final_step is not None else cfg.max_steps} steps, {hp.epochs} epoch(s), "
        f"LoRA r={hp.lora_r}/alpha={hp.lora_alpha}, lr {hp.learning_rate:g}, max length {hp.max_seq_len}, "
        f"seed {cfg.seed}" + (f", final loss {final_loss:.4f}" if final_loss is not None else ""),
    ]
    if metrics:
        shown = ", ".join(f"{k} {v}" for k, v in metrics.items() if v is not None)
        if shown:
            out.append(f"- Evaluation: {shown}")
    if is_thinking_model(cfg):
        out += [
            "",
            "The model was trained in **non-thinking** mode (`enable_thinking=False`). Use the same chat "
            "template when running it (the Modelfile below does).",
        ]
    if cfg.dataset.system_prompt:
        out += ["", "System prompt used in training:", "", "```", cfg.dataset.system_prompt, "```"]
    out += ["", "## Run it locally with Ollama", ""]
    if gguf_file:
        out += ["```bash", f"ollama create {name.lower()} -f Modelfile", f"ollama run {name.lower()}", "```"]
    else:
        out += [
            "This folder holds a LoRA adapter. The easiest way to run it locally is the GGUF export from the DocTune "
            "notebook (optional cell), then:",
            "",
            "```bash",
            f"ollama create {name.lower()} -f Modelfile",
            f"ollama run {name.lower()}",
            "```",
            "",
            "Or load it with PEFT:",
            "",
            "```python",
            "from peft import AutoPeftModelForCausalLM",
            "model = AutoPeftModelForCausalLM.from_pretrained('path/to/this/folder')",
            "```",
        ]
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------------------------------------- licenses


def hf_license_fetcher(repo_id: str, token: str | None) -> str | None:
    """Return the base model's LICENSE text from the Hub (tries the upstream repo for unsloth mirrors)."""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        return None
    short = repo_id.split("/")[-1]
    candidates = [repo_id]
    if repo_id.lower().startswith("unsloth/") and short.lower().startswith("qwen"):
        candidates.append(f"Qwen/{re.sub(r'(?i)-(unsloth-)?bnb-4bit$', '', short)}")
    for repo in candidates:
        for fname in ("LICENSE", "LICENSE.txt", "LICENSE.md", "license.txt"):
            try:
                return Path(hf_hub_download(repo, fname, token=token or None)).read_text(encoding="utf-8")
            except Exception:
                continue
    return None


LICENSE_URLS = {
    "apache-2.0": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    "mit": "https://opensource.org/license/mit",
}


def write_license_files(
    dest: Path, cfg: JobConfig, *, hf_token: str | None = None, fetcher: LicenseFetcher | None = None
) -> list[Path]:
    fetcher = fetcher or hf_license_fetcher
    dest.mkdir(parents=True, exist_ok=True)
    text = None
    try:
        text = fetcher(cfg.base_model_id, hf_token)
    except Exception:
        text = None
    lic = (cfg.base_model_license or "unknown").lower()
    if not text:
        url = LICENSE_URLS.get(lic, f"https://huggingface.co/{cfg.base_model_id}")
        text = (
            f"This model is a derivative of {cfg.base_model_id}, licensed under: {lic}.\n"
            f"Full license text: {url}\n"
            "You must comply with the base model's license when using or sharing this model.\n"
        )
    files = [dest / "LICENSE"]
    files[0].write_text(text, encoding="utf-8")
    if cfg.is_llama:
        notice = dest / "NOTICE"
        notice.write_text(
            "Built with Llama\n\n"
            f"{model_name(cfg)} is a fine-tune of {cfg.base_model_id}. Llama is licensed under the Llama Community "
            "License, Copyright (c) Meta Platforms, Inc. All Rights Reserved.\n"
            "Use of this model is subject to the Llama license and Acceptable Use Policy included with the base "
            "model.\n",
            encoding="utf-8",
        )
        files.append(notice)
    return files


def write_docs(
    dest: Path,
    cfg: JobConfig,
    *,
    kind: str,
    final_step: int | None = None,
    final_loss: float | None = None,
    metrics: dict[str, Any] | None = None,
    gguf_file: str | None = None,
    chat_format: str | None = None,
    hf_token: str | None = None,
    license_fetcher: LicenseFetcher | None = None,
) -> list[Path]:
    """README.md + Modelfile + LICENSE (+ NOTICE for Llama) into `dest`."""
    dest.mkdir(parents=True, exist_ok=True)
    files = write_license_files(dest, cfg, hf_token=hf_token, fetcher=license_fetcher)
    rd = dest / "README.md"
    rd.write_text(
        readme(cfg, kind=kind, final_step=final_step, final_loss=final_loss, metrics=metrics, gguf_file=gguf_file),
        encoding="utf-8",
    )
    mf = dest / "Modelfile"
    mf.write_text(modelfile(gguf_file or f"{model_name(cfg)}-Q4_K_M.gguf", cfg, chat_format), encoding="utf-8")
    return [rd, mf, *files]


# ----------------------------------------------------------------------------------------------- adapter


def save_adapter(result: TrainResult, cfg: JobConfig, dest: Path) -> Path:
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    result.model.save_pretrained(str(dest))
    from doctune_nb.data import text_tokenizer

    text_tokenizer(result.tokenizer).save_pretrained(str(dest))
    cfg_path = dest / "adapter_config.json"
    if cfg_path.exists():  # point at the catalog id (Unsloth may record a pre-quantized repo name)
        ac = json.loads(cfg_path.read_text())
        ac["base_model_name_or_path"] = cfg.base_model_id
        cfg_path.write_text(json.dumps(ac, indent=2))
    return dest


def zip_dir(src: Path, zip_path: Path) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(src).as_posix())
    return zip_path


def _metrics(eval_result: EvalResult | None) -> dict[str, float | None]:
    return eval_result.metrics() if eval_result is not None else {}


def upload_adapter_and_finish(
    client: DocTuneClient,
    cfg: JobConfig,
    result: TrainResult,
    eval_result: EvalResult | None = None,
    *,
    hf_token: str | None = None,
    license_fetcher: LicenseFetcher | None = None,
) -> dict[str, Any]:
    """Cell 9: adapter (safetensors + config + tokenizer + README/LICENSE) -> DocTune, then finish()."""
    ui.step("Uploading your fine-tuned adapter to DocTune")
    adir = save_adapter(result, cfg, result.workdir / "export" / "adapter")
    write_docs(
        adir,
        cfg,
        kind="LoRA adapter (safetensors)",
        final_step=result.final_step,
        final_loss=result.final_loss,
        metrics=_metrics(eval_result),
        chat_format=result.chat_format,
        hf_token=hf_token,
        license_fetcher=license_fetcher,
    )
    zpath = zip_dir(adir, result.workdir / "export" / "adapter.zip")
    ui.info(f"Adapter packaged ({ui.human_bytes(os.path.getsize(zpath))}). Uploading...")
    client.upload_artifact("adapter_safetensors", zpath)
    out = client.finish(_metrics(eval_result), {})
    ui.info("Done! Your model is ready in DocTune: " + (out.get("project_url") or cfg.project_url))
    ui.info("Optional: run the next cell to save a GGUF file (for Ollama / llama.cpp) to Google Drive or Hugging Face.")
    return out


# ----------------------------------------------------------------------------------------------- optional exports


def drive_mounted(root: str = DEFAULT_DRIVE_ROOT) -> bool:
    return (
        os.path.isdir("/content/drive/MyDrive")
        if root.startswith("/content/drive")
        else os.path.isdir(os.path.dirname(root.rstrip("/")) or "/")
    )


def check_space(path: str | os.PathLike[str], need_bytes: float, what: str) -> bool:
    try:
        free = env_mod.free_disk_bytes(path)
    except OSError:
        return True
    if free < need_bytes:
        ui.warn(
            f"Skipping {what}: needs about {ui.human_bytes(need_bytes)} free at {path}, only "
            f"{ui.human_bytes(free)} available."
        )
        return False
    return True


def check_ram(need_bytes: float, what: str) -> bool:
    avail = env_mod.available_ram_bytes()
    if avail is not None and avail < need_bytes:
        ui.warn(
            f"Skipping {what}: needs about {ui.human_bytes(need_bytes)} of free RAM, only "
            f"{ui.human_bytes(avail)} available. Restart the session and run only the export cell's "
            "prerequisites, or use the adapter instead."
        )
        return False
    return True


def find_gguf(out_dir: Path) -> Path | None:
    hits = sorted(set(glob.glob(f"{out_dir}*/**/*.gguf", recursive=True) + glob.glob(f"{out_dir}*/*.gguf")))
    q4 = [h for h in hits if "Q4_K_M" in os.path.basename(h).upper()]
    return Path(q4[0]) if q4 else None


def _hf_user(token: str) -> str:
    from huggingface_hub import HfApi

    return HfApi(token=token).whoami()["name"]


def _hf_upload_folder(folder: Path, repo_id: str, token: str) -> str:
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.create_repo(repo_id, private=True, exist_ok=True, repo_type="model")
    api.upload_folder(folder_path=str(folder), repo_id=repo_id, repo_type="model")
    return repo_id


def export_optional(
    client: DocTuneClient | None,
    cfg: JobConfig,
    result: TrainResult,
    eval_result: EvalResult | None = None,
    *,
    gguf_to: str | None = "drive",
    push_merged_to_hf: bool = False,
    hf_token: str | None = None,
    hf_repo: str | None = None,
    drive_root: str = DEFAULT_DRIVE_ROOT,
    allow_experimental: bool = False,
    license_fetcher: LicenseFetcher | None = None,
) -> dict[str, str | None]:
    """Cell 10: GGUF Q4_K_M -> Drive or HF; merged 16-bit -> HF (opt-in). Never blocks the adapter."""
    exports: dict[str, str | None] = {}
    if not result.use_unsloth:
        ui.warn("GGUF / merged exports need the GPU (Unsloth) path; skipped.")
        return exports
    pb = params_b(cfg, result.model)
    if pb >= EXPERIMENTAL_PARAMS_B and not allow_experimental:
        ui.warn(
            f"Exports for {pb:g}B models are experimental on free Colab (RAM); skipped. Your adapter is in "
            "DocTune. Set ALLOW_EXPERIMENTAL = True to try anyway."
        )
        return exports
    if gguf_to not in (None, "", "drive", "hf"):
        raise ValueError("gguf_to must be 'drive', 'hf' or None")
    if (gguf_to == "hf" or push_merged_to_hf) and not hf_token:
        ui.warn("Hugging Face export needs your HF token (cell 5); skipped the Hugging Face parts.")
        push_merged_to_hf = False
        gguf_to = None if gguf_to == "hf" else gguf_to
    name = model_name(cfg)
    from doctune_nb.data import text_tokenizer

    tok = text_tokenizer(result.tokenizer)
    work = result.workdir / "export"
    metrics = _metrics(eval_result)
    user = None
    if hf_token and (gguf_to == "hf" or push_merged_to_hf):
        user = hf_repo.split("/")[0] if hf_repo and "/" in hf_repo else _hf_user(hf_token)

    if gguf_to:
        gguf_est = pb * GGUF_GB_PER_B * GB
        ok = True
        if gguf_to == "drive" and not drive_mounted(drive_root):
            ui.warn("Google Drive is not mounted (cell 6); skipped the GGUF export. Your adapter is in DocTune.")
            ok = False
        ok = ok and check_space(work.parent, pb * 5 * GB, "the GGUF export (local disk)")
        ok = ok and check_ram(pb * 1.0 * GB + 1 * GB, "the GGUF export")
        if ok and gguf_to == "drive":
            ok = check_space(
                "/content/drive" if drive_root.startswith("/content/drive") else drive_root,
                gguf_est * 1.1,
                "the GGUF export (Google Drive)",
            )
        if ok:
            ui.step("GGUF Q4_K_M export (about 20-25 minutes: builds llama.cpp, then quantizes)")
            gdir = work / "gguf"
            shutil.rmtree(gdir, ignore_errors=True)
            try:
                result.model.save_pretrained_gguf(str(gdir), tok, quantization_method="q4_k_m")
                src = find_gguf(gdir)
                if src is None:
                    raise DocTuneError("no Q4_K_M .gguf file was produced")
                fname = f"{name}-Q4_K_M.gguf"
                bundle = work / "gguf_bundle"
                shutil.rmtree(bundle, ignore_errors=True)
                bundle.mkdir(parents=True)
                shutil.move(str(src), bundle / fname)
                shutil.rmtree(gdir, ignore_errors=True)
                write_docs(
                    bundle,
                    cfg,
                    kind="GGUF Q4_K_M",
                    final_step=result.final_step,
                    final_loss=result.final_loss,
                    metrics=metrics,
                    gguf_file=fname,
                    chat_format=result.chat_format,
                    hf_token=hf_token,
                    license_fetcher=license_fetcher,
                )
                if gguf_to == "drive":
                    target = Path(drive_root) / slug(cfg.project_name) / "gguf"
                    target.mkdir(parents=True, exist_ok=True)
                    for f in bundle.iterdir():
                        shutil.copy2(f, target / f.name)
                    exports["drive_path"] = str(target)
                    ui.info(f"GGUF saved to Google Drive: {target}")
                else:
                    repo = (hf_repo or f"{user}/{name}") + "-GGUF"
                    _hf_upload_folder(bundle, repo, hf_token or "")
                    exports["hf_repo"] = repo
                    ui.info(f"GGUF uploaded to https://huggingface.co/{repo} (private)")
                ui.info(
                    "Run it with Ollama (download the folder, then in it):\n"
                    f"  ollama create {name.lower()} -f Modelfile\n  ollama run {name.lower()}\n"
                    "Modelfile:\n" + (bundle / "Modelfile").read_text()
                )
            except Exception as exc:
                ui.warn(
                    f"GGUF export failed ({type(exc).__name__}: {str(exc)[:300]}). Your adapter is safe in DocTune."
                )

    if (
        push_merged_to_hf
        and hf_token
        and check_ram(pb * 0.5 * GB + 1 * GB, "the merged 16-bit export")
        and check_space(work.parent, pb * MERGED_GB_PER_B * GB * 1.2, "the merged 16-bit export (local disk)")
    ):
        repo = hf_repo or f"{user}/{name}"
        ui.step(f"Merged 16-bit weights -> Hugging Face {repo} (about 6 minutes + upload)")
        try:
            from huggingface_hub import HfApi

            HfApi(token=hf_token).create_repo(repo, private=True, exist_ok=True, repo_type="model")
            result.model.push_to_hub_merged(repo, tok, save_method="merged_16bit", token=hf_token)
            docs = work / "merged_docs"
            write_docs(
                docs,
                cfg,
                kind="merged 16-bit weights",
                final_step=result.final_step,
                final_loss=result.final_loss,
                metrics=metrics,
                chat_format=result.chat_format,
                hf_token=hf_token,
                license_fetcher=license_fetcher,
            )
            (docs / "Modelfile").unlink(missing_ok=True)
            _hf_upload_folder(docs, repo, hf_token)
            exports["hf_repo"] = exports.get("hf_repo") or repo
            ui.info(f"Merged weights uploaded to https://huggingface.co/{repo} (private)")
        except Exception as exc:
            ui.warn(f"Merged export failed ({type(exc).__name__}: {str(exc)[:300]}).")

    if exports and client is not None:
        try:  # records where the exports went (no tokens are sent)
            client.finish(metrics, exports)
        except Exception as exc:
            ui.warn(f"Could not record the export location in DocTune ({exc}).")
    if not exports:
        ui.info("No optional exports were made. Your adapter is in DocTune.")
    return exports
