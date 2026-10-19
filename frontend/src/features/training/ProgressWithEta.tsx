import { Progress } from '@/components/ui/progress'
import { trainingPercent } from '@/features/training/eta'
import { formatEta } from '@/lib/format'

function etaText(seconds: number): string {
  const t = formatEta(seconds)
  return t.charAt(0).toUpperCase() + t.slice(1)
}

/** Hero progress: big mono percent, step counter, thin bar and the time left. */
export function ProgressWithEta({ current, max, etaSeconds, label = 'Training progress', statusText }: { current: number; max: number; etaSeconds?: number | null; label?: string; statusText?: string }) {
  const percent = trainingPercent(current, max)
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-end justify-between gap-4">
        <span className="text-metric text-5xl leading-none">{percent}%</span>
        <span className="text-metric pb-1 text-sm text-muted-foreground">
          Step {current.toLocaleString()} of {max.toLocaleString()}
        </span>
      </div>
      <Progress value={percent} aria-label={label} className="h-1.5" />
      <p role="status" aria-live="polite" className="text-caption text-muted-foreground tabular-nums">
        {statusText ?? (etaSeconds != null ? `${etaText(etaSeconds)} left` : 'Working out the time left…')}
      </p>
    </div>
  )
}
