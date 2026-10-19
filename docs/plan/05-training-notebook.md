# 05 — Training & Notebook

## 1. Base model catalog (`backend/src/doctune/training/catalog.py`)
Single source for UI cards, validation and the playground. Fields: `id` (HF repo), `display_name`, `params_b`, `license`, `fits_t4` (`yes`/`unconfirmed`), `unsloth_id` (pre-quantized `unsloth/...-bnb-4bit` repo if available — faster download), `chat_template`, `max_seq_len_default`, `time_hint` (minutes per 1,000 pairs per epoch on T4), `playground_gguf` (base GGUF repo/file for llama.cpp, Q4_K_M), `recommended`.

Each entry also has `train_mode`: `lora16` (16-bit LoRA, fp16 on T4) or `qlora4` (4-bit QLoRA). Verified 2026-10-07: Unsloth advises **against QLoRA for Qwen3.5**; Qwen3.5 16-bit LoRA needs 0.8B 3 GB · 2B 5 GB · 4B 10 GB · 9B 22 GB.

| Model | Params | License | Mode | Fits T4 | Playground |
|---|---|---|---|---|---|
| **Qwen3.5 4B (default, ADR-0001)** | 4B | Apache 2.0 | lora16 | ✅ 9.7 GB, fp16 stable | yes |
| Qwen3 4B ("faster" option / fallback) | 4B | Apache 2.0 | qlora4 | ✅ 4.2 GB, 1.4× faster | yes |
| Qwen3.5 0.8B / 2B | 0.8–2B | Apache 2.0 | lora16 | yes | yes |
| Qwen3 0.6B / 1.7B | 0.6–1.7B | Apache 2.0 | qlora4 | yes | yes |
| Qwen3 8B ("large") | 8B | Apache 2.0 | qlora4 | ✅ 8.3 GB at seq 1024, bs 1×8 | no — adapter-only export by default; "use Ollama locally" |
| ~~Qwen3.5 9B~~ | 9B | Apache 2.0 | — | **no** (22 GB in 16-bit; QLoRA not recommended) | removed |

Qwen3.5 notes: custom Mamba-style Triton kernels compile slowly on T4 (first steps are slow — show "compiling kernels, this takes a few minutes" in the notebook); Qwen3/3.5 are thinking models — train and serve in **non-thinking** mode (`enable_thinking=False` in the chat template) and use the same template at inference/GGUF export, since a wrong chat template/EOS is the most common cause of a broken exported model. Exact HF repo IDs verified in T3.1 against https://huggingface.co/collections/Qwen/qwen35.

## 2. Custom model check (`training/hf_check.py`, `POST /models/check`)
Uses `huggingface_hub.HfApi.model_info(hf_id, files_metadata=True)` (optional server read-only token for rate limits; never accesses gated weights).
1. Exists & public metadata → else blocking `not_found`.
2. **Gated** (`info.gated`) → warning `gated_requires_token`: "You'll need your own Hugging Face token in the notebook."
3. **Architecture**: `config.json` `architectures[0]` / `model_type` ∈ `UNSLOTH_SUPPORTED` (list maintained in code: llama, mistral, qwen2, qwen3, qwen3_5*, gemma2/3, phi3, …; verify against Unsloth docs in T3.1) → else blocking `unsupported_architecture`.
4. **Size & mode**: `safetensors.total` params (from metadata) or sum of weight file sizes / bytes-per-param. Mode: `qlora4` by default for custom models, `lora16` for architectures where Unsloth advises against 4-bit (qwen3.5). Limits: `qlora4` > 10B blocking `too_large`, 8–10B warning `may_not_fit`; `lora16` > 4.5B blocking.
5. **License**: `cardData.license` / tags `license:*` → `apache-2.0` or `mit` pass; anything else (incl. missing) warning `license_review` → UI requires acknowledgement checkbox (`license_ack`).
6. **Llama family** (license `llama*` or model_type llama with Meta org) → flags `is_llama` → naming + notice obligations.
7. Result cached in Redis 24 h. Custom models: `playground_supported=false` in v1.

