import { statusMeta, type Tone } from '@/components/status-meta'
import type { ProjectStatus } from '@/features/projects/api'
import { cn } from '@/lib/utils'

/** Soft background + text per tone, and the dot colour. Colour is never the only signal: the label is always shown. */
const toneStyle: Record<Tone, { badge: string; dot: string }> = {
  neutral: { badge: 'bg-muted text-muted-foreground', dot: 'bg-muted-foreground/60' },
  running: { badge: 'bg-info-muted text-info-muted-foreground', dot: 'bg-info' },
  paused: { badge: 'bg-warning-muted text-warning-muted-foreground', dot: 'bg-warning' },
  ready: { badge: 'bg-success-muted text-success-muted-foreground', dot: 'bg-success' },
  failed: { badge: 'bg-destructive-muted text-destructive-muted-foreground', dot: 'bg-destructive' },
}

export function StatusBadge({ status, className }: { status: ProjectStatus; className?: string }) {
  const { label, tone } = statusMeta[status]
  const style = toneStyle[tone]
  return (
    <span
      data-slot="badge"
      data-status={status}
      data-tone={tone}
      className={cn(
        'inline-flex w-fit shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap',
        style.badge,
        className,
      )}
    >
      <span aria-hidden className="relative flex size-1.5">
        {tone === 'running' && (
          <span className={cn('absolute inline-flex size-full rounded-full opacity-60 motion-safe:animate-ping', style.dot)} />
        )}
        <span className={cn('relative inline-flex size-1.5 rounded-full', style.dot)} />
      </span>
      {label}
    </span>
  )
}
