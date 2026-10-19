import { ArrowLeftRight, ChevronDown, ChevronRight, Pencil, RotateCcw, Trash2 } from 'lucide-react'
import { useId, useState, type Ref } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { Pair } from '@/features/dataset/api'
import { isDropped, ROW_GRID } from '@/features/dataset/pair-utils'
import { LABELS, recordProblem, sameRecord, trimRecord, type PairRecord } from '@/features/dataset/record-utils'
import { RecordEditor } from '@/features/dataset/RecordEditor'
import { RecordView } from '@/features/dataset/RecordView'
import { ScoreChips } from '@/features/style/ScoreChips'
import { ApiError } from '@/lib/api/client'
import { cn } from '@/lib/utils'

type Props = {
  pair: Pair
  rowIndex: number
  readOnly: boolean
  selected: boolean
  focused: boolean
  expanded: boolean
  saving: boolean
  onSelect: (selected: boolean) => void
  onToggleExpand: () => void
  onToggleKept: () => void
  onToggleSplit: () => void
  onSave: (record: PairRecord) => Promise<void>
  rowRef?: Ref<HTMLDivElement>
}

export function PairRow({
  pair,
  rowIndex,
  readOnly,
  selected,
  focused,
  expanded,
  saving,
  onSelect,
  onToggleExpand,
  onToggleKept,
  onToggleSplit,
  onSave,
  rowRef,
}: Props) {
  const dropped = isDropped(pair)
  const Chevron = expanded ? ChevronDown : ChevronRight
  const detailsId = useId()

  const mobileLabel = 'text-eyebrow md:hidden'
  const labels = LABELS[pair.dataset_format]
  const extra = pairExtra(pair.record)
  return (
    <div
      ref={rowRef}
      role="row"
      aria-rowindex={rowIndex + 2}
      aria-selected={selected}
      data-row-index={rowIndex}
      tabIndex={focused ? 0 : -1}
      className={cn(
        'relative flex flex-wrap items-start gap-x-2 gap-y-3 rounded-xl border bg-card p-4 text-sm shadow-card transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:ring-inset',
        'md:rounded-none md:border-0 md:border-b md:border-border/60 md:bg-transparent md:px-4 md:py-2.5 md:text-[0.8125rem] md:leading-5 md:shadow-none md:hover:bg-muted/40',
        ROW_GRID,
        dropped && 'bg-muted/50 md:bg-muted/40',
        selected && 'border-primary/40 bg-accent/60 md:bg-accent/60 md:hover:bg-accent/70',
      )}
    >
      <div role="cell" className="absolute top-4 right-4 flex items-center md:static md:pt-0.5">
        {!readOnly && (
          <input
            type="checkbox"
            className="size-4 accent-primary"
            aria-label={`Select pair ${rowIndex + 1}`}
            checked={selected}
            onChange={(e) => onSelect(e.target.checked)}
          />
        )}
      </div>
      <div role="cell" className={cn('flex min-w-0 basis-full flex-col gap-0.5 pr-8 md:basis-auto md:pr-0', dropped && 'opacity-60')}>
        <span className={mobileLabel}>{labels.input}</span>
        <p className={cn('font-medium', expanded ? 'whitespace-pre-wrap' : 'line-clamp-2')}>{pair.question}</p>
        {extra && <span className="text-caption text-muted-foreground">{extra}</span>}
      </div>
      <div role="cell" className={cn('flex min-w-0 basis-full flex-col gap-0.5 md:basis-auto', dropped && 'opacity-60')}>
        <span className={mobileLabel}>{labels.output}</span>
        <p className={cn('text-foreground/80', expanded ? 'whitespace-pre-wrap' : 'line-clamp-2')}>{pair.answer}</p>
      </div>
      <div role="cell" className="flex items-center gap-1">
        <span className={cn('inline-flex items-center gap-1.5 font-mono text-xs', pair.split === 'eval' ? 'text-info-muted-foreground' : 'text-muted-foreground')}>
          <span aria-hidden className={cn('size-1.5 rounded-full', pair.split === 'eval' ? 'bg-info' : 'bg-muted-foreground/50')} />
          {pair.split}
        </span>
      </div>
      <div role="cell">
        <ScoreChips correctness={pair.judge_correctness} style={pair.judge_style} reason={pair.judge_reason} />
      </div>
      <div role="cell" className="flex flex-col items-start gap-1 text-caption text-muted-foreground">
        <span>{pair.origin === 'user_added' ? 'Added by you' : 'Generated'}</span>
        {pair.edited && <span className="font-medium text-foreground">Edited</span>}
        {dropped && (
          <Badge className="bg-destructive-muted text-destructive-muted-foreground">
            Dropped{pair.dropped_reason ? `: ${pair.dropped_reason.replace(/_/g, ' ')}` : ''}
          </Badge>
        )}
      </div>
      <div role="cell" className="min-w-0 basis-full truncate text-caption text-muted-foreground md:basis-auto" title={pair.chunk?.excerpt}>
        <span className="md:hidden">Source: </span>
        {pair.chunk?.section_path || (pair.chunk ? 'Untitled section' : '—')}
      </div>
      <div role="cell" className="flex basis-full flex-wrap items-center gap-1.5 md:basis-auto md:flex-nowrap md:gap-1">
        {!readOnly && (
          <>
            {dropped ? (
              <Button variant="outline" size="xs" aria-label={`Restore pair ${rowIndex + 1}`} title="Restore (r)" onClick={onToggleKept}>
                <RotateCcw aria-hidden /> <span className="md:sr-only">Restore</span>
              </Button>
            ) : (
              <Button variant="outline" size="xs" aria-label={`Drop pair ${rowIndex + 1}`} title="Drop (d)" onClick={onToggleKept}>
                <Trash2 aria-hidden /> <span className="md:sr-only">Drop</span>
              </Button>
            )}
            {pair.split !== 'unassigned' && (
              <Button
                variant="outline"
                size="xs"
                aria-label={`Move pair ${rowIndex + 1} to ${pair.split === 'train' ? 'eval' : 'train'}`}
                title={`Move to ${pair.split === 'train' ? 'eval' : 'train'}`}
                onClick={onToggleSplit}
              >
                <ArrowLeftRight aria-hidden /> <span className="md:sr-only">To {pair.split === 'train' ? 'eval' : 'train'}</span>
              </Button>
            )}
          </>
        )}
        <Button
          variant="ghost"
          size="xs"
          aria-expanded={expanded}
          aria-controls={detailsId}
          aria-label={`${expanded ? 'Close' : readOnly ? 'View' : 'Edit'} pair ${rowIndex + 1}`}
          title={readOnly ? 'View (e)' : 'Edit (e)'}
          onClick={onToggleExpand}
        >
          {readOnly ? <Chevron aria-hidden /> : expanded ? <ChevronDown aria-hidden /> : <Pencil aria-hidden />} <span className="md:sr-only">{readOnly ? 'View' : 'Edit'}</span>
        </Button>
      </div>

      {expanded && (
        <div id={detailsId} role="cell" className="flex basis-full flex-col gap-3 border-t border-border/60 pt-4 md:col-span-full">
          {readOnly ? (
            <>
              <RecordView record={pair.record} />
              {pair.judge_reason && <p className="text-muted-foreground">Judge: {pair.judge_reason}</p>}
              {pair.chunk && <p className="text-caption text-muted-foreground">Source: {pair.chunk.excerpt}</p>}
            </>
          ) : (
            <EditForm pair={pair} rowIndex={rowIndex} saving={saving} onSave={onSave} onCancel={onToggleExpand} />
          )}
        </div>
      )}
    </div>
  )
}

