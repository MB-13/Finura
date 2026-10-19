import { Check, CheckCircle2, Clock, HelpCircle, MessageSquare, MessageSquareOff } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { MODE_LABEL } from '@/features/training/model-copy'
import type { BaseModel } from '@/features/training/api'
import { cn } from '@/lib/utils'

const PRESET_LABEL: Record<string, string> = { quick: 'Quick', balanced: 'Balanced', thorough: 'Thorough' }

export function ModelCard({ model, selected, onSelect }: { model: BaseModel; selected: boolean; onSelect: () => void }) {
  return (
    <label
      className={cn(
        'relative flex cursor-pointer flex-col gap-2 rounded-xl border bg-card p-4 pr-12 text-sm transition-colors hover:border-primary/50 has-focus-visible:ring-[3px] has-focus-visible:ring-ring/50',
        selected && 'border-primary bg-accent/40 ring-1 ring-primary hover:border-primary',
      )}
    >
      <input type="radio" name="base-model" className="sr-only" checked={selected} onChange={onSelect} aria-label={model.display_name} />
      <span
        aria-hidden
        className={cn(
          'absolute top-4 right-4 flex size-5 items-center justify-center rounded-full border',
          selected ? 'border-primary bg-primary text-primary-foreground' : 'bg-background',
        )}
      >
        {selected && <Check className="size-3" />}
      </span>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-card-title">{model.display_name}</span>
        {model.recommended && <Badge>Recommended</Badge>}
        {model.fits_t4 === 'yes' && (
          <Badge variant="success">
            <CheckCircle2 aria-hidden /> Fits free T4
          </Badge>
        )}
        {model.fits_t4 === 'unconfirmed' && (
          <Badge variant="outline">
            <HelpCircle aria-hidden /> Not tested on T4
          </Badge>
        )}
        {model.playground_supported ? (
          <Badge variant="success">
            <MessageSquare aria-hidden /> Chat here
          </Badge>
        ) : (
          <Badge variant="outline">
            <MessageSquareOff aria-hidden /> No chat here
          </Badge>
        )}
      </div>
      <p className="text-caption text-muted-foreground">
        {model.params_b} B parameters · {model.license} · {MODE_LABEL[model.train_mode]}
      </p>
      {model.note && <p className="text-foreground/85">{model.note}</p>}
      <p className="flex items-center gap-1.5 text-caption text-muted-foreground">
        <Clock className="size-3.5 shrink-0" aria-hidden />
        <span>
          Estimated time:{' '}
          {Object.entries(model.est_minutes)
            .map(([k, v]) => `${PRESET_LABEL[k] ?? k} ~${v} min`)
            .join(' · ')}
        </span>
      </p>
    </label>
  )
}
