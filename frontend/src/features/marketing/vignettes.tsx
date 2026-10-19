import { Check, ChevronDown, Cpu, FileText, Globe2, Pencil, Quote, Send } from 'lucide-react'
import type { ReactNode } from 'react'

import { Callout } from '@/components/Callout'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { ScoreChips } from '@/features/style/ScoreChips'
import type { Metric } from '@/features/training/api'
import { LossChart } from '@/features/training/LossChart'
import { REVIEW_PAIRS } from '@/features/marketing/vignette-data'
import { cn } from '@/lib/utils'

/**
 * Static, decorative miniatures of real DocTune screens for the marketing pages. Built from the same components
 * as the app with fixture data. Callers wrap them in <Decor> so they are hidden from assistive tech and inert.
 */

/** aria-hidden + inert wrapper for decorative product visuals. */
export function Decor({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div aria-hidden inert className={cn('select-none', className)}>
      {children}
    </div>
  )
}

const lossPoints: Metric[] = Array.from({ length: 24 }, (_, i) => ({
  step: i * 12,
  loss: 2.1 * Math.exp(-i / 7) + 0.55 + (i % 3) * 0.03,
  lr: 0.0002,
  at: '2026-01-01T00:00:00Z',
}))

export function PairLine({ q, a, state, scores }: { q: string; a: string; state: 'approved' | 'edited' | 'review'; scores?: [number, number] }) {
  return (
    <div className="flex flex-col gap-1.5 py-3 first:pt-0 last:pb-0">
      <div className="flex items-start justify-between gap-3">
        <div className="text-sm font-medium">{q}</div>
        {state === 'approved' && (
          <span className="flex shrink-0 items-center gap-1 text-caption font-medium text-success-muted-foreground">
            <Check className="size-3.5" /> Approved
          </span>
        )}
        {state === 'edited' && (
          <span className="flex shrink-0 items-center gap-1 text-caption font-medium text-info-muted-foreground">
            <Pencil className="size-3.5" /> Edited
          </span>
        )}
        {state === 'review' && <Badge variant="outline">To review</Badge>}
      </div>
      <div className="text-sm text-muted-foreground">{a}</div>
      {scores && <ScoreChips correctness={scores[0]} style={scores[1]} />}
    </div>
  )
}

export function DropzoneVignette() {
  const files = [
    ['Returns-policy.pdf', '1.2 MB', 'Ready'],
    ['Help-centre-export.docx', '860 KB', 'Ready'],
    ['Shipping-FAQ.pdf', '2.4 MB', 'Reading…'],
  ]
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col items-center gap-1 rounded-xl border border-dashed py-6 text-center">
        <div className="text-sm font-medium">Drop files here</div>
        <div className="text-caption text-muted-foreground">PDF, DOCX, TXT or Markdown · up to 20 MB each</div>
      </div>
      <ul className="flex flex-col divide-y">
        {files.map(([name, size, state]) => (
          <li key={name} className="flex items-center gap-3 py-2.5 text-sm first:pt-0 last:pb-0">
            <FileText className="size-4 shrink-0 text-muted-foreground" />
            <span className="min-w-0 flex-1 truncate font-medium">{name}</span>
            <span className="text-caption text-muted-foreground tabular-nums">{size}</span>
            <span
              className={cn(
                'w-16 text-right text-caption font-medium',
                state === 'Ready' ? 'text-success-muted-foreground' : 'text-info-muted-foreground',
              )}
            >
              {state}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function StyleVignette() {
  const row = (label: string, options: string[], active: number) => (
    <div className="flex flex-col gap-1.5">
      <div className="text-eyebrow">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o, i) => (
          <span
            key={o}
            className={cn(
              'rounded-md border px-2.5 py-1 text-caption',
              i === active ? 'border-primary/40 bg-accent font-medium text-accent-foreground' : 'text-muted-foreground',
            )}
          >
            {o}
          </span>
        ))}
      </div>
    </div>
  )
  return (
    <div className="flex flex-col gap-4">
      {row('Tone', ['Friendly', 'Formal', 'Playful'], 0)}
      {row('Length', ['Short', 'Medium', 'Detailed'], 0)}
      <div className="flex flex-col gap-1.5 border-t pt-4">
        <div className="text-eyebrow">Example answer</div>
        <p className="flex gap-2 text-sm text-muted-foreground">
          <Quote className="mt-0.5 size-3.5 shrink-0" />
          Sure thing! Pop into Settings, hit Reset password, and we will email you a link.
        </p>
      </div>
    </div>
  )
}

export function ReviewVignette() {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <div className="text-eyebrow">Dataset review</div>
        <div className="text-caption text-muted-foreground tabular-nums">
          <span className="text-metric text-foreground">846</span> approved · <span className="text-metric text-foreground">94</span> to review
        </div>
      </div>
      <div className="flex flex-col divide-y">
        {REVIEW_PAIRS.slice(0, 3).map((p) => (
          <PairLine key={p.q} {...p} />
        ))}
      </div>
    </div>
  )
}

