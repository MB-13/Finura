# DocTune UI inspiration brief

Status: proposal (October 2026). Builds on the token system in `docs/plan/06-web-ui.md §8`; it does not replace it.
Method: headless-Chrome captures of public marketing/docs pages (1440x900 hero, 1440x5000 long, 390x844 mobile), compared with our current screens. We borrow patterns and principles only. No copy text, logos, illustrations or other assets are taken from any site.

Sites studied: linear.app, vercel.com, v0.app, resend.com, replicate.com, together.ai (+ docs.together.ai fine-tuning quickstart), modal.com, reducto.ai, cohere.com, huggingface.co/autotrain, raycast.com, supabase.com, cal.com, peec.ai, hume.ai, OpenAI fine-tuning docs. The curated list at saasframe.io/landing-page-examples/machine-learning pointed to Peec, Reducto and Hume.

---

## 1. Diagnosis: what great sites do that we don't yet

Our screens are clean, accessible and consistent. They look like a well-made **template**, not a **product with a point of view**. Specifically:

1. **The hero headline is too timid.** Ours is about 44px in Inter 700 at default tracking. Linear, Cal, Peec and Raycast set 64–80px, weight 600–700, tracking −0.03 to −0.045em, line-height ~1.0–1.05. That scale is what reads as "designed".
2. **Every section has the same rhythm.** Our landing stacks heading → equal small cards → heading → icon grid → card → FAQ, all on the same background. The best pages alternate between a two-tone statement paragraph (Linear), a bento grid with *live UI vignettes* in each tile (Supabase), a tabbed feature showcase with a product frame on the right (Together, Reducto, Modal), and a full-bleed tinted band.
3. **Icons stand in for product.** Our step and feature tiles each show a 16px outline icon in a soft square, a pattern every SaaS template uses. Supabase, Reducto and Peec put a **miniature of the real UI** (a table, a chat bubble, a parsed page) in each tile instead. DocTune's real artefacts (Q&A pair, loss curve, source citation, GGUF download) are much more convincing than icons.
4. **There is no structural framing or texture.** Peec and Cal draw thin vertical guide rails at the content edges, with "+" crosshair marks where sections meet. Supabase and Modal use a faint grid or dot field behind visuals. We have one lavender radial glow at the top and flat `background` everywhere else.
5. **The hero visual is one floating card.** Linear, Peec and Cohere show a **framed app window** (sidebar plus content, partly cropped by the fold) that suggests a whole product. Our dataset-review card is good content but reads like a widget.
6. **Live work doesn't feel alive.** Our generating and training screens show a card with a progress bar and static text. Linear's activity feed (avatar · actor · action · relative time, connected by a thin rail) and Together's quickstart steps ("Watch the job complete") make waiting legible. We have SSE data (pairs generated, steps, checkpoints, heartbeats) and don't show it as a stream.
7. **Boxes sit inside boxes.** The generating panel puts a bordered, tinted box inside a card. Top sites use hairline dividers and whitespace inside a surface, not more borders.
8. **Numbers are styled like body text.** "42%", "940 pairs" and "846 / 94" are bold Inter. Together, Supabase and Raycast set metrics and labels in a **mono face** (tabular, slightly smaller caps labels), which gives a precise, instrument-panel feel.
9. **Dark mode is an inversion, not a design.** Linear, Supabase and Raycast use near-black backgrounds (L ≈ 0.14–0.17), surfaces only 2–4% lighter, 1px borders at ~8% white, and a lighter **top-edge highlight** on cards. Ours is mid-grey cards on dark grey with uniform borders.
10. **The CTA band and footer are generic.** Ours is a solid indigo block. Vercel, Linear and Resend close with a quiet, centred CTA over a subtle glow, then a dense multi-column footer.

What we already do well and should keep: honest-expectations content, plain-language copy, the status colour system, the stepper, and the real-looking Q&A in the hero.

---

## 2. Patterns to adopt

Each item gives **Source → What → Why it fits → Where**.

### Marketing

