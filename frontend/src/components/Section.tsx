import { useId, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

type Props = {
  title: ReactNode
  description?: ReactNode
  /** Right-aligned controls in the section header (stacked layout only). */
  actions?: ReactNode
  /** Heading level to render (default h2). Use h3 inside a Section. */
  as?: 'h2' | 'h3'
  /** `stacked` (default): header above content. `side`: title on the left, content on the right from `lg`. */
  layout?: 'stacked' | 'side'
  /** Tint the title as destructive (danger zone). */
  danger?: boolean
  children: ReactNode
  className?: string
}

/** A titled block of page content, exposed as a named region. Stack Sections with `flex flex-col gap-8`. */
export function Section({
  title,
  description,
  actions,
  as: Heading = 'h2',
  layout = 'stacked',
  danger = false,
  children,
  className,
}: Props) {
  const headingId = useId()
  const heading = (
    <div className="min-w-0">
      <Heading id={headingId} className={cn('text-section-title', danger && 'text-destructive-muted-foreground')}>
        {title}
      </Heading>
      {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
    </div>
  )

  if (layout === 'side') {
    return (
      <section aria-labelledby={headingId} className={cn('grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)] lg:gap-x-10', className)}>
        {heading}
        <div className="min-w-0">{children}</div>
      </section>
    )
  }

  return (
    <section aria-labelledby={headingId} className={cn('flex flex-col gap-4', className)}>
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        {heading}
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  )
}
