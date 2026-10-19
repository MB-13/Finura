# 07 — Playground (llama.cpp + RAG)

## 1. Model serving design (D7)
- Base models: for each catalog model with `playground_supported`, a Q4_K_M GGUF is downloaded once to `LLAMA_MODELS_DIR` (`infra/llama/download-models.sh`, manifest in `infra/llama/models.json`). Start with the D16 default 4B model plus one small model (Qwen3.5 2B or Qwen3 1.7B); each Q4_K_M base ≈ 1–2.7 GB on disk.
- Size cap: `PLAYGROUND_MAX_PARAMS_B` (default 4.5) decides which catalog models the playground loads. 4B fits the 12 GB free VM next to the API and workers (D19); a machine with more free RAM can set 8 to chat with Qwen3 8B (Q4_K_M ≈ 5 GB, needs ~6 GB free). Above the cap, status returns `reason_code: too_large` and the UI points to Ollama.
- Adapters: `adapter.gguf` (f16 LoRA GGUF, converted by `convert_adapter_to_gguf`, 10–100 MB) stored in R2, cached on local disk (LRU, 5 GB cap).
- **Inference manager** (`backend/src/doctune/inference/manager.py`, runs in the `inference` worker + a small state record in Redis):
  - Oracle free VM is **2 OCPU / 12 GB** (D19), so v1 keeps **one warm `llama-server` process** (one base model + one adapter) with a FIFO queue of users waiting for their model; idle shutdown after 10 min; swapping models costs ~10–30 s of loading.
  - Process: `llama-server -m base.gguf --lora adapter.gguf -c 4096 -t 2 --port <p> --host 127.0.0.1 --parallel 1 --no-webui`. Expected speed for a 4B Q4_K_M on 2 Ampere cores: roughly 3–6 tokens/s (measure in T5.6).
  - Adapter GGUFs must be converted with a current `convert_lora_to_gguf.py` so Qwen3.5 adapters are tagged `qwen35` (older versions tag `qwen3` and fail to load).
  - Registry in Redis: `{key: (job_id, source), port, pid, last_used}`; warmup task starts the process and waits for `/health`.
  - If the llama.cpp version on the VM supports per-request LoRA selection, switch to one process per base model with per-request adapters (task T5.9 investigates; ADR).
- API `/playground/chat`: ensures loaded (or 409 `warming_up` + enqueues warmup; UI polls `status`), then proxies a streaming `/v1/chat/completions` request to the local llama-server and re-emits tokens as SSE.
- "Compare with base": same process with LoRA scale 0 via `lora` request field if supported, else a base-only process (shared across users).

## 2. RAG
- On each user message: embed query (`query: ` prefix, same e5 model, in-process in the API — model loaded lazily, ~120 MB) → `SELECT … FROM chunks WHERE project_id=:p ORDER BY embedding <=> :q LIMIT 4` → drop chunks with cosine distance > 0.6.
- Prompt: system = (dataset system prompt if used in training) + "Use the context below when relevant. If the context doesn't contain the answer, say so." + numbered context blocks (≤ 1,500 tokens total). Conversation history trimmed to fit `-c 4096`.
- Return `sources` event with chunk ids, section paths and excerpts so the UI can show citations.
- RAG toggle off → no context (shows pure fine-tuned behavior).

## 3. Limits & fairness
- Per user: 1 concurrent stream, 20 messages/min, `max_tokens ≤ 512`, 3 min generation timeout.
- Global: one active chat at a time; others queue (position shown: "You're #2 in line"), queue max 10 → 429 `playground_busy`. Warm-ups are deferred while a parse job is running.
- Playground supports models **≤ 4B**; larger ones (catalog flag) → UI shows Ollama instructions. The UI always offers "Run it locally with Ollama" as the faster option.
- If demand outgrows one slot, the upgrade path is a paid inference backend (P7), not more free VMs.

## 4. Checkpoint testing while paused
`POST /playground/warmup?source=checkpoint` → `convert_adapter_to_gguf(job, source=checkpoint)` extracts adapter weights from `latest.zip` (adapter files only) → converts → loads. UI labels "Checkpoint · step 340".

## 5. Tasks
See `11-tasks.md` P5: T5.1–T5.9.