**A. Display-scale hero with a two-tone headline.** Peec (peec.ai), Together (together.ai), Linear (linear.app).
What: 64px desktop / 40px mobile, weight 650, tracking −0.035em, line-height 1.02. The second line or key phrase is set in `muted-foreground` (Peec, Together) or in brand colour for a single word (Modal, Supabase). The subhead is 18–20px, `muted-foreground`, max ~34rem.
Why: one sentence ("your documents → your model") carries the whole pitch. Two-tone keeps it calm without a gradient-text gimmick.
Where: `routes/Landing.tsx` hero; reuse a smaller version (48px) for the final CTA.

**B. Inline "chip" nouns inside the subhead.** Peec.
What: key nouns in the subhead rendered as small bordered pills with an icon (`[file] documents`, `[gpu] free GPU`, `[chat] playground`), on the same baseline as the text.
Why: shows a non-technical audience the three moving parts at a glance.
Where: Landing hero subhead, plus the onboarding intro (`features/onboarding/OnboardingFlow.tsx`).

**C. Framed product window as the hero visual.** Linear, Peec, Cohere, Supabase ("manage without leaving the dashboard").
What: a full-width (max-w-6xl) rounded-xl frame with a 1px border, `shadow-lg`, and a faux title bar (three dots or a breadcrumb). Inside is a *real composition of our app*: stepper rail on the left, the dataset-review or training panel on the right. It is cropped at the bottom by a fade-to-background mask. On mobile, show only the right panel.
Why: proves "there is a real product here", which matters for a free tool.
Where: replace the single card in `features/marketing/HeroVisual.tsx`; build it from real components with static fixture data so it never drifts from the app.

**D. Guide rails and crosshair section joints.** Peec, Cal.
What: two 1px vertical lines at the container edges (`border-x border-border/60` on a full-height wrapper) and a horizontal hairline between sections, with a small "+" mark where the lines cross. Behind the hero, a faint dot or grid field (`radial-gradient` dots, 24px pitch, 4–6% opacity) masked to fade out.
Why: costs nothing (pure CSS), adds structure and a "crafted" feel, and works in light and dark.
Where: `features/marketing/MarketingLayout.tsx` / `MarketingContainer.tsx`. Use it in marketing only, never in the app.

**E. "How it works" as a tabbed or stepped showcase, not five equal cards.** Together (tabs with a product image on the right), Reducto (vertical list on the left whose active item expands, with a visual on the right), Modal (left sub-nav plus a dark visual panel).
What: on the left, 5 steps as a vertical list. The active step shows a 2-line description and the rest stay collapsed. On the right, a framed vignette for that step (dropzone with files, style form, a Q&A pair being approved, a loss curve, a chat with sources). Auto-advance every ~5s, pause on hover or focus, and click to select. Respect `prefers-reduced-motion`: no auto-advance.
Why: our product *is* a 5-step journey, so showing each step's real screen teaches the flow better than icons.
Where: Landing "How it works"; the vignettes can be reused in the onboarding flow.

**F. Bento feature grid with UI micro-vignettes.** Supabase (each tile has its own mini visualisation), Peec ("Key features" cards with partial tables).
What: a 3-col grid with mixed spans (one 2x tile plus four 1x tiles). Each tile has a title, a one-line description and a small *non-interactive* illustration built from our components: a score chip row, a "Paused · progress saved" notice, a "Sources (2)" expander, a download row with a size badge, a preset picker. No icons-in-squares.
Where: replaces the "Built for people who aren't ML experts" icon grid.

**G. Statement paragraph in two tones.** Linear ("A new species…" with the first sentence in foreground and the rest in muted).
What: one 28–32px paragraph, max ~40rem, first clause `foreground`, remainder `muted-foreground`, followed by generous space (py-24).
Where: between the hero and How it works. Write our own sentence about "style from fine-tuning, facts from your documents".

**H. Quiet closing CTA plus a dense footer.** Vercel, Linear, Supabase.
What: centred 40–48px headline, one primary and one ghost button, over a soft brand glow (radial, 10–15% opacity), *not* a solid indigo slab. Footer: logo and one-line mission on the left; columns Product / Help / Legal / Open source; a bottom row with theme toggle and "Built on free tiers".
Where: Landing bottom and `features/marketing/FooterLinks.tsx`.

