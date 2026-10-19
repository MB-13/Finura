import { StepMarker } from '@/components/StepRail'
import { Progress } from '@/components/ui/progress'
import type { ProjectStatus } from '@/features/projects/api'
import { STEPS, STEP_HINTS, stepPercent, stepStates } from '@/features/projects/steps'
import { cn } from '@/lib/utils'

/** Workspace step list: vertical rail on desktop (lg+), compact progress bar on mobile. */
export function ProjectStepper({ status, className }: { status: ProjectStatus; className?: string }) {
  const states = stepStates(status)
  const currentIdx = states.indexOf('active')
  const percent = stepPercent(status)

  return (
    <nav aria-label="Project steps" className={cn('lg:sticky lg:top-20 lg:self-start', className)}>
      {/* mobile: compact progress bar */}
      <div className="flex flex-col gap-2.5 rounded-xl border bg-card p-3.5 shadow-card lg:hidden">
        <div className="flex items-baseline justify-between gap-3 text-sm">
          <span className="text-card-title">{currentIdx >= 0 ? STEPS[currentIdx] : status === 'failed' ? 'Needs attention' : 'All steps complete'}</span>
          <span className="text-eyebrow tabular-nums">
            {currentIdx >= 0 ? `Step ${currentIdx + 1} of ${STEPS.length}` : status === 'failed' ? '' : `${STEPS.length} of ${STEPS.length}`}
          </span>
        </div>
        <Progress value={percent} aria-label="Project progress" className="h-1.5" />
      </div>

      {/* desktop: vertical stepper, one hairline rail; only the current step shows its hint */}
      <ol className="hidden flex-col lg:flex">
        {STEPS.map((label, i) => {
          const state = states[i]!
          const last = i === STEPS.length - 1
          return (
            <li key={label} aria-current={state === 'active' ? 'step' : undefined} className={cn('relative flex gap-3', !last && (state === 'active' ? 'pb-5' : 'pb-4'))}>
              {!last && <span aria-hidden className={cn('absolute top-6 bottom-0.5 left-[9.5px] w-px', state === 'done' ? 'bg-primary/60' : 'bg-border')} />}
              <StepMarker state={state} n={i + 1} size="sm" />
              <div className="min-w-0 flex-1">
                <div className={cn('text-[0.8125rem] leading-5', state === 'active' ? 'font-semibold text-foreground' : state === 'done' ? 'font-medium text-foreground' : 'text-muted-foreground')}>
                  {label}
                  <span className="sr-only">{state === 'done' ? ' (done)' : state === 'active' ? ' (current)' : ''}</span>
                </div>
                {state === 'active' && (
                  <div aria-hidden className="mt-0.5 text-xs leading-4 text-muted-foreground">
                    {STEP_HINTS[label]}
                  </div>
                )}
              </div>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
