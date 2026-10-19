# 03 — API Contract

Base URL: `https://api.<domain>` (prod), `http://localhost:8000` (dev). All JSON. Auth: **U** = Supabase user JWT, **J** = job token, **—** = public. Errors use the envelope in `01-architecture.md §9`. All list endpoints: `?cursor=&limit=` (default 50, max 200), response `{items, next_cursor}`.

Every route declares `response_model`; the web client is generated from `/openapi.json`.

## Health & meta
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/healthz` | — | liveness |
| GET | `/readyz` | — | DB + Redis check |
| GET | `/meta` | — | `{notebook_url, notebook_version, limits:{file_mb:20, project_mb:50, max_pairs:2000}, providers:[...]}` |

## Me & settings
| Method | Path | Auth | Body → Response |
|---|---|---|---|
| GET | `/me` | U | → `MeOut {id, email, display_name, onboarding_done, email_notifications}` |
| PATCH | `/me` | U | `{display_name?, onboarding_done?, email_notifications?}` → `MeOut` |
| DELETE | `/me` | U | → 202; deletes all projects, keys, R2 objects (async), then the user row (Supabase auth user deleted via admin API) |

## Provider keys (BYO LLM keys)
| Method | Path | Auth | Body → Response |
|---|---|---|---|
| GET | `/keys` | U | → `[ProviderKeyOut {provider, last4, status, priority, default_model, last_verified_at, quota_reset_at}]` (never the key) |
| PUT | `/keys/{provider}` | U | `{api_key, default_model?, terms_acknowledged?}` → `ProviderKeyOut`; encrypts, then enqueues `verify_key` (status `unverified` → `valid/invalid`) |
| PATCH | `/keys/{provider}` | U | `{priority?, default_model?}` → `ProviderKeyOut` |
| DELETE | `/keys/{provider}` | U | → 204 |
| POST | `/keys/{provider}/verify` | U | → 202 (re-verify) |
| GET | `/compute/kaggle` | U | → `KaggleAccountOut {username, token_hint, status: unchecked\|ok\|invalid\|no_gpu_quota, status_message, gpu_hours_used, gpu_hours_total, quota_refresh_at, checked_at}` or `null` (never the token) |
| PUT | `/compute/kaggle` | U | `{username, api_token}` → `KaggleAccountOut`; encrypts, status `unchecked`, enqueues `check_kaggle_account` (→ `ok/invalid/no_gpu_quota`) |
| POST | `/compute/kaggle/check` | U | → 202 `KaggleAccountOut`; re-check token + GPU quota; 404 if none |
| DELETE | `/compute/kaggle` | U | → 204 |
| GET | `/keys/{provider}/models` | U | → `[{id, context_window, license?, recommended}]` via provider `/models` (cached 1 h) |

Gemini PUT requires `terms_acknowledged: true` (409 `terms_required` otherwise).

## Projects
| Method | Path | Auth | Body → Response |
|---|---|---|---|
| GET | `/projects` | U | → page of `ProjectSummary {id, name, status, updated_at, doc_count, pair_count, base_model_id}` |
| POST | `/projects` | U | `{name}` → 201 `ProjectOut` (status `draft`). Limit 20 active projects/user |
| GET | `/projects/{id}` | U | → `ProjectOut` (see below) |
| PATCH | `/projects/{id}` | U | `{name?, target_pairs?, gen_provider?, gen_model?}` → `ProjectOut` |
| DELETE | `/projects/{id}` | U | → 202; marks `deleted_at`, revokes tokens, enqueues `purge_project` |
| POST | `/projects/{id}/retry` | U | → `ProjectOut`; only when `failed`, moves to `status_retry_to` |
| GET | `/projects/{id}/events` | U | SSE stream (see architecture §6) |
| GET | `/projects/{id}/activity` | U | → page of `project_events` |

`ProjectOut`: `{id, name, status, status_reason, status_message, status_changed_at, base_model_id, base_model_license, gen_provider, gen_model, target_pairs, total_bytes, counts:{documents, chunks, pairs_kept, pairs_train, pairs_eval}, style: StyleOut|null, latest_preview: GenerationRunOut|null, active_run: GenerationRunOut|null, dataset_version: DatasetVersionOut|null, active_job: TrainingJobOut|null, evaluation: EvaluationOut|null, allowed_actions: [string]}`.
`allowed_actions` is computed server-side (e.g. `["upload","process","delete"]`) so the UI never re-implements the state machine.

## Documents
| Method | Path | Auth | Body → Response |
|---|---|---|---|
| POST | `/projects/{id}/documents` | U | `{filename, size_bytes, content_type}` → 201 `{document: DocumentOut, upload: {url, method:"PUT", headers, expires_at}}`. Validates extension (pdf in P1; +docx/txt/md in P2), size ≤ 20 MB, project total ≤ 50 MB, status in {draft, uploaded} |
| POST | `/projects/{id}/documents/{doc_id}/complete` | U | → `DocumentOut`; HEAD object: size matches, magic-bytes sniff (download first 8 KB); sets `uploaded`; project `draft→uploaded` |
| GET | `/projects/{id}/documents` | U | → `[DocumentOut {id, filename, size_bytes, status, page_count, ocr_pages, error, chunk_count}]` |
| DELETE | `/projects/{id}/documents/{doc_id}` | U | → 204; only before generation (status ≤ awaiting_style); deletes chunks + R2 object |
| POST | `/projects/{id}/process` | U | → 202 `ProjectOut`; `uploaded→parsing`, enqueues `parse_document` per unparsed doc |
| GET | `/projects/{id}/chunks` | U | `?document_id=&q=` → page of `ChunkOut {id, document_id, ordinal, section_path, text, token_count, page_start, page_end}` |

## Style & templates
| Method | Path | Auth | Body → Response |
|---|---|---|---|
| GET | `/style-templates` | U | → `[StyleTemplateOut {key, name, description, defaults}]` |
| GET | `/dataset-formats` | U | → `[FormatInfo {key, name, description, best_for, relative_cost, input_label, output_label, sample}]` (ADR-0003) |
| PUT | `/projects/{id}/style` | U | `StyleIn {template_key?, description, tone, length, format, language, examples:[{input, output}], system_prompt_in_data, dataset_format}` → `StyleOut {…, id, warnings:[{code, message}]}`. Creates a new immutable `style_configs` row. Allowed in `awaiting_style`. Warnings: `single_example`, `examples_inconsistent` (format/length mismatch heuristics; LLM check optional), `description_short` |
| GET | `/projects/{id}/style` | U | → `StyleOut` |

## Generation
| Method | Path | Auth | Body → Response |
|---|---|---|---|
| POST | `/projects/{id}/preview` | U | `{n_chunks?: 3..5, pairs_per_chunk?: 2}` → 202 `GenerationRunOut`; `awaiting_style→previewing`. Requires style + ≥1 valid key |
| GET | `/projects/{id}/runs/{run_id}` | U | → `GenerationRunOut {id, kind, state, done_chunks, total_chunks, pairs_generated, pairs_kept, provider_chain, resume_at, error}` |
| GET | `/projects/{id}/runs/{run_id}/pairs` | U | → page of `PairOut` (preview pairs with their source chunk excerpt) |
| GET | `/projects/{id}/estimate` | U | → `{chunks, pairs_per_chunk, est_requests, est_tokens, est_minutes_by_provider:{groq:…}, fits_daily_quota: bool}` |
| POST | `/projects/{id}/generate` | U | `{confirm: true}` → 202 `GenerationRunOut`; `awaiting_style→generating`. 409 `preview_required` if no finished preview for the current style hash |
| POST | `/projects/{id}/runs/{run_id}/cancel` | U | → `GenerationRunOut`; `generating→awaiting_style` |
| POST | `/projects/{id}/runs/{run_id}/finish` | U | → `ProjectOut`. Finish early: stops a running or quota-waiting full run, skips the remaining units and finalizes with the pairs judged so far (`generating→in_review` via the finalize worker). 409 `too_few_pairs` below 20 kept pairs |

## Dataset review
| Method | Path | Auth | Body → Response |
|---|---|---|---|
| GET | `/projects/{id}/pairs` | U | `?split=train|eval|all&kept=true|false&q=&sort=` → page of `PairOut {id, dataset_format, question, answer, record, split, origin, judge_correctness, judge_style, judge_reason, kept, dropped_reason, edited, chunk:{id, section_path, excerpt}}` |
| PATCH | `/projects/{id}/pairs/{pair_id}` | U | `{question?, answer?, record?, kept?, split?}` → `PairOut` (sets `edited`). `record` replaces the whole example; another format → 409 `format_mismatch` |
| POST | `/projects/{id}/pairs` | U | `{record}` or `{question, answer}`, `split?` → 201 `PairOut` (origin `user_added`); a question + answer is shaped into the project's format |
| POST | `/projects/{id}/pairs/bulk` | U | `{ids:[…], action: "drop"|"restore"|"move_to_train"|"move_to_eval"}` → `{updated}` |
| GET | `/projects/{id}/dataset/stats` | U | → `{kept, train, eval, dropped_by_reason:{…}, avg_scores, length_hist}` |
| POST | `/projects/{id}/dataset/export` | U | `{shape?: "training"\|"native"}` → `{url, expires_at}` JSONL of current kept pairs: chat messages (as trained), or the format's own layout (Alpaca for instructions, ShareGPT for conversations) |
| POST | `/projects/{id}/dataset/approve` | U | → `DatasetVersionOut`; freezes version (writes train/eval JSONL to R2). Validates 50 ≤ kept ≤ 2,000, eval ≥ 5 |
| POST | `/projects/{id}/dataset/restyle` | U | `{confirm:true}` → `ProjectOut`; `in_review→awaiting_style` |

Allowed only in `in_review` (except GET/export).

## Models
| Method | Path | Auth | Body → Response |
|---|---|---|---|
| GET | `/models/catalog` | U | → `[BaseModelOut {id, display_name, params_b, license, fits_t4: "yes"|"unconfirmed", time_hint, recommended, playground_supported}]` |
| POST | `/models/check` | U | `{hf_id}` → `ModelCheckOut {hf_id, ok, architecture, params_b, license, license_ok, gated, unsloth_supported, fits_t4, warnings:[], blocking:[]}` |
| GET | `/training/presets` | U | → `[PresetOut {key, name, description, est_minutes_by_size, hyperparams}]` |

## Training (user side)
| Method | Path | Auth | Body → Response |
|---|---|---|---|
| POST | `/projects/{id}/training` | U | `{base_model_id, preset, advanced?: {...}, license_ack?: bool, backend?: "colab"(default)\|"kaggle"}` → 201 `{job: TrainingJobOut, token?: "dtj_…", notebook_url?}`. Requires approved dataset; `in_review→awaiting_run`; Colab: token returned **once**; Kaggle (ADR-0002): `token`/`notebook_url` are null and a worker launches the kernel; 409 `kaggle_not_connected` (no account with status `ok`), 409 `kaggle_gated_model` |
| GET | `/projects/{id}/training/{job_id}` | U | → `TrainingJobOut {id, state, backend, external_url, launch_attempts, base_model_id, preset, current_step, max_steps, last_loss, last_heartbeat_at, pause_reason, token_prefix, token_expires_at, started_at, completed_at, checkpoint:{step, uploaded_at}|null}` |
| GET | `/projects/{id}/training/{job_id}/metrics` | U | → `[{step, loss, lr, at}]` |
| POST | `/projects/{id}/training/{job_id}/switch` | U | `{backend: "kaggle"}` → `TrainingCreated` (token null). Moves a Colab job still in `created` (no notebook connected) to Kaggle with the same model/preset/hyperparams; cancels the old job and revokes its token; project stays `awaiting_run`. 409 `kaggle_not_connected`, `kaggle_gated_model`, `invalid_state` |
| POST | `/projects/{id}/training/{job_id}/token` | U | → `{token, expires_at}`; rotate (revoke old); Colab only (409 `token_managed` for Kaggle jobs) |
| POST | `/projects/{id}/training/{job_id}/cancel` | U | → `ProjectOut`; revoke token, job `cancelled`, project → `in_review` |
| GET | `/projects/{id}/training/{job_id}/checkpoint/download` | U | → `{url, expires_at}` |
| GET | `/projects/{id}/artifacts` | U | → `[ArtifactOut {id, kind, size_bytes, expires_at}]` |
| GET | `/projects/{id}/artifacts/{artifact_id}/download` | U | → `{url, expires_at}` |
| GET | `/projects/{id}/evaluation` | U | → `EvaluationOut` |

## Notebook endpoints (job token)
All under `/jobs/current`. Rate-limited per token. Responses designed for a simple `requests` client.

| Method | Path | Body → Response |
|---|---|---|
| GET | `/jobs/current/config` | → `JobConfig {job_id, project_name, base_model_id, base_model_license, is_llama, hyperparams, seed, max_seq_len, lib_versions, dataset:{train_url, eval_url, sha256_train, sha256_eval, system_prompt}, checkpoint_every_minutes, heartbeat_every_seconds, eval_max_items, notebook_min_version}`. 426 `notebook_outdated` if the notebook is older than `notebook_min_version` |
| POST | `/jobs/current/start` | `{runtime:{gpu_name, vram_gb, platform, python, torch, cuda}, resumed_from_step?: int}` → `{ok}`; job `running`; project `awaiting_run|paused → training`; 409 if job cancelled/completed |
| POST | `/jobs/current/heartbeat` | `{step, max_steps, loss?, lr?, epoch?}` → `{ok, cancel_requested: bool}`; updates job, samples metrics, publishes SSE. Moves `paused→training` if needed |
| GET | `/jobs/current/checkpoint/latest` | → `{exists, step?, url?, sha256?}` |
| POST | `/jobs/current/checkpoint/upload-url` | `{step, size_bytes}` → `{url, headers, expires_at}` (size ≤ 1.5 GB) |
| POST | `/jobs/current/checkpoint/complete` | `{step, sha256, size_bytes}` → `{ok}`; HEAD check; replaces `checkpoints` row (old object overwritten — same key) |
| POST | `/jobs/current/pause` | `{reason: session_ended|idle_timeout|no_gpu|stopped|user_stopped, step}` → `{ok}`; best-effort from notebook (e.g. KeyboardInterrupt / no GPU detected) |
| POST | `/jobs/current/training-complete` | `{final_step, final_loss, train_runtime_s}` → `{ok}`; project `training→evaluating` |
| POST | `/jobs/current/artifacts/upload-url` | `{kind: adapter_safetensors|eval_generations, size_bytes}` → `{url, headers}` |
| POST | `/jobs/current/artifacts/complete` | `{kind, sha256, size_bytes}` → `{ok}`; adapter → enqueue `convert_adapter_to_gguf`; eval_generations → enqueue `score_evaluation` |
| POST | `/jobs/current/finish` | `{metrics:{eval_loss?, rouge_l_base?, rouge_l_tuned?}, exports:{drive_path?, hf_repo?}}` → `{ok, project_url}`; requires adapter uploaded; project `evaluating→ready`; job `completed`; email |
| POST | `/jobs/current/fail` | `{error, step?}` → `{ok}`; job stays resumable unless `fatal: true` (e.g. OOM on step 0 → suggest smaller model) |

## Playground
| Method | Path | Auth | Body → Response |
|---|---|---|---|
| GET | `/projects/{id}/playground/status` | U | → `{available, reason?, model_loaded, source: "final"|"checkpoint", warm: bool}` |
| POST | `/projects/{id}/playground/warmup` | U | → 202; enqueue `ensure_loaded` (load base GGUF + adapter into llama-server) |
| POST | `/projects/{id}/playground/chat` | U | `{messages:[{role, content}], use_rag: true, compare_base?: false, temperature?, max_tokens? ≤ 512}` → SSE stream: `token` events `{text}`, `sources` event `[{chunk_id, section_path, excerpt}]`, `done` `{usage}`. Rate limit 20 req/min/user, 1 concurrent |

## Admin (role check via `users.is_admin` or allowlist env)
`GET /admin/usage` → DB size, R2 bytes by prefix, active jobs, queue depths, emails today.

## Status codes summary
200 OK · 201 created · 202 accepted (async) · 204 no content · 400 malformed · 401 unauth/token expired/revoked · 403 forbidden · 404 not found / not owned · 409 invalid transition / conflict / preview_required / terms_required · 413 too large · 415 unsupported file type · 422 validation · 426 notebook outdated · 429 rate limited · 502 upstream provider error.
