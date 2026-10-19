import { AlertTriangle, CheckCircle2, Info, OctagonAlert, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type CalloutTone = 'info' | 'success' | 'warning' | 'destructive'

const toneStyle: Record<CalloutTone, { box: string; text: string; icon: LucideIcon }> = {
  info: { box: 'border-info/25 bg-info-muted', text: 'text-info-muted-foreground', icon: Info },
  success: { box: 'border-success/25 bg-success-muted', text: 'text-success-muted-foreground', icon: CheckCircle2 },
  warning: { box: 'border-warning/40 bg-warning-muted', text: 'text-warning-muted-foreground', icon: AlertTriangle },
  destructive: { box: 'border-destructive/25 bg-destructive-muted', text: 'text-destructive-muted-foreground', icon: OctagonAlert },
}

type Props = {
  tone?: CalloutTone
  title?: ReactNode
  /** Body text / content. */
  children?: ReactNode
  /** Buttons or links placed under the body. */
  action?: ReactNode
  /** Override the default tone icon. */
  icon?: LucideIcon
  /** Announce changes to assistive tech: "alert" for errors, "status" for updates. Omit for static notes. */
  role?: 'alert' | 'status'
  className?: string
}

/** Inline notice. Tone changes colour AND icon, so meaning never relies on colour alone. */
export function Callout({ tone = 'info', title, children, action, icon, role, className }: Props) {
  const style = toneStyle[tone]
  const Icon = icon ?? style.icon
  return (
    <div role={role} className={cn('flex items-start gap-3 rounded-xl border p-4', style.box, className)}>
      <Icon className={cn('mt-0.5 size-5 shrink-0', style.text)} aria-hidden />
      <div className="flex min-w-0 flex-1 flex-col items-start gap-1">
        {title && <div className={cn('text-card-title', style.text)}>{title}</div>}
        {children && <div className="text-sm text-foreground/85 break-words">{children}</div>}
        {action && <div className="mt-2 flex flex-wrap gap-2">{action}</div>}
      </div>
    </div>
  )
}
