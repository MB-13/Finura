---
name: ml-conventions
description: Conventions for DocTune's ML side - base-model catalog and custom model validation, QLoRA presets on a free T4, notebook rules for Colab free tier, checkpoint/resume, evaluation, export formats, license compliance, dataset format, and the llama.cpp + RAG playground. Load whenever working on notebook/, training/, model selection, export or the playground.
user-invocable: false
---

# ML conventions

## Hardware & training
- Target: Colab free **T4, 16 GB, no bf16** → `fp16=True`. Training mode per catalog entry: `qlora4` (Qwen3, most custom models) or `lora16` (Qwen3.5 — Unsloth advises against QLoRA). Non-thinking chat template for Qwen3/3.5, identical at training, inference and export.
- Presets hide hyperparameters (e.g. Quick / Balanced / Thorough: epochs, LoRA r/alpha, LR, max_seq_len, batch × grad-accum). Advanced panel may override; validate ranges server-side.
- Pin every library version in the notebook; record versions in the job config so resume uses the same ones.
- Fixed seed per job.

## Base models
Curated catalog in one place (`backend/src/doctune/training/catalog.py`): id, display name, params, license, train_mode, fits_t4, time hint. Default: **Qwen3.5 4B (lora16)** — confirmed on a free T4 (ADR-0001). Qwen3 4B (qlora4) is the faster option/fallback. "Large" = Qwen3 8B QLoRA (fits, 8.3 GB; adapter-only export by default). Qwen3.5 9B is excluded (22 GB). Pinned versions are listed in ADR-0001.
Custom HF ID checks (HF API): Unsloth-supported architecture · ≤ ~10B params for qlora4, ≤ 4.5B for lora16 · license Apache-2.0/MIT passes, others warn + require acknowledgement · gated models need the user's HF token in the notebook. Store base_model_id + license on the project.

## Dataset format
JSONL, chat format: `{"messages":[{"role":"system",...}?,{"role":"user",...},{"role":"assistant",...}]}`. System message only when the "style as system prompt" toggle is on. 90/10 train/eval split fixed at review approval; ≤ 2,000 pairs.

## Notebook (Colab free-tier rules)
Interactive only — the user runs cells and watches. One job per notebook. No headless execution, keep-alive hacks, SSH, tunnels, web UIs, servers, or multi-account use. Tokens via `getpass`; Google creds and HF tokens never leave the notebook. Portable: must run anywhere with Python + GPU + internet.

## Checkpoints & heartbeats
Checkpoint every 5–10 min (adapter, optimizer, scheduler, RNG, step) → zip → pre-signed PUT to R2 → API records it; keep only latest. Heartbeat with step, max_steps, loss on each log step (throttled). 15 min silence → server marks `paused`.

## Evaluation
Base vs tuned on the held-out split; use the same LLM-judge rubric as dataset filtering (correctness vs source, style adherence) plus simple metrics. Report per-model scores + a few side-by-side examples.

## Export
Adapter (safetensors) → R2 first (project `ready`). Then optional GGUF Q4_K_M (2.8 GB for 4B, ~22 min) → Drive or HF. Merged 16-bit (9.3 GB for 4B) opt-in, HF only (free Drive 15 GB; Colab RAM 13.6 GB). Expect ~8 min startup per Qwen3.5 session (kernel compile + load), including resumes. Check free space/RAM first and skip with a clear message. Include README with base model, license, and how to run in Ollama.

## Licenses
Show license per model. Llama derivatives: name starts with "Llama-", include license file, show "Built with Llama". Never offer models whose license forbids the user's stated use without warning.

## Playground
llama.cpp server (GGUF, CPU on the 2 OCPU / 12 GB Oracle VM, one warm model, ≤ 4B; adapters converted with a current `convert_lora_to_gguf.py` so Qwen3.5 tags as `qwen35`) + top-k retrieval from the project's pgvector chunks injected into the prompt. Expect ~3–6 tokens/s for 4B; always offer local Ollama. Stream tokens to the web via SSE.
