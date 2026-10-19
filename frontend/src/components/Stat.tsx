import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type StatProps = {
  label: string
  value: ReactNode
  /** Small secondary line, e.g. "of 2,000" or "+12 today". */
  hint?: ReactNode
  icon?: LucideIcon
  /**
   * `tile` (default): bordered card-like tile. `inline`: no border, background or padding; use inside a surface,
   * ideally via `StatRow`, so stats are separated by hairlines instead of nested boxes.
   */
  variant?: 'tile' | 'inline'
  className?: string
}

/** Metric: mono label, big tabular mono number, optional hint. */
export function Stat({ label, value, hint, icon: Icon, variant = 'tile', className }: StatProps) {
  return (
    <div
      className={cn(
        'flex min-w-0 flex-col gap-1',
        variant === 'tile' && 'rounded-xl border bg-card p-4 shadow-card',
        className,
      )}
    >
      <div className="flex items-center gap-1.5 text-eyebrow">
        {Icon && <Icon className="size-3.5" aria-hidden />}
        {label}
      </div>
      <div className="min-w-0 text-metric text-xl break-words sm:text-2xl">{value}</div>
      {hint && <div className="text-caption text-muted-foreground">{hint}</div>}
    </div>
  )
}
