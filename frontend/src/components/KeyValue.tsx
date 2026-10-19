import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type KeyValueItem = { label: string; value: ReactNode; /** Render the value in the mono font (ids, tokens, paths). */ mono?: boolean }

/** Definition list of label/value pairs: stacked on mobile, two columns from `sm`. */
export function KeyValue({ items, className }: { items: KeyValueItem[]; className?: string }) {
  return (
    <dl className={cn('divide-y text-sm', className)}>
      {items.map((item) => (
        <div key={item.label} className="flex flex-col gap-0.5 py-2.5 first:pt-0 last:pb-0 sm:flex-row sm:gap-6">
          <dt className="shrink-0 text-muted-foreground sm:w-40">{item.label}</dt>
          <dd className={cn('min-w-0 break-words tabular-nums', item.mono && 'font-mono text-[0.8125rem]')}>{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}
