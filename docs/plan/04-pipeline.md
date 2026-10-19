# 04 — Worker Pipeline (Celery)

## 1. Celery setup
- `workers/celery_app.py`: broker/backend Redis; `task_acks_late=True`, `task_reject_on_worker_lost=True`, `worker_prefetch_multiplier=1`, JSON serializer, `task_time_limit` per task, UTC.
- Queues and worker processes (docker services):

| Queue | Service | Concurrency | Tasks |
|---|---|---|---|
| `parse` | `worker-parse` | 1 prefork, mem limit 2 GB | parse_document, ocr |
| `llm` | `worker-llm` | 8 threads (`-P threads`), I/O bound | generate_preview, generate_chunk, judge_batch, score_evaluation, verify_key, check_examples |
| `embed`, `default` | `worker-cpu` | 2 prefork (e5 model loaded once per process) | embed_chunks, embed_pairs, finalize_run, approve_dataset, convert_adapter_to_gguf, purge_project, send_email, monitor, cleanup |
| `inference` | `worker-inference` | 1 | ensure_loaded / unload (talks to inference manager) |

- Beat schedule (`workers/beat.py`):

| Task | Every | Purpose |
|---|---|---|
| `monitor_heartbeats` | 1 min | jobs `running` with `last_heartbeat_at < now-15m` → pause |
| `resume_waiting_runs` | 5 min | runs `waiting_quota` with `resume_at <= now` → re-dispatch pending chunks |
| `expire_tokens` | 1 h | mark tokens past `expires_at` (no-op, validation is lazy; for UI) |
| `cleanup_retention` | daily 03:00 | R2 `j/` objects 14 days after `ended_at`; preview pairs > 7 days; exports > 1 day |
| `reset_key_quota_flags` | 15 min | `quota_exhausted` keys past `quota_reset_at` → `valid` |
| `usage_snapshot` | 6 h | log DB size / R2 bytes; alert (Sentry message) at 80% of free tier |

- Common task helpers: `with task_db() as db` (sync session), `publish(project_id, …)`, `transition_sync(...)`, `@idempotent(key=...)` using Redis `SET NX` locks for single-flight tasks.

## 2. Parsing (`queue=parse`)

### `parse_document(document_id)`
1. Load doc; skip if `parsed`. Set doc `parsing`; publish progress.
2. Download from R2 to a temp dir (streaming, abort if > 20 MB).
3. Sniff type with magic bytes (`filetype`/`python-magic`); must match extension. Reject encrypted PDFs (`needs_pass`) with a clear error.
4. Extract by type (`parsing/`):
   - **PDF** (`pdf.py`): `pymupdf4llm.to_markdown(page_chunks=True)` → per-page markdown with headings. For each page with < 50 chars of text and an image → **OCR** (`ocr.py`: render 200 DPI via PyMuPDF → `pytesseract`, language from style if known else `eng`); count `ocr_pages`. Cap pages at 500.
   - **DOCX** (P2): `mammoth` → HTML → markdown (`markdownify`), headings preserved.
   - **TXT/MD** (P2): decode (charset-normalizer), normalize newlines.
5. Clean: drop repeated headers/footers (lines appearing on > 50% of pages), collapse whitespace, remove null bytes.
6. **Chunk** (`chunker.py`):
   - Split by markdown headings into sections; keep `section_path` breadcrumb.
   - Token counting with a fixed tokenizer (`tiktoken cl100k_base` as a stable approximation).
   - Target 300–900 tokens, hard max 1,000; merge small adjacent sections under the same parent; split large sections on paragraphs then sentences; 0 overlap (generation) — RAG uses the same chunks.
   - Drop chunks < 40 tokens unless the doc has nothing else.
