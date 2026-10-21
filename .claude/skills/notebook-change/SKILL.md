---
name: notebook-change
description: Create or modify DocTune's Colab training notebook and train.py template - job-token config fetch, dataset download, Unsloth QLoRA in fp16, checkpoint upload/resume via R2, heartbeats, evaluation, export (adapter/merged/GGUF). Use for anything under notebook/ or the /jobs/current/* contract it calls.
argument-hint: "[change]"
---

# Notebook change

Change: $ARGUMENTS. Load `ml-conventions`; delegate to **ml-engineer**.

## Cell structure (keep this order)
1. Intro markdown: what it does, select **Runtime → Change runtime type → T4 GPU**, keep the tab open.
2. Job token: `JOB_TOKEN = getpass("Paste your DocTune job token: ")` — never echoed, never saved to disk.
3. Install pinned deps (Unsloth, TRL, PEFT, transformers) — exact versions.
4. Fetch config + latest checkpoint: `GET /jobs/current/config`, `GET /jobs/current/checkpoint/latest`.
5. Download dataset via pre-signed URL; optional HF token via `getpass` for gated models.
6. Load base model 4-bit; LoRA config from preset; `fp16=True, bf16=False`.
7. Train with `UploadCheckpoint` callback (save every 5–10 min, zip + PUT pre-signed URL, heartbeat step/max_steps/loss); `resume_from_checkpoint` if one exists; visible progress bar.
8. Evaluate base vs tuned on held-out eval split → POST results.
9. Export: adapter → R2; merged + GGUF → user's Google Drive (and HF if user provided a token).
10. Final markdown: what to do next / how to resume.

## Checklist
- [ ] Interactive only: no background threads keeping it alive, no servers/tunnels/web UIs, one job per notebook
- [ ] No Google creds or HF tokens leave the notebook
- [ ] Resume restores weights, optimizer, scheduler, step, seed; same dataset version
- [ ] Graceful handling of 401/410 (expired/revoked token) with a clear message
- [ ] API contract changes in `/jobs/current/*` mirrored in FastAPI + tests
- [ ] Smoke test on a tiny model; resume test (save → restart → continues at step N)