## 3. Presets (`training/presets.py`)
All: load per catalog `train_mode` (`qlora4` → `load_in_4bit=True`; `lora16` → `load_in_4bit=False, dtype=float16`), `fp16=True`, `bf16=False`, `optim="adamw_8bit"`, `lr_scheduler_type="cosine"`, `warmup_ratio=0.05`, `weight_decay=0.01`, LoRA targets all linear proj (`q,k,v,o,gate,up,down`), `lora_dropout=0`, `use_gradient_checkpointing="unsloth"`, `packing=False`, train on responses only (mask prompts).

| Preset | epochs | r / alpha | lr | per-device batch × grad-accum | max_seq_len |
|---|---|---|---|---|---|
| Quick | 1 | 16 / 16 | 2e-4 | 2 × 4 | 1024 |
| Balanced (default) | 2 | 16 / 32 | 2e-4 | 2 × 4 | 2048 |
| Thorough | 3 | 32 / 64 | 1e-4 | 2 × 4 | 2048 |

Large models (≥ 8B) force batch 1 × 8 and max_seq_len 1024. Advanced panel (validated ranges): epochs 1–5, r ∈ {8,16,32,64}, lr 1e-5–5e-4, max_seq_len 512–4096. `max_steps` = ceil(train_pairs × epochs / (batch × accum)). `seed` = random int stored on the job.

Time hint shown before start: `time_hint × pairs/1000 × epochs`, plus a note "Free Colab sessions can end early — progress is saved."

## 4. Notebook structure

### 4.1 `notebook/doctune_nb/` (pip package, versioned with the repo tag)
```
doctune_nb/
  __init__.py      __version__
  api.py           DocTuneClient(token, api_url): config(), start(), heartbeat(), checkpoint_*(), artifacts_*(), pause(), finish(), fail()
                   retries with backoff; raises TokenExpired/TokenRevoked/NotebookOutdated with friendly messages
  env.py           detect GPU (torch.cuda), VRAM, platform (Colab/other), bf16 support; NoGPU → api.pause("no_gpu") + message
  data.py          download + sha256-verify dataset; load as HF Dataset; apply chat template
  train.py         build model (FastLanguageModel.from_pretrained 4-bit), LoRA, SFTTrainer config from cfg; run with resume
  callbacks.py     HeartbeatCallback (every N s), TimedCheckpointCallback (forces save every K minutes), UploadCheckpointCallback (on_save → zip → PUT → complete; keeps 1 local)
  evaluate.py      generate answers for ≤100 eval items with tuned model and base model (adapter disabled), quick ROUGE-L, upload generations.jsonl
  export.py        save adapter → zip → upload; merged 16-bit + GGUF (Q4_K_M) via Unsloth save_pretrained_merged / save_pretrained_gguf → Google Drive; optional push to HF (user token); Llama naming + LICENSE/NOTICE
  ui.py            progress bars (tqdm.auto), clear status messages, the pause-message table from the design doc
```

### 4.2 `doctune_train.ipynb` cells
| # | Cell | Content |
|---|---|---|
| 0 | Markdown | What this does · **Runtime → Change runtime type → T4 GPU** · keep this tab open · resuming = run all cells again · nothing is stored from your Google account |
| 1 | Install | `%pip install -q "doctune-nb @ git+https://github.com/<org>/doctune@nb-vX.Y.Z#subdirectory=notebook"` (pins Unsloth/TRL/transformers/peft versions via its dependencies) |
| 2 | Token | `from getpass import getpass; JOB_TOKEN = getpass("Paste your DocTune job token: ")` · `API_URL = "https://api.<domain>"` |
| 3 | Check | `env = doctune_nb.env.check()` → shows GPU; if none: pause(no_gpu) + "Colab has no free GPU for your account right now…" and stop |
| 4 | Config | `client = DocTuneClient(JOB_TOKEN, API_URL); cfg = client.config()` → prints project, model, preset, steps; if checkpoint exists: "Resuming from step N (X%)" |
| 5 | Optional HF token | Markdown + `HF_TOKEN = getpass(...)` only if `cfg.gated` or user wants HF upload (blank = skip) |
| 6 | Optional Drive | `drive.mount('/content/drive')` for exports (user-initiated, standard Colab auth; DocTune never sees credentials) |
| 7 | Train | `doctune_nb.train.run(client, cfg, env)` — downloads data + checkpoint, start(), trains with callbacks, handles `KeyboardInterrupt` → pause(user_stopped) |
| 8 | Evaluate | `doctune_nb.evaluate.run(...)` |
| 9 | Export | `doctune_nb.export.run(...)` → adapter to DocTune, merged+GGUF to Drive (and HF if token) → `client.finish(...)` |
| 10 | Markdown | Done → link back to project; how to run GGUF in Ollama (`Modelfile` snippet printed by cell 9) |