7. Bulk insert chunks (delete existing for the doc first → idempotent). Doc `parsed`, `page_count`.
8. Enqueue `embed_chunks(document_id)` on `embed`.
9. `on_doc_done`: if all docs of the project are `parsed|failed`: if ≥1 chunk → `parsing→awaiting_style`; else `→failed (reason=no_text)`.
- Limits: `soft_time_limit=300s`, `time_limit=360s`; run under a low-privilege user; temp dir cleaned in `finally`.
- Errors: per-document `failed` with message ("This PDF is password-protected", "No readable text found"); project fails only if every doc fails.

### `embed_chunks(document_id)` (`queue=embed`)
- Model `intfloat/multilingual-e5-small` loaded once per process (sentence-transformers, CPU). Input prefix `passage: `. Batch 32. Update `chunks.embedding`. Idempotent (skip non-null).

## 3. LLM layer (`llm/`)

### Providers (`providers.py`)
Limits are **per model** (Groq) and per project (Gemini), so the unit of rotation is a *(provider, model)* pair. Verified 2026-10-07 (`docs/runbooks/free-tiers.md`):
```py
PROVIDERS = {
  "groq": ProviderSpec(base_url="https://api.groq.com/openai/v1", models=[
      ModelSpec("openai/gpt-oss-120b", rpm=30, rpd=1000, tpm=8_000, tpd=200_000, license="apache-2.0"),
      ModelSpec("qwen/qwen3.8-27b",    rpm=30, rpd=1000, tpm=8_000, tpd=200_000, license="apache-2.0"),
      ModelSpec("openai/gpt-oss-20b",  rpm=30, rpd=1000, tpm=8_000, tpd=200_000, license="apache-2.0"),
  ]),
  "gemini": ProviderSpec(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", models=[
      ModelSpec("<current free Flash model>", rpm=10, rpd=250, tpm=250_000, tpd=None),   # per-project, read real values from 429s
  ], requires_terms_ack=True),
  "cerebras": ProviderSpec(base_url="https://api.cerebras.ai/v1", models=[...],
      note="Needs a payment method; $5 credits expire after 30 days — optional, never recommended as free"),
}
```
- Default chain for a user with only a Groq key: `gpt-oss-120b → qwen3.8-27b → gpt-oss-20b` (≈600K tokens/day). The generation and judge prompts must work on all three (tested in T2.3).
- The **8K tokens/minute** limit is the real throttle on Groq: the Redis limiter tracks **tokens per minute** (estimated input + max output) as well as requests.
- Model IDs and limits live only in this file and are re-verified before launch (L3).

### Client (`client.py`)
- `openai` Python SDK with `base_url` per provider, `timeout=60s`, `max_retries=0` (we handle retries).
- `complete_json(user_id, messages, schema, *, purpose)`:
  1. Build chain = (provider, model) pairs from the user's `valid` keys, ordered by key `priority` then the provider's model order.
  2. For each pair: per-user-per-model **request and token buckets** in Redis (rpm/tpm/rpd/tpd from spec; honors `retry-after` and `x-ratelimit-*` headers, which also correct the spec values at runtime). Call with `response_format={"type":"json_object"}` where supported.
  3. On 429: wait `retry-after` (≤ 30 s) up to 2 times, then mark provider cooling (`Redis key with TTL`), publish `notice`, move to next provider.
  4. On daily-quota errors: set key `quota_exhausted`, `quota_reset_at` (from headers or +1 h), next provider.
  5. On 401/403: key `invalid`, email-free notice in UI, next provider.
  6. All exhausted → raise `ProvidersExhausted(retry_after=min reset)`.
  7. Parse JSON → validate with Pydantic schema; on failure one repair retry ("Return only valid JSON matching…"); then raise `BadModelOutput`.
- Records `tokens_in/out` on the run. Never logs prompts with document text at INFO; never logs keys.