/** What the summary columns can't show: the rest of a conversation, or an instruction's input. */
function pairExtra(record: PairRecord): string | null {
  if (record.format === 'multi_turn' && record.messages.length > 2) {
    const followUps = record.messages.length / 2 - 1
    return `+ ${followUps} follow-up${followUps === 1 ? '' : 's'}`
  }
  if (record.format === 'instruction' && record.input) return 'With input text'
  return null
}

function EditForm({
  pair,
  rowIndex,
  saving,
  onSave,
  onCancel,
}: {
  pair: Pair
  rowIndex: number
  saving: boolean
  onSave: Props['onSave']
  onCancel: () => void
}) {
  const [record, setRecord] = useState<PairRecord>(pair.record)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})
  const dirty = !sameRecord(record, pair.record)

  async function save() {
    const problem = recordProblem(record)
    if (problem) return setError(problem)
    setError(null)
    setFieldErrors({})
    try {
      await onSave(trimRecord(record))
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length > 0) setFieldErrors(err.fieldErrors)
      else setError(err instanceof Error ? err.message : 'Could not save')
    }
  }

  return (
    <>
      <RecordEditor record={record} onChange={setRecord} labelSuffix={` for ${LABELS[pair.dataset_format].example} ${rowIndex + 1}`} errors={fieldErrors} />
      {error && (
        <p role="alert" className="text-sm text-destructive-muted-foreground">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button size="sm" disabled={saving || !dirty} onClick={save}>
          {saving ? 'Saving…' : 'Save changes'}
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </>
  )
}
