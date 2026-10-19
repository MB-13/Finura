import { ChevronDown, ChevronRight } from 'lucide-react'
import { useId, useState } from 'react'

import { RecordView } from '@/features/dataset/RecordView'
import type { Pair } from '@/features/style/api'
import { ScoreChips } from '@/features/style/ScoreChips'

/** One generated example in its dataset format, with score chips and an expandable source excerpt. */
export function PairCard({ pair, index }: { pair: Pair; index?: number }) {
  const [open, setOpen] = useState(false)
  const sourceId = useId()
  const Chevron = open ? ChevronDown : ChevronRight
  return (
    <li className="flex flex-col gap-4 rounded-xl border bg-card p-4 shadow-card sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {index !== undefined && <span className="text-eyebrow">Sample {index}</span>}
        <ScoreChips correctness={pair.judge_correctness} style={pair.judge_style} reason={pair.judge_reason} />
      </div>
      <RecordView record={pair.record} />
      {pair.chunk && (
        <div className="flex flex-col gap-2">
          <button
            type="button"
            aria-expanded={open}
            aria-controls={sourceId}
            onClick={() => setOpen((v) => !v)}
            className="inline-flex w-fit max-w-full items-center gap-1 rounded-md text-left text-caption font-medium text-primary outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            <Chevron className="size-3.5 shrink-0" aria-hidden />
            <span className="min-w-0 break-words">Source: {pair.chunk.section_path || 'Untitled section'}</span>
          </button>
          {open && (
            <blockquote id={sourceId} className="border-l-2 border-primary/40 pl-3 text-caption whitespace-pre-wrap text-muted-foreground">
              {pair.chunk.excerpt}
            </blockquote>
          )}
        </div>
      )}
    </li>
  )
}
