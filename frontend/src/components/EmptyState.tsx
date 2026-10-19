import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

type Props = {
  icon: LucideIcon
  title: string
  description?: string
  /** Primary call to action (a Button). `children` works too. */
  action?: ReactNode
  children?: ReactNode
  className?: string
}

export function EmptyState({ icon: Icon, title, description, action, children, className }: Props) {
  return (
    <div
      className={cn(
        'flex flex-col items-center gap-3 rounded-xl border border-dashed bg-card/50 px-6 py-12 text-center',
        className,
      )}
    >
      <div className="flex size-11 items-center justify-center rounded-full bg-accent text-accent-foreground">
        <Icon className="size-5" aria-hidden />
      </div>
      <div className="flex flex-col gap-1">
        <div className="text-card-title">{title}</div>
        {description && <p className="mx-auto max-w-sm text-sm text-muted-foreground">{description}</p>}
      </div>
      {(action || children) && <div className="mt-1 flex flex-wrap items-center justify-center gap-2">{action}{children}</div>}
    </div>
  )
}
