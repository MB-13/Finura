import { ArrowLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { cn } from '@/lib/utils'

type Props = {
  title: ReactNode
  description?: ReactNode
  /** Small "<- Label" link above the title. */
  back?: { to: string; label: string }
  /** Status badge or other chips shown next to the title. */
  badge?: ReactNode
  /**
   * Inline editor (e.g. rename form) shown in place of the visible title. The <h1> stays in the DOM
   * (screen-reader only) so the page outline and landmarks do not change while editing.
   */
  editor?: ReactNode
  /** Right-aligned buttons / menus; wraps under the title on mobile. */
  actions?: ReactNode
  className?: string
}

/** Page title block used at the top of every page. Renders the page's single <h1>. */
export function PageHeader({ title, description, back, badge, editor, actions, className }: Props) {
  return (
    <header className={cn('flex flex-col gap-3', className)}>
      {back && (
        <Link
          to={back.to}
          className="-ml-1 inline-flex w-fit items-center gap-1 rounded-md px-1 text-caption font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-3.5" aria-hidden /> {back.label}
        </Link>
      )}
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1 basis-64">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            {editor ? (
              <>
                <h1 className="sr-only">{title}</h1>
                {editor}
              </>
            ) : (
              <h1 className="min-w-0 text-page-title break-words">{title}</h1>
            )}
            {badge}
          </div>
          {description && <p className="mt-1.5 max-w-2xl text-body text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  )
}
