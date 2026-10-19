import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

export type PanelTone = 'primary' | 'info' | 'warning' | 'success' | 'neutral'

const toneStyle: Record<PanelTone, string> = {
  primary: 'text-primary',
  info: 'text-info-muted-foreground',
  warning: 'text-warning-muted-foreground',
  success: 'text-success-muted-foreground',
  neutral: 'text-muted-foreground',
}

type Props = {
  icon: LucideIcon
  tone?: PanelTone
  title: ReactNode
  description?: ReactNode
  /** Animate the icon (waiting/working states). Respects reduced motion. */
  spin?: boolean
  /** Right-aligned buttons; wraps below the title on mobile. */
  actions?: ReactNode
  /** Small mono label above the title (e.g. "Training complete"). */
  eyebrow?: ReactNode
  /** Larger title for the results screen. */
  large?: boolean
}

/** Header shared by the training and results panels: tone-coloured icon inline with the title, one-line description. */
export function PanelHeader({ icon: Icon, tone = 'primary', title, description, spin = false, actions, eyebrow, large = false }: Props) {
  return (
    <CardHeader>
      <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
        <div className="min-w-0 flex-1 basis-64">
          {eyebrow && <div className={cn('mb-1.5 flex items-center gap-1.5 text-eyebrow')}>{eyebrow}</div>}
          <CardTitle className={cn('flex items-center gap-2', large ? 'text-2xl leading-8 font-semibold tracking-tight' : 'text-section-title')}>
            <Icon className={cn('shrink-0', large ? 'size-6' : 'size-5', toneStyle[tone], spin && 'motion-safe:animate-spin')} aria-hidden />
            <span className="min-w-0">{title}</span>
          </CardTitle>
          {description && <CardDescription className="mt-1">{description}</CardDescription>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </CardHeader>
  )
}
