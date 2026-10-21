---
name: brainstorm
description: Structured brainstorming for a DocTune feature, improvement or open question - frame the problem, generate distinct options, score them against DocTune's constraints (free-only, BYO key, user-run Colab), and recommend one. Use when the user says "brainstorm", "ideas for", "how could we", or is exploring options.
argument-hint: "[feature, problem or question]"
---

# Brainstorm

Topic: $ARGUMENTS

Read the relevant parts of `docs/design/doctune-design.md` first so ideas build on decisions already made (check the Decisions log — don't reopen resolved questions unless the user wants to).

## Steps
1. **Frame** — Restate the problem, who hits it (non-ML developers, students, small teams), and when in the flow (upload → style → preview → review → train → playground). Ask at most 3 questions, only for genuinely missing info.
2. **Diverge** — 4–6 genuinely different options (not tweaks of one). One line each: idea, how it works, which component it touches (web / api / worker / notebook).
3. **Research** — For the top 2–3, check how others solve it (web search, cite).
4. **Score** (1–5) — User value · Effort · Fits free-tier constraint · Fits Colab rules & BYO-key model · Risk. One-line verdict each.
5. **Recommend** — Pick one; give MVP scope, explicit non-goals, riskiest assumption and how to test it, and which roadmap phase it belongs to.
6. **Save** — `docs/ideas/<slug>.md`. If it changes the design doc, list the section and proposed wording. Suggest `/write-prd` or `/plan-feature` next.

Pause for the user's input after steps 1, 2 and 5.
