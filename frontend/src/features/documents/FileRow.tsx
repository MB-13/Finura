import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

function extension(filename: string): string {
  const dot = filename.lastIndexOf('.')
  return dot >= 0 ? filename.slice(dot + 1, dot + 5).toUpperCase() : 'FILE'
}

type Props = {
  filename: string
  /** Secondary line under the name (size, pages, error). */
  meta?: ReactNode
  /** Right-aligned status chip or action button. */
  trailing?: ReactNode
  /** Extra content under the text, e.g. a progress bar. */
  children?: ReactNode
  tone?: 'default' | 'error'
}

/** One file in a list: extension, name, meta line, trailing status/action. Used by upload and processing. */
export function FileRow({ filename, meta, trailing, children, tone = 'default' }: Props) {
  return (
    <li className="flex items-center gap-3 py-3">
      <span aria-hidden className={cn('w-10 shrink-0 text-eyebrow', tone === 'error' && 'text-destructive-muted-foreground')}>
        {extension(filename)}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="truncate text-sm font-medium">{filename}</div>
        {meta && (
          <div className="text-caption break-words">
            <div className={tone === 'error' ? 'text-destructive-muted-foreground' : 'text-muted-foreground'}>{meta}</div>
          </div>
        )}
        {children}
      </div>
      {trailing && <div className="flex shrink-0 items-center gap-2">{trailing}</div>}
    </li>
  )
}
