# 02 — Data Model

Postgres (Supabase) + pgvector. SQLAlchemy 2.0 models in `backend/src/doctune/models/`, Alembic migrations in `backend/alembic/`.

Conventions: `id uuid PK default gen_random_uuid()`; `created_at timestamptz not null default now()`; `updated_at timestamptz not null default now()` (trigger or ORM `onupdate`); all FKs indexed; user-owned rows reach `user_id`; `ON DELETE CASCADE` from `projects` down so deleting a project fully deletes its data. RLS enabled on every table with no policies (deny-all for anon/authenticated roles); the API connects as a privileged role.

## Enums
```
project_status: draft, uploaded, parsing, awaiting_style, previewing, generating, in_review,
                awaiting_run, training, paused, evaluating, ready, failed
document_status: pending_upload, uploaded, parsing, parsed, failed
provider: groq, gemini, cerebras
key_status: unverified, valid, invalid, quota_exhausted
gen_kind: preview, full
gen_state: queued, running, waiting_quota, finalizing, done, failed, cancelled
pair_origin: generated, user_added
pair_split: unassigned, train, eval
job_state: created, running, paused, completed, cancelled, failed
pause_reason: session_ended, idle_timeout, no_gpu, stopped, heartbeat_timeout, user_stopped
artifact_kind: adapter_safetensors, adapter_gguf, checkpoint, eval_generations, license_notice
tone: neutral, friendly, formal, casual, technical, enthusiastic
length: short, medium, long
format: plain, bullets, json, markdown
```

## Tables

### users
| column | type | notes |
|---|---|---|
| id | uuid PK | = Supabase `auth.users.id` (JWT `sub`) |
| email | text | |
| display_name | text null | |
| onboarding_done | bool default false | |
| email_notifications | bool default true | |
| created_at, updated_at | | |

### provider_keys
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK users | idx |
| provider | provider | unique(user_id, provider) |
| ciphertext | bytea | Fernet-encrypted key |
| key_version | smallint | which encryption key |
| last4 | text | for masked display |
| status | key_status | |
| priority | smallint | fallback order (0 = first) |
| default_model | text null | e.g. `qwen/qwen3-32b` |
| terms_acknowledged_at | timestamptz null | required for gemini |
| last_verified_at, last_used_at | timestamptz null | |
| quota_reset_at | timestamptz null | when `quota_exhausted` |

### projects
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK | idx (user_id, updated_at desc) |
| name | text | 1–80 chars |
| status | project_status | idx |
| status_reason | text null | machine code |
| status_message | text null | human text |
| status_retry_to | project_status null | for failed → retry |
| status_changed_at | timestamptz | |
| base_model_id | text null | HF id |
| base_model_license | text null | |
| license_ack_at | timestamptz null | non-permissive license acknowledged |
| base_model_is_custom | bool default false | |
| gen_provider | provider null | |
| gen_model | text null | |
| style_id | uuid FK style_configs null | current style |
| total_bytes | bigint default 0 | for 50 MB cap |
| target_pairs | int default 500 | ≤ 2000 (D13) |
| deleted_at | timestamptz null | soft-delete marker during async purge |

### documents
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| project_id | uuid FK cascade | idx |
| filename | text | sanitized original |
| content_type | text | sniffed after upload |
| size_bytes | bigint | ≤ 20 MB |
| r2_key | text unique | |
| sha256 | text null | dedupe identical uploads in a project |
| status | document_status | |
| page_count | int null | |
| ocr_pages | int default 0 | |
| error | text null | |

### chunks
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| project_id | uuid FK cascade | idx |
| document_id | uuid FK cascade | idx |
| ordinal | int | order in document; unique(document_id, ordinal) |
| section_path | text | e.g. `Guide > Setup > Install` |
| text | text | |
| token_count | int | |
| page_start, page_end | int null | |
| embedding | vector(384) null | HNSW index `vector_cosine_ops`; queries always filter project_id |

### style_configs
Immutable snapshots; editing the style creates a new row (so previews and runs reference exactly what they used).
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| project_id | uuid FK cascade | idx |
| template_key | text null | if started from a template |
| description | text | ≤ 2,000 chars |
| tone, length, format | enums | |
| language | text | BCP-47, default `en` |
| examples | jsonb | `[{input, output}]` 1–5 items |
| system_prompt_in_data | bool default false | advanced toggle |
| dataset_format | text default `qa_chat` | `qa_chat` / `instruction` / `multi_turn` (ADR-0003); left out of `content_hash` when `qa_chat` |
| content_hash | text | sha256 of normalized fields; idx |

### style_templates (seeded, read-only)
`key` PK (`support_bot`, `tech_docs_assistant`, `json_extractor`, …), `name`, `description`, `defaults jsonb`. Saved user profiles (P7) add `user_style_profiles`.

### generation_runs
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| project_id | uuid FK cascade | idx |
| style_id | uuid FK style_configs | |
| kind | gen_kind | |
| state | gen_state | |
| prompt_version | text | e.g. `gen-v1` |
| provider_chain | jsonb | providers/models used, in order |
| total_chunks, done_chunks | int | |
| pairs_generated, pairs_kept | int | |
| tokens_in, tokens_out | bigint | for estimates |
| resume_at | timestamptz null | when waiting_quota |
| error | text null | |
| started_at, finished_at | timestamptz null | |

