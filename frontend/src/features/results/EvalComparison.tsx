import { ChevronDown, Loader2, Minus, TrendingDown, TrendingUp } from 'lucide-react'
import { type ReactNode, useLayoutEffect, useRef, useState } from 'react'

import { Callout } from '@/components/Callout'
import { SafeMarkdown } from '@/features/playground/ChatMessageView'
import { parseSamples, SCORE_LABELS, scoreScale, type Sample } from '@/features/results/eval-utils'
import type { Evaluation } from '@/features/training/api'
import { formatScore } from '@/lib/format'
import { cn } from '@/lib/utils'

const round1 = (v: number) => Math.round(v * 10) / 10

function Bar({ label, value, scale, tone }: { label: string; value: number; scale: number; tone: 'base' | 'tuned' }) {
  const pct = Math.max(0, Math.min(100, (value / scale) * 100))
  return (
    <div className="flex items-center gap-3 text-xs">
      <span className={cn('w-14 shrink-0', tone === 'tuned' ? 'font-medium text-foreground' : 'text-muted-foreground')}>{label}</span>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={scale}
        aria-valuenow={value}
        className="h-1.5 flex-1 overflow-hidden rounded-full bg-border/70"
      >
        <div className={cn('h-full rounded-full', tone === 'tuned' ? 'bg-primary' : 'bg-muted-foreground/45')} style={{ width: `${pct}%` }} />
      </div>
      <span className={cn('text-metric w-8 text-right text-[0.8125rem]', tone === 'base' && 'text-muted-foreground')}>{formatScore(round1(value))}</span>
    </div>
  )
}

/** "+0.8 vs original" in mono with an arrow icon so the direction never relies on colour. */
function Delta({ base, tuned }: { base: number; tuned: number }) {
  const d = round1(tuned) - round1(base)
  const rounded = Math.round(d * 10) / 10
  if (rounded === 0)
    return (
      <span className="inline-flex items-center gap-1 text-metric text-sm text-muted-foreground">
        <Minus className="size-3.5" aria-hidden /> No change
      </span>
    )
  const up = rounded > 0
  return (
    <span className={cn('inline-flex items-center gap-1 text-metric text-sm', up ? 'text-success-muted-foreground' : 'text-warning-muted-foreground')}>
      {up ? <TrendingUp className="size-3.5" aria-hidden /> : <TrendingDown className="size-3.5" aria-hidden />}
      {up ? '+' : '−'}
      {formatScore(Math.abs(rounded))}
      <span className="sr-only"> vs original</span>
    </span>
  )
}

