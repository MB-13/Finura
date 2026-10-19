import { Check } from 'lucide-react'

import { ErrorState } from '@/components/ErrorState'
import { Skeleton } from '@/components/ui/skeleton'
import { useStyleTemplates, type StyleTemplate } from '@/features/style/api'
import { cn } from '@/lib/utils'

type Props = { selectedKey: string | null | undefined; onPick: (template: StyleTemplate) => void; disabled?: boolean }

export function TemplatePicker({ selectedKey, onPick, disabled }: Props) {
  const templates = useStyleTemplates()

  if (templates.isPending) {
    return (
      <div aria-busy="true" aria-label="Loading templates" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
    )
  }
  if (templates.isError) return <ErrorState title="Couldn't load templates" message={templates.error.message} onRetry={() => templates.refetch()} />
  if (templates.data.length === 0) return <p className="text-sm text-muted-foreground">No templates available. Describe your style below.</p>

  return (
    <div role="group" aria-label="Style templates" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {templates.data.map((t) => {
        const selected = selectedKey === t.key
        return (
          <button
            key={t.key}
            type="button"
            disabled={disabled}
            aria-pressed={selected}
            onClick={() => onPick(t)}
            className={cn(
              'relative flex flex-col gap-1 rounded-xl border bg-card p-4 pr-10 text-left shadow-xs transition-[border-color,box-shadow,background-color] outline-none',
              'hover:border-primary/50 hover:bg-accent/40 focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50',
              selected && 'border-primary bg-accent ring-1 ring-primary hover:bg-accent',
            )}
          >
            <span className="text-card-title">{t.name}</span>
            <span className="text-caption text-muted-foreground">{t.description}</span>
            <span
              aria-hidden
              className={cn(
                'absolute top-3.5 right-3.5 flex size-5 items-center justify-center rounded-full border transition-colors',
                selected ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-card',
              )}
            >
              {selected && <Check className="size-3" strokeWidth={3} />}
            </span>
          </button>
        )
      })}
    </div>
  )
}