Notebook must stay interactive (Colab rules): no `while True` keep-alives, no JS click hacks, no tunnels/servers, no background threads beyond the trainer itself.

## 5. Training loop details (`train.py`)
1. Load `FastLanguageModel.from_pretrained(cfg.unsloth_id or base_model_id, load_in_4bit=(cfg.train_mode == "qlora4"), max_seq_length=cfg.max_seq_len, dtype=torch.float16, token=HF_TOKEN or None)`. Chat template applied with thinking disabled.
2. `get_peft_model(r, alpha, targets, use_gradient_checkpointing="unsloth", random_state=seed)`.
3. Dataset: chat JSONL → `tokenizer.apply_chat_template`; `train_on_responses_only`.
4. `SFTTrainer` with `SFTConfig(output_dir="/content/doctune/ckpt", save_strategy="steps", save_steps=<computed from time: est steps per 7 min, min 10>, save_total_limit=1, logging_steps=5, report_to="none" (or wandb if user sets WANDB_API_KEY), seed, data_seed, fp16=True, bf16=False)`.
5. `TimedCheckpointCallback` triggers `control.should_save=True` when 7 minutes passed since last save (guards against slow steps).
6. Resume: if `client.checkpoint_latest().exists` → download zip → verify sha256 → unzip to `ckpt/checkpoint-{step}` → `trainer.train(resume_from_checkpoint=path)`; else `trainer.train()`. Dataset sha must match config (refuse otherwise).
7. Heartbeat every 30 s via callback `on_log` / `on_step_end` (time-throttled): step, max_steps, loss, lr. Response `cancel_requested=true` → `control.should_training_stop=True`, final message.
8. OOM handling: catch `torch.cuda.OutOfMemoryError` at step 0 → `client.fail(fatal=True, error="out_of_memory")` with advice (pick smaller model / Quick preset); mid-run OOM → retry once with halved batch & doubled accum.
9. On completion → `client.training_complete(...)`.

## 6. Checkpoint & resume (P4)
- Checkpoint contents: adapter weights, `optimizer.pt`, `scheduler.pt`, `rng_state.pth`, `trainer_state.json`, `training_args.bin`. 4B r=16 ≈ 60–150 MB (optimizer 8-bit). Zipped with `zipfile ZIP_STORED` (already compressed tensors).
- Upload flow: `checkpoint/upload-url` → `PUT` (requests streaming, retries 3) → `checkpoint/complete {step, sha256}`. Upload runs in the callback synchronously (keeps it simple and rule-compliant; ~10–30 s each).
- Server keeps only `j/{job}/checkpoint/latest.zip` (same key overwritten) + `checkpoints` row.
- Pause detection matrix:

| Situation | Who reports | Reason |
|---|---|---|
| User interrupts cell | notebook `pause(user_stopped)` | user_stopped |
| No GPU at start | notebook `pause(no_gpu)` | no_gpu |
| Runtime disconnected / 12 h cap / reclaimed / idle | nobody → monitor after 15 min | heartbeat_timeout (UI shows the "Training stopped at X%" message, mentioning idle/session limits as likely causes) |
| Python exception | notebook `fail(error)` (non-fatal) → paused | stopped |

