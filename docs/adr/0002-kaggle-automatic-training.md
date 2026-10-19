# ADR-0002 — Automatic training on the user's own Kaggle account

Date: 2026-10-08 · Status: **Accepted** · Evidence: `notebook/spike/kaggle/` (`kernel.py`, `run_spike.py`, `results/results.json`)

## Context
Training on Colab means the user opens our notebook, picks a T4, runs every cell and keeps the tab open. Product feedback: training must start **automatically**; users shouldn't run cells. Free Colab can't do that: there is no API to start a notebook in someone's account, and its free-tier rules forbid automated or headless use. That is why the Colab notebook stays interactive.

Kaggle offers a free T4 GPU (~30 GPU-hours/week, sessions up to 12 h) and an **official API** to create and run a private notebook ("kernel") in the caller's account, choose the accelerator and enable internet.

## Spike (2026-10-08, the developer's own Kaggle account)
A private script kernel was pushed through the API with `machine_shape=NvidiaTeslaT4` and internet on, and its results downloaded. Everything passed:

| Check | Result |
|---|---|
| GPU assigned | 2 × Tesla T4 (15 GB each); training pinned to one with `CUDA_VISIBLE_DEVICES=0` |
| RAM / disk | 31 GB RAM, 20.9 GB free in `/kaggle/working` |
| Internet | Hugging Face 200, PyPI 200, our API through an ngrok tunnel 200 |
| Pinned stack install | ✅ 38 s (unsloth 2026.10.1, torch 2.11.0+cu128, transformers 5.17.0, trl 1.13.0, peft 0.21.1) on Python 3.13 |
| Qwen3.5 4B lora16, fp16, 30 steps | ✅ load 66 s, first step incl. kernel compile 324 s, **median step 1.77 s** (Colab: 3.0 s), peak VRAM 9.65 GB, loss 3.60 → 0.083, adapter 85 MB |
| Wall time, push → complete | ~10 min |

## Decision
1. Add a **Kaggle training backend** behind the existing `TrainingBackend` interface. It is the default when the user has connected Kaggle; the **Colab notebook stays** as the manual fallback (no Kaggle account, no phone verification, or gated models that need an HF token).
2. **Each user connects their own Kaggle account** in Settings (username + API token). DocTune never has a shared Kaggle account and never runs one user's job on another's quota. The token is encrypted at rest like LLM keys, never logged, never returned in full.
3. On "Start training", a worker issues the job token and pushes a **private** script kernel to the user's account (`NvidiaTeslaT4`, internet on, `sessionTimeoutSeconds` bounded by the estimate). The kernel installs the pinned stack plus our notebook package (embedded in the script) and runs the same `doctune_nb` code headlessly: env check → config → train (checkpoints) → evaluate → upload adapter → complete. Progress keeps flowing through the existing `/jobs/current/*` API, so the UI is unchanged.
4. A beat task polls kernel status. A kernel that errors or ends without completing the job is reported to the user; a session that ends mid-training is **re-launched automatically** (bounded attempts) and resumes from the latest checkpoint.
5. Cancel revokes the job token; the kernel stops at its next API call.

## Rule change
`CLAUDE.md` non-negotiable "the notebook stays interactive" now reads: the **Colab** notebook stays interactive; the **Kaggle** backend runs automatically through Kaggle's official API in the user's own account.

## Consequences / risks
- Users need a **phone-verified** Kaggle account (Kaggle's requirement for GPU and internet). Settings checks the token and shows the remaining weekly GPU quota.
- The job token is in the source of a private kernel in the user's own account (Kaggle has no API to pass secrets). It is job-scoped, expires, and is revoked when the job ends.
- Kaggle's API docs are incomplete for accelerator values; the kernel verifies it got a T4 and fails clearly otherwise.
- Kaggle may change its API or limits. The pluggable backend keeps Colab available.
- Kaggle offers OAuth for third-party apps; using it instead of pasted tokens is a later improvement (needs app registration).
- The optional GGUF/Drive/HF exports from the Colab notebook are not part of the Kaggle path; downloads and the playground work from the uploaded adapter.
