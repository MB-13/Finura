import { Check } from 'lucide-react'
import { useId } from 'react'

import { ErrorState } from '@/components/ErrorState'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import type { DatasetFormat, FormatInfo } from '@/features/dataset/record-utils'
import { RecordView } from '@/features/dataset/RecordView'
import { useDatasetFormats } from '@/features/style/api'
import { cn } from '@/lib/utils'

type Props = { value: DatasetFormat; onChange: (format: DatasetFormat) => void; disabled?: boolean }

/** The shape of every training example. Chosen before the preview; it drives generation, review and training. */
export function DatasetFormatPicker({ value, onChange, disabled = false }: Props) {
  const formats = useDatasetFormats()
  const sampleId = useId()

  if (formats.isPending) {
    return (
      <div aria-busy="true" aria-label="Loading dataset formats" className="grid gap-3 lg:grid-cols-3">
        <Skeleton className="h-28 rounded-xl" />
        <Skeleton className="h-28 rounded-xl" />
        <Skeleton className="h-28 rounded-xl" />
      </div>
    )
  }
  if (formats.isError) return <ErrorState message={formats.error.message} onRetry={() => formats.refetch()} />

  const selected = formats.data.find((f) => f.key === value) ?? formats.data[0]
  return (
    <div className="flex flex-col gap-4">
      <fieldset className="grid gap-3 lg:grid-cols-3" disabled={disabled}>
        <legend className="sr-only">Dataset format</legend>
        {formats.data.map((f) => (
          <FormatCard key={f.key} format={f} selected={f.key === selected?.key} onSelect={() => onChange(f.key)} describedBy={sampleId} />
        ))}
      </fieldset>
      {selected && (
        <div id={sampleId} className="flex flex-col gap-3 rounded-xl border border-dashed bg-muted/30 p-4">
          <span className="text-eyebrow">What one {selected.name.toLowerCase()} example looks like</span>
          <RecordView record={selected.sample} className="text-sm" />
        </div>
      )}
    </div>
  )
}

function FormatCard({ format, selected, onSelect, describedBy }: { format: FormatInfo; selected: boolean; onSelect: () => void; describedBy: string }) {
  const cost = format.relative_cost
  return (
    <label
      className={cn(
        'relative flex cursor-pointer flex-col gap-1.5 rounded-xl border bg-card p-4 pr-11 text-sm transition-colors hover:border-primary/50 has-focus-visible:ring-[3px] has-focus-visible:ring-ring/50 has-disabled:cursor-not-allowed has-disabled:opacity-60',
        selected && 'border-primary bg-accent/40 ring-1 ring-primary hover:border-primary',
      )}
    >
      <input
        type="radio"
        name="dataset-format"
        value={format.key}
        className="sr-only"
        checked={selected}
        onChange={onSelect}
        aria-describedby={selected ? describedBy : undefined}
      />
      <span
        aria-hidden
        className={cn(
          'absolute top-4 right-4 flex size-5 items-center justify-center rounded-full border',
          selected ? 'border-primary bg-primary text-primary-foreground' : 'bg-background',
        )}
      >
        {selected && <Check className="size-3" />}
      </span>
      <span className="flex flex-wrap items-center gap-2">
        <span className="text-card-title">{format.name}</span>
        {cost > 1 && <Badge variant="outline">~{Number(cost.toFixed(1))}× quota</Badge>}
      </span>
      <span className="text-foreground/85">{format.description}</span>
      <span className="text-caption text-muted-foreground">{format.best_for}</span>
    </label>
  )
}
