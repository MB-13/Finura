# 12 — Launch

## 1. Launch checklist (design doc + plan)
| # | Item | Owner | Evidence required |
|---|---|---|---|
| L1 | Google ToS + Colab Additional Terms reviewed; notebook interactive-only | pm + sec | quoted clauses, date |
| L2 | doctune.dev / .app availability, GitHub + HF org names, basic trademark search | pm | search results |
| L3 | Groq (per-model limits), Gemini, Cerebras free tiers & terms re-verified against `docs/runbooks/free-tiers.md`; `providers.py` updated | pipe | provider pages, date |
| L4 | Supabase, R2, Oracle, Resend, Sentry limits re-verified | ops | `free-tiers.md` |
| L5 | Privacy policy + terms published (third-party AI processing, Colab disclaimer) | pm | URLs |
| L6 | ✅ Qwen3 8B QLoRA fits a T4 (8.25 GB) and the D16 default (Qwen3.5 4B lora16) is confirmed — ADR-0001. Re-confirm on the release notebook | ml | Colab run log |
| L7 | Security review: no Critical/High | sec | report |
| L8 | Backups + restore test | ops | runbook entry |
| L9 | Monitoring & alerts firing to the team | ops | test alert |
| L10 | Colab release checklist (`10 §6`) all ✅ on the release tag | ml + qa | checklist |
| L11 | E2E suite green on production-like stack | qa | CI run |
| L12 | Domain bought (~$10/yr) and verified in Resend with SPF/DKIM, or email explicitly deferred (in-app notices only) | ops | test emails |

## 2. Launch plan
1. Soft launch: invite 10–20 testers (students/devs); collect feedback via a simple form; watch Sentry, queue depth, free-tier usage daily.
2. Fix top issues (expect: Colab confusion, key setup, dataset quality).
3. Public launch posts (pm drafts): Hugging Face community, Reddit r/LocalLLaMA, Hacker News "Show HN", dev.to tutorial "Fine-tune a model on your docs for $0".

## 3. Metrics to watch
Activation funnel per step (signed up → key connected → preview → dataset approved → training started → ready → playground used) · median time per step · pause rate & resume success rate · generation failures by provider · free-tier usage %.
Implement as `project_events` queries in `/admin/usage` (no third-party analytics needed for v1).

## 4. Post-launch
Weekly: free-tier usage review, provider terms check (monthly), dependency updates, notebook compatibility check against Colab's current image (monthly — Colab updates CUDA/torch regularly).
