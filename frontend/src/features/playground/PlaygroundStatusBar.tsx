import { Loader2 } from 'lucide-react'
import { Link } from 'react-router'

import type { PlaygroundStatus } from '@/features/playground/api'
import { cn } from '@/lib/utils'

/** One quiet status line: state dot, mono model name, where the weights come from, and the speed tip. */
export function PlaygroundStatusBar({ status }: { status: PlaygroundStatus }) {
  const source =
    status.source === 'checkpoint'
      ? `Checkpoint · step ${status.checkpoint_step ?? '?'}`
      : status.source === 'final'
        ? 'Final model'
        : null
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b pb-3 text-caption">
      {/* one persistent live region: only its content changes, so screen readers announce each state change */}
      <div role="status" className="flex items-center gap-1.5 font-medium">
        {status.state === 'warming' ? (
          <span className="flex items-center gap-1.5 text-info-muted-foreground">
            <Loader2 className="size-3.5 motion-safe:animate-spin" aria-hidden /> Loading your model… ~20 s
          </span>
        ) : status.state === 'warm' ? (
          <span className="flex items-center gap-1.5 text-success-muted-foreground">
            <span aria-hidden className="size-1.5 rounded-full bg-success" />
            Ready
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span aria-hidden className={cn('size-1.5 rounded-full bg-muted-foreground/50')} />
            Not loaded yet
          </span>
        )}
      </div>
      {status.model && <span className="min-w-0 font-mono text-[0.75rem] break-all text-foreground">{status.model}</span>}
      {source && <span className="font-mono text-[0.75rem] text-muted-foreground">{source}</span>}
      <span className="text-muted-foreground sm:ml-auto">
        Slow on our shared CPU.{' '}
        <Link to="/docs/ollama" className="font-medium text-foreground underline underline-offset-4 hover:text-primary">
          Run it locally with Ollama
        </Link>{' '}
        for speed.
      </span>
    </div>
  )
}