export function EvalComparison({ evaluation }: { evaluation: Evaluation | null | undefined }) {
  if (!evaluation) {
    return <p className="text-sm text-muted-foreground">No evaluation results for this model.</p>
  }
  if (evaluation.state === 'pending' || evaluation.state === 'scoring') {
    return (
      <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 motion-safe:animate-spin" aria-hidden /> Scoring… We are comparing your tuned model with the original.
      </p>
    )
  }
  if (evaluation.state === 'failed') {
    return (
      <Callout tone="destructive" role="alert">
        Evaluation failed{evaluation.error ? `: ${evaluation.error}` : '.'} Your model is still ready to use.
      </Callout>
    )
  }
  const { base_scores: base, tuned_scores: tuned } = evaluation
  if (!base || !tuned) return <p className="text-sm text-muted-foreground">Scores are not available for this model.</p>
  const scale = scoreScale(base, tuned)
  return (
    <div className="flex flex-col gap-5">
      <p className="text-caption text-muted-foreground">
        Scored by an AI judge on <span className="text-metric">{evaluation.n_items}</span> held-out questions (out of {scale}). Higher is better.
      </p>
      <ul className="grid gap-6 border-t pt-5 md:grid-cols-3 md:gap-0 md:divide-x">
        {SCORE_LABELS.filter(([k]) => k in base || k in tuned).map(([k, label]) => (
          <li key={k} className="flex flex-col gap-3 max-md:border-t max-md:pt-5 max-md:first:border-t-0 max-md:first:pt-0 md:px-6 md:first:pl-0 md:last:pr-0">
            <span className="text-eyebrow">{label}</span>
            <div className="flex items-baseline gap-3">
              {tuned[k] !== undefined && <span className="text-metric text-3xl">{formatScore(round1(tuned[k]))}</span>}
              {base[k] !== undefined && tuned[k] !== undefined && <Delta base={base[k]} tuned={tuned[k]} />}
            </div>
            <div className="flex flex-col gap-2">
              {base[k] !== undefined && <Bar label="Original" value={base[k]} scale={scale} tone="base" />}
              {tuned[k] !== undefined && <Bar label="Tuned" value={tuned[k]} scale={scale} tone="tuned" />}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Long answers start collapsed so one verbose reply can't push the comparison off screen. */
function Collapsible({ children, id }: { children: ReactNode; id: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [overflows, setOverflows] = useState(false)
  const [open, setOpen] = useState(false)
  useLayoutEffect(() => {
    const el = ref.current
    if (el) setOverflows(el.scrollHeight > el.clientHeight + 4)
  }, [children])
  return (
    <div className="flex flex-col gap-2">
      <div
        id={id}
        ref={ref}
        className={cn(
          'relative',
          !open && 'max-h-64 overflow-hidden',
          !open && overflows && 'after:pointer-events-none after:absolute after:inset-x-0 after:bottom-0 after:h-16 after:bg-gradient-to-t after:from-card after:to-transparent',
        )}
      >
        {children}
      </div>
      {overflows && (
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((o) => !o)}
          className="inline-flex w-fit items-center gap-1 rounded-sm text-xs font-medium text-primary hover:text-primary/80 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          {open ? 'Show less' : 'Show full answer'}
          <ChevronDown className={cn('size-3.5 transition-transform', open && 'rotate-180')} aria-hidden />
        </button>
      )}
    </div>
  )
}

function Answer({ id, title, text, score, tuned }: { id: string; title: string; text: string | null; score: number | null; tuned?: boolean }) {
  return (
    <div
      className={cn(
        'flex min-w-0 flex-col gap-3 rounded-lg border bg-card p-4',
        tuned && 'border-primary/40 shadow-[inset_0_1px_0_0_var(--color-primary)]',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className={cn('text-eyebrow flex items-center gap-1.5', tuned && 'text-foreground')}>
          <span aria-hidden className={cn('size-1.5 rounded-full', tuned ? 'bg-primary' : 'bg-muted-foreground/50')} />
          {title}
        </span>
        {score !== null && (
          <span
            className={cn(
              'text-metric rounded-md border px-1.5 py-0.5 text-xs',
              tuned ? 'border-primary/30 bg-primary/10 text-foreground' : 'text-muted-foreground',
            )}
          >
            <span className="text-muted-foreground">Score </span>
            {formatScore(round1(score))}
          </span>
        )}
      </div>
      {text ? (
        <Collapsible id={id}>
          <SafeMarkdown className="text-sm leading-relaxed [&>*+*]:mt-2">{text}</SafeMarkdown>
        </Collapsible>
      ) : (
        <p className="text-sm text-muted-foreground">No answer.</p>
      )}
    </div>
  )
}

function Gain({ base, tuned }: { base: number | null; tuned: number | null }) {
  if (base === null || tuned === null) return null
  const d = round1(tuned - base)
  if (d === 0) return <span className="text-metric text-xs text-muted-foreground">No change</span>
  const up = d > 0
  return (
    <span
      className={cn(
        'text-metric inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-xs',
        up ? 'bg-success-muted text-success-muted-foreground' : 'bg-warning-muted text-warning-muted-foreground',
      )}
    >
      {up ? <TrendingUp className="size-3" aria-hidden /> : <TrendingDown className="size-3" aria-hidden />}
      {up ? '+' : '−'}
      {formatScore(Math.abs(d))}
      <span className="sr-only"> points vs original</span>
    </span>
  )
}

export function SamplesList({ evaluation }: { evaluation: Evaluation | null | undefined }) {
  const samples: Sample[] = parseSamples(evaluation?.samples ?? null)
  if (samples.length === 0) return null
  return (
    <ol className="flex flex-col divide-y" aria-label="Sample answers">
      {samples.map((s, i) => (
        <li key={i} className="flex flex-col gap-4 py-6 first:pt-0 last:pb-0">
          <div className="flex items-start gap-3">
            <span className="text-metric mt-0.5 shrink-0 text-xs text-muted-foreground">Q{i + 1}</span>
            <p className="text-card-title min-w-0 flex-1">{s.question}</p>
            <Gain base={s.base_score} tuned={s.tuned_score} />
          </div>
          {s.context && (
            <details className="group rounded-lg border px-4 py-3 text-sm">
              <summary className="cursor-pointer text-eyebrow outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50">Earlier in the conversation</summary>
              <p className="mt-2 whitespace-pre-wrap text-muted-foreground">{s.context}</p>
            </details>
          )}
          {s.reference && (
            <div className="rounded-lg border-l-2 border-primary/60 bg-muted/50 px-4 py-3">
              <p className="text-eyebrow mb-1">Expected answer</p>
              <p className="text-sm text-muted-foreground">{s.reference}</p>
            </div>
          )}
          <div className="grid items-start gap-3 md:grid-cols-2">
            <Answer id={`sample-${i}-base`} title="Original model" text={s.base_answer} score={s.base_score} />
            <Answer id={`sample-${i}-tuned`} title="Your tuned model" text={s.tuned_answer} score={s.tuned_score} tuned />
          </div>
        </li>
      ))}
    </ol>
  )
}