- Resume = user reruns all cells with the same token (token valid 14 days; can rotate). `start(resumed_from_step)` → project `paused→training`, email "resumed" only if paused > 1 h.
- Deterministic resume: same seed, same dataset sha, same pinned lib versions (`cfg.lib_versions` compared to installed; mismatch → warning).

## 7. Evaluation (P5, notebook side)
- Take `min(100, eval_count)` eval items (seeded).
- Tuned answers: `FastLanguageModel.for_inference(model)`, greedy, `max_new_tokens=256`, batch 8.
- Base answers: same model with adapter disabled (`with model.disable_adapter():`) — no second download.
- Quick metric: ROUGE-L vs reference (pure Python implementation to avoid extra deps).
- Upload `generations.jsonl`; server scores with the LLM judge (D6). Eval time budget ≤ 10 min on T4 for 4B; for large models cap 50 items.

## 8. Export (P5)
Defaults per D17 (free Drive is 15 GB shared; Colab free RAM ≈ 12–13 GB):

| Output | Default? | Where | How |
|---|---|---|---|
| LoRA adapter (safetensors + config + tokenizer) | **always** | DocTune R2 (`adapter.zip`) | `model.save_pretrained`, zip, upload |
| GGUF Q4_K_M (2.8 GB for 4B) | **yes, after `finish`** (separate cell) | Drive `/MyDrive/DocTune/{project}/gguf/` or HF | `model.save_pretrained_gguf(..., quantization_method="q4_k_m")` — **~22 min** on Colab (builds llama.cpp), peak RAM 10.1 GB for 4B; 8B experimental |
| Merged 16-bit weights (9.3 GB for 4B) | opt-in; **HF push only** | user's HF repo | `model.save_pretrained_merged(..., save_method="merged_16bit")` (5.7 min for 4B) |
| README + Modelfile | with exports | base model, license, training summary, Ollama `Modelfile` |
| LICENSE / NOTICE | with exports (+ in adapter.zip) | copy base model license; Llama: "Built with Llama" notice, model name prefixed `Llama-` |

If Drive isn't mounted, GGUF/merged are skipped with a message (adapter still uploaded). Before writing to Drive, check free space via `shutil.disk_usage` on the mount and skip with a clear message if it won't fit. Free RAM checked before merging; skip merge if < 1.5× model size.

## 9. Version management
- `doctune_nb.__version__` = git tag `nb-vX.Y.Z`. API config returns `notebook_min_version`; outdated notebook gets 426 with the new Colab link.
- `NOTEBOOK_URL` = `https://colab.research.google.com/github/<org>/doctune/blob/nb-vX.Y.Z/notebook/doctune_train.ipynb`.
- CI job `notebook-smoke` runs `doctune_nb` against a fake API with a tiny model (e.g. `HuggingFaceTB/SmolLM2-135M` or tiny Qwen) on CPU for ~5 steps, including save → kill → resume (Unsloth requires GPU, so CI uses a `--no-unsloth` path with plain PEFT; GPU path is tested manually on Colab per release — T3.12 checklist).

## 10. Spike first (T3.0)
✅ **Done 2026-10-07 — see `docs/adr/0001-base-model-and-training-mode.md`** (raw results in `notebook/spike/results/`). Pinned versions from the run: Unsloth 2026.10.1, torch 2.11.0, transformers 5.17.0, TRL 1.13.0, PEFT 0.21.1, bitsandbytes 0.50.2. What was tested:
1. **Qwen3.5 4B, 16-bit LoRA, fp16** — does it train stably (no NaN/inf loss, no fp16 overflow), how long is kernel compilation, step time, peak VRAM?
2. **Qwen3 4B, QLoRA** — same measurements (fallback default).
3. **Qwen3 8B, QLoRA** — peak VRAM at max_seq_len 1024, batch 1 × 8.
4. For the chosen default: checkpoint size and upload time to R2, resume correctness (loss continues), GGUF Q4_K_M export time and size, free RAM during merge, adapter → GGUF conversion with current llama.cpp (`qwen35` arch tag), output quality on 10 prompts in Ollama.
Record in `docs/adr/0001-base-model-and-training-mode.md`; this sets D16 and the preset time hints.
