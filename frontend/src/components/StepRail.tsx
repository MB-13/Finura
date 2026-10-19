import { Check } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/** `done` = finished, `active` = the step in progress, `todo` = not reached yet. */
export type StepState = 'done' | 'active' | 'todo'

const size = {
  md: 'size-7 text-xs',
  sm: 'size-5 text-[0.6875rem]',
} as const

/**
 * Round step marker, shared by every stepper: check when done, highlighted ring when active
 * (pulsing dot with `pulse`, the number otherwise), number when waiting. Decorative: convey state in text next to it.
 */
export function StepMarker({
  state,
  n,
  pulse = false,
  size: s = 'md',
  className,
}: {
  state: StepState
  n?: number
  pulse?: boolean
  size?: keyof typeof size
  className?: string
}) {
  const base = 'relative z-10 flex shrink-0 items-center justify-center rounded-full font-semibold tabular-nums'
  const iconSize = s === 'md' ? 'size-4' : 'size-3'
  if (state === 'done')
    return (
      <span aria-hidden className={cn(base, size[s], 'bg-primary text-primary-foreground', className)}>
        <Check className={iconSize} strokeWidth={3} />
      </span>
    )
  if (state === 'active')
    return (
      <span aria-hidden className={cn(base, size[s], 'border-2 border-primary bg-accent text-accent-foreground', className)}>
        {pulse ? (
          <span className="relative flex size-2.5">
            <span className="absolute inline-flex size-full rounded-full bg-primary opacity-60 motion-safe:animate-ping" />
            <span className="relative inline-flex size-2.5 rounded-full bg-primary" />
          </span>
        ) : (
          n
        )}
      </span>
    )
  return (
    <span aria-hidden className={cn(base, size[s], 'border bg-background font-medium text-muted-foreground', className)}>
      {n}
    </span>
  )
}

/** One row of a vertical stepper: marker column with a connecting line, then the content. */
export function StepItem({
  state,
  n,
  last,
  pulse = true,
  children,
  ...rest
}: {
  state: StepState
  n?: number
  last: boolean
  /** Pulse the active marker (live progress). Pass false to show the number instead. */
  pulse?: boolean
  children: ReactNode
  'aria-current'?: 'step'
}) {
  return (
    <li {...rest} className={cn('relative flex gap-4', !last && 'pb-6')}>
      {!last && <span aria-hidden className={cn('absolute top-8 bottom-1 left-[13px] w-0.5 rounded-full', state === 'done' ? 'bg-primary' : 'bg-border')} />}
      <StepMarker state={state} n={n} pulse={pulse} />
      <div className="min-w-0 flex-1 pt-0.5">{children}</div>
    </li>
  )
}
