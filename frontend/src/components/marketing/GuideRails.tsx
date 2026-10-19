import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/**
 * Marketing only. Wraps page sections in a centred column with thin vertical guide rails at its edges.
 * Use the same `className` width (default `max-w-6xl`) on `GuideJoint` so the "+" marks sit on the rails.
 */
export function GuideRails({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('relative mx-auto w-full max-w-6xl border-x border-border/70', className)}>{children}</div>
}

/**
 * Marketing only. Full-bleed horizontal hairline with "+" crosshair marks where it crosses the rails.
 * Place between sections, as a sibling OUTSIDE `GuideRails` (or `-mx-px`-aligned inside); decorative.
 */
export function GuideJoint({ className, railsClassName }: { className?: string; railsClassName?: string }) {
  return (
    <div aria-hidden className={cn('relative h-px w-full bg-border/70', className)}>
      <div className={cn('relative mx-auto h-0 w-full max-w-6xl', railsClassName)}>
        <span className="guide-plus absolute top-0 left-0 -translate-x-1/2 -translate-y-1/2" />
        <span className="guide-plus absolute top-0 right-0 translate-x-1/2 -translate-y-1/2" />
      </div>
    </div>
  )
}
