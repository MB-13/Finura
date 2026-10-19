import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

type Props = {
  /** Shown in the faux title bar (mono, muted). Decorative text only. */
  title?: string
  children: ReactNode
  /** Fade the bottom edge into the page background, so the window looks cropped by the fold. */
  fade?: boolean
  className?: string
  /** Class for the content area (e.g. to set a fixed height or padding). */
  bodyClassName?: string
}

/** Framed app-window mock for hero / product visuals: three dots, title, border, shadow, optional bottom fade. */
export function AppFrame({ title, children, fade = false, className, bodyClassName }: Props) {
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-2xl border bg-card text-card-foreground shadow-lg',
        className,
      )}
    >
      <div className="flex h-10 items-center gap-3 border-b bg-muted/40 px-4">
        <div className="flex gap-1.5" aria-hidden>
          <span className="size-2.5 rounded-full bg-muted-foreground/25" />
          <span className="size-2.5 rounded-full bg-muted-foreground/25" />
          <span className="size-2.5 rounded-full bg-muted-foreground/25" />
        </div>
        {title && <div className="min-w-0 flex-1 truncate text-center text-eyebrow normal-case tracking-normal sm:pr-12">{title}</div>}
      </div>
      <div className={cn('relative', bodyClassName)}>{children}</div>
      {fade && (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 h-28 bg-gradient-to-b from-transparent to-background"
        />
      )}
    </div>
  )
}
