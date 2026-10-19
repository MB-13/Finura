import { Check, Clock } from 'lucide-react'

import type { Preset, PresetKey } from '@/features/training/api'
import { formatDuration } from '@/lib/format'
import { cn } from '@/lib/utils'

export function PresetPicker({
  presets,
  value,
  onChange,
  minutes,
}: {
  presets: Preset[]
  value: PresetKey
  onChange: (key: PresetKey) => void
  /** Estimated minutes per preset key for the chosen model, when known. */
  minutes?: Record<string, number> | null
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-card-title">How thorough should training be?</legend>
      <div className="grid gap-3 sm:grid-cols-3">
        {presets.map((p) => {
          const key = p.key as PresetKey
          const mins = minutes?.[p.key]
          const selected = value === key
          return (
            <label
              key={p.key}
              className={cn(
                'relative flex cursor-pointer flex-col gap-1 rounded-xl border bg-card p-3.5 pr-10 text-sm transition-colors hover:border-primary/50 has-focus-visible:ring-[3px] has-focus-visible:ring-ring/50',
                selected && 'border-primary bg-accent/40 ring-1 ring-primary hover:border-primary',
              )}
            >
              <input type="radio" name="preset" className="sr-only" checked={selected} onChange={() => onChange(key)} aria-label={p.name} />
              <span
                aria-hidden
                className={cn(
                  'absolute top-3.5 right-3.5 flex size-5 items-center justify-center rounded-full border',
                  selected ? 'border-primary bg-primary text-primary-foreground' : 'bg-background',
                )}
              >
                {selected && <Check className="size-3" />}
              </span>
              <span className="text-card-title">{p.name}</span>
              <span className="text-caption text-muted-foreground">{p.description}</span>
              {mins !== undefined && (
                <span className="mt-1 flex items-center gap-1 text-caption font-medium">
                  <Clock className="size-3.5 text-muted-foreground" aria-hidden /> About {formatDuration(mins, 0).replace('about ', '')}
                </span>
              )}
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}