**I. Mono overlines.** Together, Modal, Linear ("FIG 0.1").
What: section eyebrows in mono, 11–12px, uppercase, tracking 0.08em, `muted-foreground`, optionally with a small square or icon glyph. Replaces brand-coloured "HOW IT WORKS".
Where: `text-overline` utility (index.css); used across Landing and Docs.

### App

**J. Activity timeline for long-running work.** Linear's issue activity feed; Together's fine-tuning "watch the job" steps.
What: below the progress header, a vertical feed. Each event is an icon dot, a short sentence, and the right-aligned relative time in mono. A thin connecting rail joins the events. Example events: "Read 3 documents · 128 sections", "Preview approved", "Batch 12 written · 24 pairs", "Switched to Gemini (Groq rate limit)", "Checkpoint saved at step 300", "Kaggle session restarted, resuming". The newest event fades in. The region is `aria-live="polite"`.
Why: it turns multi-hour, multi-day waits into visible progress and explains pauses honestly (our copy principle).
Where: `features/generation/GenerationPanel.tsx`, `features/training/TrainingPanel.tsx`, `KaggleRunPanel.tsx`, `EvaluatingPanel.tsx`. It needs the events from SSE; if the API lacks an event list, derive it client-side from status/progress deltas first.

**K. Live sample stream during generation.** Peec and v0 show real content flowing in.
What: a "Latest pairs" strip showing the 3 most recent Q&A pairs as compact cards that slide in (150ms) as they arrive, each with a "View all" link.
Why: users see *their* style taking shape, which reassures them during a long run.
Where: GenerationPanel (reuses `PairRow` styles).

**L. Instrument-style metrics.** Together's docs and dashboards, Supabase's table editor, Raycast's "Information" panel.
What: big numbers in mono with `tabular-nums` (e.g. 36px for the hero % and 24px for stats). Labels are 12px mono uppercase in muted. Stats sit in a single row separated by hairline dividers (`divide-x`), not in four tinted boxes.
Where: `components/Stat.tsx`, `ReviewPanel.tsx` stats row, `ProgressWithEta.tsx`, `EvalComparison.tsx`.

**M. One surface per panel: hairlines, not nested boxes.** Linear, Vercel dashboards.
What: inside a panel card, separate regions with `border-t border-border/70` and padding. Drop the inner `bg-muted` boxes (e.g. the GPU / Heartbeat / Checkpoint key-value block and the generation progress box).
Where: GenerationPanel, TrainingPanel/KaggleJobInfo, ReviewPanel, ResultsPanel.

**N. A denser projects list option.** Linear (issue rows), Peec (table with inline deltas).
What: keep the cards, but make the status the card's *top accent*: a 2px top border in the status colour, or a status-tinted dot plus label in the meta row. Remove the duplicated "Step 5 of 6" when the badge already says Training. Add a list/grid toggle where list = name · status · step · model · updated, sortable by updated. Add a tiny sparkline (loss or progress) on training cards.
Where: `routes/Projects.tsx`, `features/projects/ProjectCard.tsx`.

**O. A stepper with done / now / next semantics and a compact header.** Linear sidebar, Together docs "On this page" rail.
What: the done steps collapse to a single line (check + label, no description), the current step is emphasised (brand-tinted pill background), and the future steps are muted. The project title shrinks to 24px with the status badge inline, so the panel starts higher on the page (the panel currently starts ~220px down).
Where: `ProjectStepper.tsx`, `ProjectHeader.tsx`.

**P. Chat with clear model identity and citation chips.** v0's composer, Linear's agent panel, Perplexity-style sources (a common pattern).
What: the composer is a rounded-2xl box with the textarea on top and a toolbar row below (model chip, "Use my documents" toggle as a chip, send button). Sources render as numbered inline chips `[1]` in the answer, plus a horizontal row of source cards (file name, section, snippet) under the message instead of a collapsed accordion. User bubbles use `secondary`/`accent` instead of the solid primary fill, and the assistant message has no bubble.
Where: `features/playground/PlaygroundPage.tsx`, `ChatMessageView.tsx`. The settings side panel can become a collapsible sheet on < lg.