export function TrainVignette() {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end justify-between gap-3">
        <span className="text-metric text-4xl">62%</span>
        <span className="text-caption text-muted-foreground tabular-nums">Step 186 of 300 · about 20 min left</span>
      </div>
      <Progress value={62} aria-label="Example progress" className="h-2.5" />
      <LossChart points={lossPoints} maxSteps={300} />
    </div>
  )
}

export function ChatVignette() {
  return (
    <div className="flex flex-col gap-3">
      <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-secondary px-3.5 py-2 text-sm">How long do refunds take?</div>
      <div className="flex flex-col gap-2 text-sm">
        <p>Refunds land in 3 to 5 working days after we receive the item. You will get an email when it is on its way.</p>
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="outline">
            <FileText /> Returns-policy.pdf · p.2
          </Badge>
          <Badge variant="outline">
            <FileText /> Shipping-FAQ.pdf · p.1
          </Badge>
        </div>
      </div>
      <div className="mt-1 flex items-center gap-2 rounded-xl border px-3 py-2 text-sm text-muted-foreground">
        <span className="flex-1">Ask your model…</span>
        <Send className="size-4" />
      </div>
    </div>
  )
}

/* ---- bento vignettes ---- */

export function ScoresTile() {
  return (
    <div className="flex flex-col divide-y">
      {REVIEW_PAIRS.slice(0, 2).map((p) => (
        <PairLine key={p.q} {...p} />
      ))}
    </div>
  )
}

export function PausedTile() {
  return (
    <Callout tone="warning" title="Paused · progress saved (62%)">
      The free GPU session ended. Open the notebook again to continue from step 186.
    </Callout>
  )
}

export function KaggleTile() {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <div className="text-eyebrow flex items-center gap-1.5">
          <Cpu className="size-3.5" /> GPU hours this week
        </div>
        <span className="text-metric text-sm">
          9<span className="text-muted-foreground"> / 30 h</span>
        </span>
      </div>
      <Progress value={30} aria-label="Example GPU hours" />
      <p className="text-caption text-muted-foreground">Your own free account. Training uses about 1 hour.</p>
    </div>
  )
}

export function PresetTile() {
  const presets = [
    ['Fast', 'about 30 min'],
    ['Balanced', 'about 1 hour'],
    ['Thorough', 'about 2 hours'],
  ]
  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-3 gap-1.5">
        {presets.map(([n, t], i) => (
          <div key={n} className={cn('rounded-lg border px-2.5 py-2', i === 1 && 'border-primary/40 bg-accent')}>
            <div className={cn('text-caption font-medium', i === 1 && 'text-accent-foreground')}>{n}</div>
            <div className="text-[0.6875rem] leading-4 text-muted-foreground">{t}</div>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-1 text-caption text-muted-foreground">
        Advanced <ChevronDown className="size-3.5" />
      </div>
    </div>
  )
}

export function SourcesTile() {
  return (
    <div className="flex flex-col gap-2 text-sm">
      <p>Refunds land in 3 to 5 working days.</p>
      <div className="flex items-center gap-1.5 text-caption font-medium text-muted-foreground">
        <Globe2 className="size-3.5" /> Sources (2) <ChevronDown className="size-3.5" />
      </div>
      <div className="border-l-2 pl-3 text-caption text-muted-foreground">
        <span className="font-medium text-foreground">Returns-policy.pdf</span> · “Refunds are issued within 3 to 5 working days…”
      </div>
    </div>
  )
}

export function DownloadTile() {
  const rows = [
    ['LoRA adapter (zip)', '84 MB'],
    ['Merged model', '8.1 GB'],
    ['GGUF for Ollama', '2.6 GB'],
  ]
  return (
    <ul className="flex flex-col divide-y">
      {rows.map(([n, s]) => (
        <li key={n} className="flex items-center justify-between gap-3 py-2 text-sm first:pt-0 last:pb-0">
          <span className="font-medium">{n}</span>
          <Badge variant="outline" className="text-metric">
            {s}
          </Badge>
        </li>
      ))}
    </ul>
  )
}
