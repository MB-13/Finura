# ADR-0001 — Default base model and training mode

Date: 2026-10-07 · Status: **Accepted** (llama.cpp generation check pending, see "Open items") · Evidence: `notebook/spike/results/` (Colab spike, `notebook/spike/doctune_spike_t4.ipynb`)

## Context
Plan decision D16 left the default model to a real Colab test. Unsloth advises against QLoRA for Qwen3.5, and its docs describe bf16 training, which a T4 doesn't support. We needed to know whether Qwen3.5 4B trains in fp16 16-bit LoRA on a free T4, and how it compares with Qwen3 4B QLoRA.

## Environment measured
Free Colab, Tesla T4 (15.6 GB VRAM, no bf16), 13.6 GB system RAM, ~75 GB free disk. Python 3.13, torch 2.11.0+cu130, transformers 5.17.0, TRL 1.13.0, PEFT 0.21.1, bitsandbytes 0.50.2, Unsloth 2026.10.1.
Dataset: 500 synthetic chat pairs, **~88 tokens/example (short)**. Batch 2 × grad-accum 4, LoRA r=16/α=32, lr 2e-4.

## Results
| | Qwen3.5 4B lora16 (fp16) | Qwen3 4B qlora4 | Qwen3 8B qlora4 (bs 1×8, seq 1024) |
|---|---|---|---|
| Stable (no NaN/inf) | ✅ | ✅ | ✅ |
| Load time | 130 s | 82 s | 120 s |
| First step (incl. kernel compile) | **348 s** | 18 s | 14 s |
| Median step | 3.00 s | 2.11 s | 4.99 s |
| Peak VRAM | 9.66 GB | 4.24 GB | 8.25 GB |
| Peak RAM | 5.7 GB | 4.9 GB | 7.6 GB |
| Loss first5 → last5 | 2.40 → 0.074 | 3.93 → 0.078 | 3.28 → 0.88 (20 steps) |
| min / 1k pairs / epoch (short examples) | 6.3 | 4.4 | 10.4 |
| Style learned (3 samples) | ✅ all 3 | ✅ all 3 | n/a |
| Facts in samples | ✅ 3/3 correct | ❌ 1/3 wrong ("works with 5 GHz") | n/a |

Checkpoint & resume (Qwen3.5 4B): checkpoint 148 MB (adapter + optimizer + scheduler + RNG), zip 2.5 s; resumed at step 21; loss steps 21–40 matched the uninterrupted run (mean relative diff 0.07%, max 0.26%). ✅

Export (Qwen3.5 4B):
| Step | Result | Time | Peak RAM |
|---|---|---|---|
| Adapter save | 105 MB (82 MB zipped) | 5 s | 6.9 GB |
| Adapter → GGUF (llama.cpp `convert_lora_to_gguf.py`) | 42.5 MB, tagged **`qwen35`** ✅ | 25 s | 7.4 GB |
| GGUF Q4_K_M | 2.78 GB ✅ | **22.5 min** (includes building llama.cpp) | **10.1 GB** of 13.6 |
| Merged 16-bit | **9.34 GB** ✅ | 5.7 min | 5.5 GB |
| llama.cpp run of fine-tuned GGUF | model loaded, then **killed (SIGKILL)** | — | 12.6 GB |
| llama.cpp base GGUF + adapter GGUF | base + adapter **loaded** (LoRA tensors initialised), then **killed (SIGKILL)** | — | 12.7 GB |

The two SIGKILLs happened while the notebook's Python process still held the trained model in RAM (system RAM peaked at 12.6–12.7 of 13.6 GB). They show a Colab memory limit in the test setup, **not** a llama.cpp incompatibility: both models and the adapter loaded. (The notebook wrongly reported these steps as `ok`; fixed in the notebook.)

## Decision
1. **Default base model: Qwen3.5 4B, 16-bit LoRA in fp16** (`train_mode = lora16`). fp16 is stable on T4. It's 1.42× slower per step than Qwen3 4B QLoRA (under the 1.5× threshold) and gave better factual answers in the samples.
2. **Qwen3 4B QLoRA stays in the catalog** as the "faster" option and the automatic fallback if a user's runtime fails on Qwen3.5.
3. **Qwen3 8B QLoRA: training fits a T4** (8.25 GB at seq 1024). `fits_t4 = yes` for training. Exports for 8B are **adapter-only by default**; GGUF/merged for 8B are marked experimental until tested (a 4B GGUF export already peaked at 10.1 GB of Colab's 13.6 GB RAM).
4. **Merged 16-bit for 4B is 9.3 GB**, which is most of a free 15 GB Google Drive → merged export goes to the user's **Hugging Face account only**, never to Drive by default. GGUF (2.8 GB) is the default Drive export.
5. Pin the notebook to the measured versions: Unsloth 2026.10.1, torch 2.11.0, transformers 5.17.0, TRL 1.13.0, PEFT 0.21.1, bitsandbytes 0.50.2 (bump deliberately, re-run the release checklist).

## Consequences
- **Every Qwen3.5 session pays ~6 min of kernel compilation + ~2 min loading**, including each resume. The notebook must say so ("compiling kernels, this takes a few minutes the first time in each session"), and time estimates add ~8 min per session.
- **Time hints must be per token, not per pair.** Real DocTune examples will be ~300–600 tokens vs 88 here. Rough expectation: 500 pairs × 2 epochs (Balanced) ≈ 30–60 min of training + ~8 min startup — well inside a free Colab session. Re-measure with realistic lengths in T3.2.
- **GGUF export takes ~22 min** on Colab (llama.cpp build dominates). Show it as a separate, optional cell with a progress message; the adapter upload happens first so the project reaches `ready` without waiting for the GGUF.
- The chat template trains in non-thinking mode (`<think>\n\n</think>` block present); exports and the playground must use the same template.
- llama.cpp warned that LoRA tensors "cannot use buft CPU_REPACK, fallback to CPU" → base + adapter inference on ARM may be slower than base alone. Measure on the Oracle VM (T5.6); if too slow, serve a merged GGUF for the playground instead (would need R2 space: ~2.8 GB per active model).

## Open items
- **llama.cpp generation output not yet observed.** Re-run with the fixed notebook's Test F (fresh session, frees the training model before running llama.cpp), or test directly on the Oracle VM with the saved `adapter.gguf`.
- 8B GGUF export on Colab RAM — untested.
- Training time with realistic example lengths — T3.2.