**Q. A split-screen sign-in.** Cal (form left, product vignette right), Linear/Vercel (minimal centred form).
What: on lg+, the left half holds the form (no card border, just the form on background) and the right half holds a tinted panel with the framed hero vignette or a rotating Q&A example. On mobile, show the form only. Move the dev-only password block behind a "Developer sign-in" disclosure.
Where: `features/auth/AuthShell.tsx`, `routes/SignIn.tsx`.

**R. Empty states that preview the outcome.** Supabase templates and Linear's empty views show what "full" looks like.
What: replace the dashed box plus folder icon with a 3-step mini-strip (upload → style → chat) that uses the same vignettes as the landing, one primary CTA, and a secondary "See an example project" link (a read-only fixture).
Where: `components/EmptyState.tsx` (add a `visual` slot), Projects empty, Playground unavailable, Dataset empty.

**S. Results as a celebration, then reference.** The Vercel deployment-ready screen (preview thumbnail + big domain) is a common pattern.
What: the top of Results is a hero strip: "Your model is ready", the three eval deltas as large mono numbers (+1.0 / +2.5 / +1.7), and the primary "Open playground" button. Below that, keep Downloads, Ollama and License as quieter sections with hairline separators. Use a subtle one-time confetti-free accent: a success-tinted glow behind the strip.
Where: `features/results/ResultsPanel.tsx`, `EvalComparison.tsx`.

---

## 3. Token and typography adjustments

All free and self-hosted via fontsource; no paid assets.

| Change | Detail |
|---|---|
| Display type | Use Inter's **optical-size axis** (`@fontsource-variable/inter/opsz.css`, the same package, no new dependency) so headings ≥ 32px render as Inter Display. Add `text-display` (64/66, −0.035em, weight 650; 40/44 on mobile) and `text-display-sm` (48/52, −0.03em). Tighten `text-page-title` to −0.025em. Fallback if opsz isn't wanted: `@fontsource-variable/geist` (OFL) for display only. |
| Mono | Add `@fontsource-variable/geist-mono` (OFL) or `@fontsource-variable/jetbrains-mono` (OFL) as `--font-mono` so metrics, overlines and tokens look intentional across OSes. The current system stack renders differently on every platform. |
| Overline | `text-overline` → mono, 11px, 0.08em, `muted-foreground` (not primary). |
| Dark palette | background `oklch(0.155 0.01 277)`, card `oklch(0.185 0.012 277)`, border `oklch(1 0 0 / 8%)`, plus `--highlight: oklch(1 0 0 / 6%)` used as `shadow-[inset_0_1px_0_var(--highlight)]` on cards and buttons (top-edge sheen). Re-check AA for muted-foreground. |
| Light palette | Keep. Move the borders slightly cooler/lighter (`oklch(0.92 0.006 277)`) and give cards `shadow-xs` plus border rather than shadow-sm, which flattens toward the Linear/Vercel feel. |
| Backgrounds | New utilities: `bg-grid` (1px lines, 32px, 5% foreground, radial mask), `bg-dots` (24px), and `bg-glow` (radial primary at 12% light / 18% dark). Marketing and auth only. |
| Radius | Keep `--radius: 0.75rem`. Use rounded-2xl only for the product frames and the chat composer. Buttons stay rounded-md (not pill) to match the existing system. |
| Buttons | Primary: add a 1px inner top highlight and a `shadow-xs` tinted with primary. Secondary/outline: `bg-card` with a hairline border. Small ghost "link with arrow" variant (`→` slides 2px on hover) for marketing. |
| Motion | 150–200ms ease-out for state changes; 400ms fade/translate-y-2 on scroll reveal (IntersectionObserver, CSS only, `prefers-reduced-motion` disables it). There is no motion library today and none is needed. |

---

## 4. Prioritised implementation list

