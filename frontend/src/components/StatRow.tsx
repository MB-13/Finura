import { Stat, type StatProps } from '@/components/Stat'
import { cn } from '@/lib/utils'

type Props = {
  items: Omit<StatProps, 'variant' | 'className'>[]
  className?: string
}

/**
 * One row of stats separated by vertical hairlines, inside a single surface (put it in a card or on the page).
 * 2 columns on mobile (with horizontal hairlines between rows), one row from `sm`. Use 2 to 4 items.
 */
export function StatRow({ items, className }: Props) {
  return (
    <div className={cn('grid grid-cols-2 gap-y-4 sm:flex sm:gap-y-0', className)}>
      {items.map((item, i) => (
        <div
          key={item.label}
          className={cn(
            'min-w-0 sm:flex-1 sm:px-5 sm:first:pl-0 sm:last:pr-0',
            // mobile: right column gets a vertical rule, later rows a top rule
            i % 2 === 1 && 'border-l pl-4 sm:pl-5',
            i >= 2 && 'max-sm:border-t max-sm:pt-4',
            i % 2 === 0 && 'max-sm:pr-4',
            i > 0 && 'sm:border-l',
          )}
        >
          <Stat variant="inline" {...item} />
        </div>
      ))}
    </div>
  )
}
