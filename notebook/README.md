# doctune-nb — DocTune training notebook

`doctune_train.ipynb` is the notebook users open in **their own** Google Colab (free T4) to fine-tune the model for a
DocTune project. The notebook itself is a set of thin cells; the logic lives in the `doctune_nb` package in this
folder, installed from a git tag so every notebook version pins its own code and library versions.

Spec: `docs/plan/05-training-notebook.md` (sections 4–9), `docs/adr/0001-base-model-and-training-mode.md`,
design doc section "Training: user-run Colab notebook".

## How it works

| Cell | What it does | DocTune API |
|---|---|---|
| 0 | Intro: Runtime -> T4 GPU, keep the tab open, rerun all cells to resume | — |
| 1 | `%pip install "doctune-nb[train] @ git+...@nb-vX.Y.Z#subdirectory=notebook"` (pinned Unsloth/torch/TRL/PEFT) | — |
| 2 | `getpass` job token + `API_URL`; builds `DocTuneClient` (token is never printed or saved) | — |
| 3 | `env.check(client)`: GPU name/VRAM; no GPU -> `pause(no_gpu)` + message, stops | `POST /pause` |
| 4 | `client.config()`: project, model, preset, steps, "Resuming from step N" | `GET /config?notebook_version=`, `GET /checkpoint/latest` |
| 5 | Optional Hugging Face token (`getpass`, gated models / HF uploads; never sent to DocTune) | — |
| 6 | Optional Google Drive mount (standard Colab auth; DocTune never sees it) | — |
| 7 | `train.run(...)`: dataset download + sha256, checkpoint download + sha256, start, train, checkpoints, heartbeats | `GET /checkpoint/latest`, signed GETs, `POST /start`, `POST /heartbeat`, `POST /checkpoint/upload-url` + signed PUT + `POST /checkpoint/complete`, `POST /pause` (Ctrl-C), `POST /fail`, `POST /training-complete` |
| 8 | `evaluate.run(...)`: base (adapter off) vs fine-tuned answers on <= 100 held-out items, ROUGE-L, upload | `POST /artifacts/upload-url {eval_generations}` + PUT + `POST /artifacts/complete`, `POST /heartbeat` |
| 9 | `export.upload_adapter_and_finish(...)`: adapter + README + LICENSE -> DocTune, project becomes `ready` | `POST /artifacts/upload-url {adapter_safetensors}` + PUT + `POST /artifacts/complete`, `POST /finish` |
| 10 | Optional: GGUF Q4_K_M -> Drive or HF; merged 16-bit -> HF only (opt-in) | `POST /finish` again with `exports` (paths/repo names only) |
| 11 | Done: link back to the project, Ollama instructions | — |

### Training
- Model loaded per `cfg.train_mode`: `lora16` -> `load_in_4bit=False, dtype=float16`; `qlora4` -> `load_in_4bit=True`.
  Always `fp16=True, bf16=False` (T4). LoRA on all linear projections, `use_gradient_checkpointing="unsloth"`,
  `random_state = seed`.
- Chat template rendered with `enable_thinking=False` (Qwen3/3.5 non-thinking) for training, evaluation and the
  exported Ollama `Modelfile`. Loss on responses only (`train_on_responses_only`, markers detected from the template).
- `max_steps` comes from the server, `save_total_limit=1`, seed/data_seed = job seed.
- Checkpoints: `TimedCheckpointCallback` forces a save every `checkpoint_every_minutes` (default 7) plus a final save;
  `UploadCheckpointCallback.on_save` zips the checkpoint (`ZIP_STORED`, adds `doctune_meta.json` with seed / dataset
  sha / lib versions) and uploads it (3 attempts; failures never stop training).
- Heartbeats: `HeartbeatCallback`, at most every 30 s (server-provided), with step / max_steps / loss / lr / epoch.
  `cancel_requested` or a revoked token stops training.
