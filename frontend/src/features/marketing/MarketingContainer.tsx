import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/** Page width + gutters for public pages (the marketing layout itself is full-bleed so sections can have bands). */
export function MarketingContainer({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('mx-auto w-full max-w-6xl px-4 sm:px-6', className)}>{children}</div>
}