**P1: biggest visual gain, low risk**
1. Display type, mono font, mono overline, dark-palette rework, card top highlight. Files: `src/index.css`, `package.json`, `frontend/preview/` gallery.
2. Landing hero: display headline in two tones, chip nouns, framed product window (pattern C). Files: `routes/Landing.tsx`, `features/marketing/HeroVisual.tsx`.
3. Marketing guide rails, dot/grid background, quiet CTA plus footer (D, H). Files: `features/marketing/MarketingLayout.tsx`, `MarketingContainer.tsx`, `FooterLinks.tsx`.
4. Remove nested boxes and adopt hairline sections plus instrument metrics in the app panels (L, M). Files: `components/Stat.tsx`, `KeyValue.tsx`, `features/generation/GenerationPanel.tsx`, `features/training/TrainingPanel.tsx`, `KaggleJobInfo.tsx`, `ProgressWithEta.tsx`, `features/dataset/ReviewPanel.tsx`.

**P2: product feel**
5. Activity timeline plus live pair stream (J, K). Files: GenerationPanel, TrainingPanel, KaggleRunPanel, EvaluatingPanel, new `components/ActivityFeed.tsx`. This may need an events field in the SSE payload; plan it with the backend first (`/plan-feature`).
6. Tabbed "How it works" showcase plus bento features (E, F). Files: Landing, new `features/marketing/StepShowcase.tsx`, `FeatureBento.tsx`.
7. Playground composer, inline citations and source cards (P). Files: `features/playground/*`.
8. Split-screen sign-in (Q). Files: `features/auth/AuthShell.tsx`, `routes/SignIn.tsx`.
9. Compact stepper and header (O). Files: `ProjectStepper.tsx`, `ProjectHeader.tsx`.

**P3: polish**
10. Projects list/grid toggle, status accent, sparkline (N). Files: `routes/Projects.tsx`, `ProjectCard.tsx`.
11. Results hero strip (S). Files: `features/results/ResultsPanel.tsx`, `EvalComparison.tsx`.
12. Visual empty states and an example project fixture (R). Files: `components/EmptyState.tsx`, Projects, Playground.
13. Scroll-reveal motion and a two-tone statement paragraph (G). Files: Landing, `index.css`.

Each item ends with `pnpm lint && pnpm typecheck && pnpm test`, light/dark/360px screenshots, and an AA contrast check of any new token pair.

---

## 5. Things NOT to copy

- **Logo walls, testimonials, "trusted by" rows, usage stats or star ratings** (Vercel, Cal, AutoTrain, Supabase). We have none, and inventing them would be dishonest. If we ever add social proof, use real numbers only (e.g. a live "models trained" counter from our own DB).
- **Fake avatars or people** in the hero product frame. Use neutral initials and generic project names.
- **Heavy WebGL or 3D hero art and particle fields** (Modal's hex lattice, Hume's particles, Together's 3D shapes, Raycast's keyboard). They are heavy on bundle and CPU, off-brand for a calm "no ML knowledge needed" tool, and would hurt Cloudflare Pages load time on low-end devices.
- **Saturated gradient floods** (Replicate's magenta/yellow) and **gradient text**. One brand colour stays the rule.
- **All-black marketing with white serif headlines** (Resend, Reducto's editorial serif). It is beautiful but would split our identity from the light-first app. Keep both themes and default to the system theme.
- **Announcement bars and cookie walls.** We set no tracking cookies, so we don't need a banner. Don't add promo strips.
- **Pill-shaped, all-caps mono buttons** (Together). They reduce readability for non-technical users.
- **Code-first heroes** (Replicate, Supabase, Resend SDK tabs). Our audience doesn't write code; show the product UI instead.
- **"Contact sales" / "Request a demo"** CTAs. DocTune is free and self-serve.
- **Any copy, illustration, icon set or logo from these sites.** Patterns only; we use lucide icons and our own text.

## 6. Reference screenshots

Saved under the session scratchpad `inspiration/<site>/` (`hero.png`, `long.png`, `long1/2.png` = half-scale slices, `mobile.png`). They are not committed, because they contain third-party trademarks.
