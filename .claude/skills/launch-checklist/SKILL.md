---
name: launch-checklist
description: Work through DocTune's pre-launch checklist from the design doc - Colab/Google terms review, name and trademark checks, re-verifying free tiers and terms for Groq/Gemini/Cerebras/Supabase/R2/Oracle, privacy policy and terms, and confirming Qwen3 8B QLoRA fits a T4 and the default model is confirmed. Use when preparing a release or asked "are we ready to launch".
---

# Launch checklist

Read the "Launch checklist" and "Decisions log" sections of `docs/design/doctune-design.md`, then for each item:

| # | Item | How to verify |
|---|---|---|
| 1 | Google ToS + Colab Additional Terms; notebook within free-tier rules | Fetch current terms/FAQ; compare against `ml-conventions` notebook rules; quote relevant clauses |
| 2 | Name: doctune.dev / .app, GitHub + Hugging Face org names, basic trademark search | Web search; report availability evidence, not guesses |
| 3 | Free tiers & terms: Groq (per model), Gemini, Cerebras (+ Supabase, R2, Oracle, Resend, Sentry) | Fetch current pricing/limits pages; compare with `docs/runbooks/free-tiers.md` and update it |
| 4 | Privacy policy + terms of use (third-party AI processing, Colab disclaimer) | Check the pages exist in `frontend/` and cover these points |
| 5 | Qwen3 8B QLoRA fits a T4; default model (D16) confirmed (Qwen3.5 9B was dropped) | Needs a real Colab run — ask the user to run the notebook; record peak VRAM |

Also confirm: caps enforced, R2 lifecycle rule active, Sentry key scrubbing, backups, `/ship-check` green.

Write results to `docs/launch-checklist.md` with date, status (✅ / ⚠️ / ❌), evidence links, and follow-ups. Use sources fetched today — free-tier terms change often. Never mark an item done without evidence.