- Resume = run all cells again: the newest checkpoint (server or this session) is downloaded, sha256-verified, its
  dataset sha checked, and `trainer.train(resume_from_checkpoint=...)` continues with the same seed and versions.
- Ctrl-C / Interrupt: writes a checkpoint, uploads it, `pause(user_stopped)`. Other errors: `fail(fatal=false)`
  (server shows "Training stopped at X%"). OOM before the first step: `fail(fatal=true, "out_of_memory: ...")` with
  advice; OOM later: one retry from the last checkpoint with half batch / double grad-accum.

### Colab free-tier rules
Interactive only: the user runs the cells and watches. No keep-alive tricks, no background threads (everything runs
in trainer callbacks), no servers / tunnels / web UIs, one job per notebook. Tokens are entered with `getpass`,
never printed, never written to disk. Google credentials and HF tokens never reach DocTune.

### Portability
Needs only Python + a CUDA GPU + internet. `env.workdir()` uses `/content/doctune` on Colab and `~/doctune`
elsewhere (`DOCTUNE_WORKDIR` overrides); Drive export is skipped outside Colab.

### Headless run (Kaggle backend, ADR-0002)
`doctune_nb.headless.run(token, api_url) -> int` runs cells 2-4 and 7-9 without prompts: env check -> config ->
train -> evaluate -> upload adapter + finish. No HF token, no Drive, no optional exports. Only for runtimes DocTune
starts through an official API in the user's own account (Kaggle); **the Colab notebook stays interactive**.
Local GPU: `DOCTUNE_JOB_TOKEN=dtj_... DOCTUNE_API_URL=https://... python -m doctune_nb.headless`.
- Resume is automatic: every run fetches the latest checkpoint from DocTune. SIGTERM -> checkpoint + `pause(session_ended)`.
- Evaluation errors don't block the adapter: it is uploaded without scores.
- On Kaggle: `CUDA_VISIBLE_DEVICES=0` (if unset), work dir `/kaggle/working/doctune`, job files deleted at the end.
- Exit codes: 0 done, 1 failed (reported via `fail(fatal=false)` if nothing was reported yet), 2 missing env vars
  (`-m` only), 3 token rejected / cancelled / job ended, 4 no GPU (`pause(no_gpu)`), 5 OOM before the first step
  (`fail(fatal=true)`), 6 interrupted (checkpoint saved, `pause(session_ended)`).

## Releasing a notebook version
1. Bump `__version__` in `doctune_nb/__init__.py` and `version` in `pyproject.toml` (same `X.Y.Z`), and the tag in
   cell 1 of `doctune_train.ipynb` (`@nb-vX.Y.Z`).
2. If you change pinned versions in the `train` extra, also update `LIB_VERSIONS` in
   `backend/src/doctune/training/catalog.py` and re-run the T4 release checklist (T3.12) on a real Colab T4.
3. Tag the repo `nb-vX.Y.Z` and push the tag. The notebook URL is
   `https://colab.research.google.com/github/<org>/doctune/blob/nb-vX.Y.Z/notebook/doctune_train.ipynb`.
4. When older notebooks must stop working, raise `NOTEBOOK_MIN_VERSION` in
   `backend/src/doctune/training/colab.py` (old notebooks get HTTP 426 with the new link).

Before tagging, replace the placeholders in `doctune_train.ipynb`: the GitHub org in cell 1 and `API_URL` in cell 2.

## Development
```bash
cd notebook
uv venv --python 3.12
uv pip install -e '.[dev]'
uv run pytest                      # fast tests, no GPU / torch / model downloads
uv run ruff check . && uv run ruff format --check .
```

Optional CPU smoke test (plain PEFT, no Unsloth; downloads a tiny model, ~1–2 min):
```bash
uv pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu
uv pip install -e '.[smoke]'
uv run pytest --run-slow -m slow
```

The GPU path (Unsloth, fp16 on a T4, GGUF export) can only be tested on a real Colab T4 — see the release checklist.
