import { AlertTriangle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type Props = { title?: string; message: string; onRetry?: () => void; className?: string }

export function ErrorState({ title = 'Something went wrong', message, onRetry, className }: Props) {
  return (
    <div
      role="alert"
      className={cn('flex items-start gap-3 rounded-xl border border-destructive/30 bg-destructive-muted p-4', className)}
    >
      <AlertTriangle className="mt-0.5 size-5 shrink-0 text-destructive-muted-foreground" aria-hidden />
      <div className="flex min-w-0 flex-1 flex-col items-start gap-1">
        <div className="text-card-title text-destructive-muted-foreground">{title}</div>
        <p className="text-sm text-foreground/80 break-words">{message}</p>
        {onRetry && (
          <Button variant="outline" size="sm" className="mt-2" onClick={onRetry}>
            Try again
          </Button>
        )}
      </div>
    </div>
  )
}