### Prompts (`llm/prompts/*.jinja`, versioned)
- `gen-v1.jinja` — the design-doc generation template verbatim, plus: language instruction, "Return JSON: {\"pairs\": [{\"question\", \"answer\"}]}" (object wrapper required for JSON mode), and when `format=json` the answer field holds a JSON string.
- `judge-v1.jinja` — given source chunk, style spec (description, tone/length/format, examples) and a batch of ≤ 10 pairs, return per pair `{id, correctness 1–5, style 1–5, reason ≤ 20 words}`. Rubric: correctness = fully supported by the source; style = matches description and examples.
- Per dataset format (ADR-0003): `gen-instruction-v1` (Alpaca: `{"items": [{instruction, input, output}]}`, input is a short source passage or "") and `gen-multiturn-v1` (`{"conversations": [{"messages": [...]}]}`, 2–4 user turns). The judge prompt is shared; its correctness/style rubric is chosen per format (conversations score the weakest assistant turn). Q&A prompts are unchanged. All of this lives in `llm/prompts.py` and `services/formats.py`.
- `examples-check-v1.jinja` — optional: are the examples consistent with each other and the description? → `{consistent: bool, issues: []}`.
- `eval-judge-v1.jinja` — for evaluation (base vs tuned answers vs reference).

## 4. Generation

### Pairs per chunk
`n = clamp(ceil(target_pairs × 1.3 / num_chunks), 1, max)` where `max` is 8 for Q&A, 6 for instructions and 3 for conversations (longer outputs per call). If `num_chunks × 8 < target × 1.3`, accept fewer pairs and tell the user ("Your documents support about N pairs"). If there are many more chunks than needed, sample chunks (stratified by document/section) instead of generating 1 pair from every chunk — fewer requests, same coverage.

### `generate_preview(run_id)` (`queue=llm`)
1. Pick `n_chunks` (default 4) random chunks, stratified across documents, skipping chunks < 100 tokens.
2. For each: render `gen-v1` with `n=2`, `complete_json`. Insert pairs (`run_id`, `kept=true`, `split=unassigned`).
3. Optionally judge preview pairs (same judge) so users see scores early.
4. Run `done`; `previewing→awaiting_style`; publish.
- On `ProvidersExhausted`: run `failed` with message, project back to `awaiting_style` (preview is cheap — no auto-resume).

### `start_full_run(run_id)` → fan-out
1. Run `running`; `total_chunks` = all chunks.
2. Dispatch `generate_chunk(run_id, chunk_id)` for chunks without a `generation_chunk_results` row. Use a Redis semaphore of 4 in-flight per user to respect rpm.
3. Completion detection: each `generate_chunk` increments `done_chunks` atomically; the one reaching `total_chunks` enqueues `finalize_run` (no chord — survives worker restarts).

### `generate_chunk(run_id, chunk_id)`
- Idempotent via `generation_chunk_results` PK.
- Render prompt → `complete_json` → validate pairs (non-empty, question ≤ 500 chars, answer ≤ 4,000 chars, no copying of example text (fuzzy ratio > 0.8 → drop)).
- Insert pairs (`kept=null` until judged). Write result row. Publish progress every 5 chunks.
- `ProvidersExhausted` → run `waiting_quota`, `resume_at`; publish `notice` ("All your providers hit their free limits. Generation resumes automatically at 14:05."); task ends without error (beat resumes).
- `BadModelOutput` after retry → result `failed`, continue (counted in stats).

### `finalize_run(run_id)` (`queue=default`, single-flight lock)
1. **Judge**: dispatch `judge_batch` over unjudged pairs in batches of 10 grouped by chunk; wait via the same counter pattern → continues in `finalize_after_judge`.
2. Keep rule: `correctness ≥ 4 AND style ≥ 4`; else `kept=false, dropped_reason=judge_low`.
3. **Dedupe**: embed kept questions+answers (`embed_pairs`, prefix `query: `) → for each pair, cosine > 0.92 with an earlier kept pair → drop `duplicate`. Also exact normalized-question duplicates.
4. **Trim** to `target_pairs` (≤ 2,000): prefer higher judge scores, keep chunk coverage balanced (round-robin by chunk).
5. **Split** 90/10 stratified by document (seeded by project id); eval min 5.
6. Null pair embeddings to save space. Run `done`; `generating→in_review`; email "Your dataset is ready for review" if the user isn't connected (best effort: send if run took > 10 min).

