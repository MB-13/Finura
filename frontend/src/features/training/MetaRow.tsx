import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type MetaItem = { label: string; value: ReactNode }

/**
 * Compact meta strip for progress screens (provider, GPU, heartbeat, checkpoint ...): eyebrow label over a value,
 * items split by hairlines from `sm`, a two-column grid on mobile. Lives inside one surface, so it adds no box.
 */
export function MetaRow({ items, className, ...rest }: { items: MetaItem[]; className?: string } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div {...rest} className={cn('grid grid-cols-2 gap-x-4 gap-y-3 sm:flex sm:flex-wrap sm:divide-x', className)}>
      {items.map((item) => (
        <div key={item.label} className="flex min-w-0 flex-col gap-1 sm:px-6 sm:first:pl-0 sm:last:pr-0">
          <span className="text-eyebrow">{item.label}</span>
          <span className="min-w-0 text-[0.8125rem] leading-5 break-words tabular-nums">{item.value}</span>
        </div>
      ))}
    </div>
  )
}
