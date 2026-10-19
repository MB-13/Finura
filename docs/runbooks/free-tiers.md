# Free-tier limits — verified 2026-10-07

Re-check before relying on any number; providers change limits without notice (Oracle halved A1 in 2026 with no announcement).

| Service | Free limits found | Impact on DocTune | Source |
|---|---|---|---|
| **Groq** | Per **model**, per org: `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b` → **30 RPM, 1K RPD, 8K TPM, 200K TPD** each | 200K tokens/day/model is far below the design doc's "~1M tokens ≈ one day". Rotate across the 3 open models (≈600K/day). 8K TPM ≈ 3 generation requests/min/model | https://console.groq.com/docs/rate-limits · https://console.groq.com/docs/models |
| **Cerebras** | **Payment method required**; $5 free credits that expire after 30 days; then paid. Free trial: 5 RPM, 1M TPD | **No longer free** → optional "if you have credits", never recommended | https://inference-docs.cerebras.ai/support/rate-limits |
| **Gemini API** | Free tier is Flash-only (Pro paid-only since Apr 2026). Limits are per-project, shown only in AI Studio; reported ~10–15 RPM, ~250–1,500 RPD, large TPM | Useful second provider (high TPM). Limits unknowable in advance → read from 429 headers. Google's terms include a no-competing-models clause (needs ack) | https://ai.google.dev/gemini-api/docs/rate-limits · https://agentdeals.dev/gemini-api-pricing-changes |
| **Oracle Always Free A1** | **2 OCPU / 12 GB RAM** (cut from 4/24 on 2026-06-15), 200 GB block storage. Reclaimed if 7-day p95 CPU < 20% **and** network < 20% **and** memory < 20% | Half the plan's original budget → one warm playground model, smaller worker pools. Memory use will stay > 20%, so reclamation is unlikely | https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm · https://linuxiac.com/oracle-quietly-cuts-free-tier-ampere-a1-resources-in-half/ |
| **Cloudflare Workers (free)** | 100K requests/day, **10 ms CPU per request**, 64 MiB uncompressed bundle (no compressed limit), 50 subrequests | 10 ms CPU rules out server rendering → the frontend is a static React (Vite) SPA on Pages | https://developers.cloudflare.com/workers/platform/limits/ |
| **Cloudflare R2** | 10 GB-month storage, 1M Class A, 10M Class B ops/month, free egress (Standard storage only) | Fine at launch scale; retention (14 days) and caps matter | https://developers.cloudflare.com/r2/pricing/ |
| **Supabase (free)** | 500 MB DB, 50K MAU, **2 active projects**, paused after 1 week inactivity | Use the 2 projects for dev + prod (local auth via Supabase CLI; no hosted staging) | https://supabase.com/pricing |
| **Resend (free)** | 3,000 emails/month, 100/day, 3 domains | Needs a verified domain for real sending → the ~$10/yr domain is required for email | https://resend.com/pricing |
| **Google Colab (free)** | ≤ 12 h sessions, idle timeouts, no guarantees. Banned: non-interactive web services, file hosting, P2P, mining, password cracking, SSH/remote desktop, bypassing the notebook UI via a web UI | Notebook design is compliant; FAQ says nothing explicit about third-party services → still on the launch checklist | https://research.google.com/colaboratory/faq.html |

## Model findings
| Item | Finding | Source |
|---|---|---|
| Qwen3.5 small series | Exists (Mar 2026): 0.8B / 2B / 4B / 9B, Apache 2.0 | https://huggingface.co/collections/Qwen/qwen35 |
| Unsloth + Qwen3.5 | **QLoRA 4-bit is "not recommended"** for Qwen3.5. 16-bit LoRA VRAM: 0.8B 3 GB, 2B 5 GB, 4B 10 GB, **9B 22 GB (won't fit a T4)**. Custom Mamba Triton kernels compile slowly on T4. Free Colab notebooks exist for 0.8B/2B/4B | https://unsloth.ai/docs/models/qwen3.5/fine-tune |
| llama.cpp + Qwen3.5 LoRA | Supported: `convert_lora_to_gguf.py` → adapter tagged `qwen35`; old converter versions mis-tag as `qwen3` (load fails) | https://github.com/ggml-org/llama.cpp/discussions/10123 |

## Colab spike results (2026-10-07, ADR-0001)
- Qwen3.5 4B 16-bit LoRA in **fp16** on T4: ✅ stable, 9.7 GB VRAM, ~6 min kernel compile per session.
- Qwen3 8B QLoRA: ✅ 8.25 GB VRAM.
- Colab free system RAM measured **13.6 GB**; ~75 GB free disk. Free Google Drive is 15 GB shared with Gmail/Photos (merged 4B = 9.3 GB → HF only).