### `judge_batch(run_id, pair_ids)`
`complete_json` with `judge-v1` in batches of **20 pairs from the same chunk** (the chunk text is sent once, examples are summarized to save tokens); store scores. Missing ids in output → retry once, else mark `judge_correctness=null` and drop as `judge_failed`.

### Dataset formats
Malformed items in a model response are skipped one by one (bad turn order, empty fields); conversations longer than 1,000 tokens are dropped so they fit the smallest training window. Exact-duplicate keys: the question for Q&A and conversations, instruction + input for instructions. Embedding dedupe uses every turn.

### `approve_dataset(project_id)` (sync in request, small) 
Query kept pairs → build chat JSONL (`{"messages":[system?, user, assistant, …]}`; an instruction's input follows the instruction in the user message after a blank line; a conversation keeps every turn) for train/eval → upload to R2 → sha256 → `dataset_versions` row. ≤ 2,000 rows so it is fast enough in-request (< 2 s); move to a task if it isn't.

## 5. Training-side workers

### `monitor_heartbeats` (beat, 1 min)
For each job `running` with `last_heartbeat_at < now − 15 min`: job `paused (heartbeat_timeout)`, project `training→paused`, publish, `send_email(kind=paused, dedupe_key=job:{id}:pause:{step})`.

### `convert_adapter_to_gguf(job_id)` (`default`)
1. Download `adapter.zip` from R2, unzip, validate `adapter_config.json` base model matches the job.
2. Run llama.cpp `convert_lora_to_gguf.py --base <cached base HF config dir> --outtype f16` (needs only base config/tokenizer, fetched once per base model and cached).
3. Upload `adapter.gguf` → artifact `adapter_gguf`. Same task also handles checkpoints for paused-state playground testing (`source=checkpoint`).

### `score_evaluation(job_id)` (`llm`)
Download `eval/generations.jsonl` (`{question, reference, base_answer, tuned_answer}` ≤ 100) → `eval-judge-v1` in batches → means for base and tuned → pick 10 samples with largest tuned−base improvement plus 2 worst → `evaluations.done`, publish. If the user has no valid key → `failed` with "Connect an API key to score evaluation" and keep notebook metrics.

## 6. Housekeeping
- `purge_project(project_id)`: revoke tokens → delete R2 prefixes `u/{uid}/p/{pid}/` and `j/{job_id}/` for all jobs → delete project row (cascade) → publish. Idempotent.
- `send_email(kind, user_id, project_id, data, dedupe_key)`: respect `email_notifications`; insert `email_log` (unique dedupe) before sending via Resend; templates: `paused`, `resumed` (only if paused > 1 h), `training_finished`, `dataset_ready`, `generation_waiting_quota` (once per run), `job_failed`, `token_expiring` (2 days before, if job not finished).
- `verify_key(user_id, provider)`: call provider `/models` → `valid/invalid`; publish to user channel.

## 7. Estimates shown to users
`/projects/{id}/estimate`: chunks × (prompt tokens ≈ chunk tokens + style tokens + 300) + output (n × 250) + judge (≈ 35% of generation) → tokens; requests = chunks + ceil(pairs/20). Duration = max(tokens / Σ tpm, tokens / Σ tpd days) over the user's chain. Show **days** when it exceeds one day's quota (e.g. "≈ 1.6 days with your Groq key; ≈ 3 hours if you also connect Gemini").

Reference numbers (Groq only, 3 models ≈ 600K tokens/day): 500 pairs ≈ 550K tokens ≈ 1 day · 1,000 pairs ≈ 1.1M ≈ 2 days · 2,000 pairs ≈ 2.2M ≈ 4 days.

## 8. Testing hooks
- Fake provider server (respx) with modes: ok, 429-with-retry-after, daily-quota, invalid-key, broken-json.
- Fixture docs: text PDF with headings, scanned PDF (2 pages), password PDF, DOCX with headings, UTF-16 TXT, empty PDF.
- Determinism: random seeds from project id.