### generation_chunk_results (idempotency for fan-out)
`run_id` FK, `chunk_id` FK, `state` (done/failed/skipped), `pairs` int, `attempts` int, `error` text; PK(run_id, chunk_id).

### dataset_pairs
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| project_id | uuid FK cascade | idx (project_id, split, kept) |
| run_id | uuid FK generation_runs | |
| chunk_id | uuid FK chunks null | null for user-added |
| origin | pair_origin | |
| dataset_format | text default `qa_chat` | the pair's shape; user-added pairs are re-shaped when the style's format changes |
| question, answer | text | first prompt and last reply, for every format (search, sort and the table use these) |
| record | jsonb null | the rest of the example: `{"input"}` for an instruction, `{"middle": [turns]}` for a conversation (ADR-0003) |
| judge_correctness, judge_style | smallint null | 1–5 |
| judge_reason | text null | |
| kept | bool | passed judge + dedupe |
| dropped_reason | text null | `judge_low`, `duplicate`, `invalid_json`, `user_deleted`, `format_changed` |
| duplicate_of | uuid null | |
| split | pair_split | |
| edited | bool default false | |
| embedding | vector(384) null | for dedupe; may be nulled after finalize to save space |

Preview pairs are rows with `run_id` of a preview run; they are never part of the dataset.

### dataset_versions (frozen on approval)
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| project_id | uuid FK cascade | |
| version | int | unique(project_id, version) |
| train_count, eval_count | int | |
| train_r2_key, eval_r2_key | text | |
| sha256_train, sha256_eval | text | resume must use the same data |
| system_prompt | text null | if toggle on |
| dataset_format | text default `qa_chat` | frozen at approval; the training files are chat messages for every format |
| approved_at | timestamptz | |

### training_jobs
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| project_id | uuid FK cascade | idx |
| dataset_version_id | uuid FK | |
| backend | text | `colab` |
| base_model_id, base_model_license | text | copied from project at submit |
| train_mode | text | `lora16` or `qlora4` (from catalog / custom check, D15) |
| preset | text | quick / balanced / thorough |
| hyperparams | jsonb | resolved values |
| seed | int | |
| lib_versions | jsonb | pinned versions sent to notebook |
| notebook_version | text | git tag |
| state | job_state | |
| current_step, max_steps | int | |
| last_loss | real null | |
| last_heartbeat_at | timestamptz null | idx where state in (running) |
| pause_reason | pause_reason null | |
| runtime_info | jsonb | GPU name, VRAM, platform reported by notebook |
| started_at, completed_at, ended_at | timestamptz null | ended_at drives 14-day retention |

### job_tokens
`id`, `job_id` FK cascade, `token_hash` text unique, `token_prefix` text (first 8 chars for display), `expires_at`, `revoked_at` null, `last_used_at` null, `created_at`.

### training_metrics
Sampled loss curve: `job_id` FK cascade, `step` int, `loss` real, `lr` real null, `at` timestamptz; PK(job_id, step). Insert at most every N steps so ≤ 500 rows/job.

### checkpoints
`job_id` PK/FK (one row = latest only), `step`, `r2_key`, `size_bytes`, `sha256`, `uploaded_at`.

### artifacts
`id`, `job_id` FK cascade, `kind` artifact_kind, `r2_key`, `size_bytes`, `sha256`, `meta jsonb`, `expires_at`.

### evaluations
`id`, `job_id` FK cascade unique, `state` (pending/scoring/done/failed), `n_items`, `base_scores jsonb` (`{correctness, style, overall}` means), `tuned_scores jsonb`, `samples jsonb` (≤ 10 side-by-side), `metrics jsonb` (e.g. ROUGE-L, eval loss from notebook), `scored_at`.

### project_events (audit trail, small)
`id bigserial`, `project_id` FK cascade, `type` text, `from_status`, `to_status`, `actor` text, `data jsonb`, `at`. Index (project_id, at desc). Used for debugging and the activity feed.

### email_log
`id`, `user_id`, `project_id` null, `kind` text, `dedupe_key` text unique, `sent_at`. Prevents duplicate pause emails.

### playground_sessions (P5, optional persistence)
v1 keeps chat history client-side only. No table.

## Size budget (Supabase free = 500 MB)
- chunks: 50 MB text/project max → ~50k tokens… realistically ≤ 5 MB text + 384-dim vectors (1.5 KB each) — fine for hundreds of projects.
- dataset_pairs: ≤ ~3,000 rows/project incl. dropped; drop `embedding` for pairs after finalize.
- training_metrics ≤ 500 rows/job.
- Retention task purges: deleted projects; preview pairs older than 7 days; dropped pairs after dataset approval (keep counts).
- Admin usage endpoint reports `pg_database_size`.

## Migration order (P0–P5)
1. `0001_init`: `create extension vector`, enums, users, provider_keys, projects, documents, chunks (embedding column, no index yet), project_events, email_log
2. `0002_style_generation`: style_templates (+ seed), style_configs, generation_runs, generation_chunk_results, dataset_pairs
3. `0003_dataset_versions`
4. `0004_training`: training_jobs, job_tokens, training_metrics, checkpoints, artifacts
5. `0005_eval`: evaluations
6. `0006_vector_indexes`: HNSW indexes on `chunks.embedding` and `dataset_pairs.embedding` (create once data exists; can move earlier)
