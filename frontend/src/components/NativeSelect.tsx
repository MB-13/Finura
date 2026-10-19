import { ChevronDown } from 'lucide-react'
import type { ComponentProps } from 'react'

import { cn } from '@/lib/utils'

/** Styled native `<select>`: accessible and keyboard friendly without extra dependencies. The chevron follows the theme. */
export function NativeSelect({ className, ...props }: ComponentProps<'select'>) {
  return (
    <span className="relative block w-full">
      <select
        className={cn(
          'h-9 w-full appearance-none rounded-md border border-input bg-card py-1 pr-9 pl-3 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:bg-input/30 dark:[&>option]:bg-popover',
          className,
        )}
        {...props}
      />
      <ChevronDown aria-hidden className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted-foreground" />
    </span>
  )
}
