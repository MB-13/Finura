---
name: write-prd
description: Write a PRD for a DocTune feature or roadmap phase (Foundation, Dataset generation, Colab training, Checkpoint & resume, Delivery, Growth), grounded in the design doc. Use when the user asks for a PRD, spec, or requirements.
argument-hint: "[phase or feature]"
---

# Write PRD

Input: $ARGUMENTS. Read the matching sections of `docs/design/doctune-design.md` and any `docs/ideas/` file first. Ask only about genuinely missing decisions.

Write `docs/prd/<slug>.md`:

```markdown
# <Feature / Phase> — PRD
Status: Draft · Owner: <name> · Updated: <date> · Design doc sections: <links>

## 1. Problem & context
## 2. Goals & "done when"        (use the roadmap's "Done when…" line if it's a phase)
## 3. Non-goals                  (what's deferred to later phases)
## 4. User stories               (P0/P1/P2, with acceptance criteria per P0)
## 5. Flow & screens             (which project statuses this covers; what each screen shows)
## 6. API surface                (endpoints, auth mode: user JWT vs job token)
## 7. Async work                 (Celery tasks, status transitions, SSE events)
## 8. Data                       (entities/fields touched)
## 9. Limits & free-tier impact  (caps, provider rate limits, storage, R2 retention)
## 10. Security & compliance     (keys, tokens, Colab rules, licenses)
## 11. Edge cases & failure modes(rate limits, pauses, bad files, provider exhaustion)
## 12. Open questions & risks
```

Requirements must be concrete enough for `system-architect` to plan from. Then suggest `/plan-feature`.
