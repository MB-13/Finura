import { Loader2 } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import type { Project } from '@/features/projects/api'
import { CancelTrainingButton } from '@/features/training/CancelTrainingButton'
import { KaggleJobInfo } from '@/features/training/KaggleJobInfo'
import { MetaRow } from '@/features/training/MetaRow'
import { PanelHeader } from '@/features/training/PanelHeader'
import { StepMarker } from '@/components/StepRail'
import { formatDuration } from '@/lib/format'
import { cn } from '@/lib/utils'

/** Awaiting-run screen for a Kaggle job: nothing for the user to run, no token, no notebook. */
export function KaggleRunPanel({ project }: { project: Project }) {
  const job = project.active_job
  if (!job) return null
  const launched = Boolean(job.external_url)

  return (
    <Card>
      <PanelHeader
        icon={Loader2}
        spin
        tone="info"
        title={launched ? 'Running on your Kaggle account' : 'Starting on Kaggle…'}
        description={
          launched
            ? 'Training runs on a free GPU in your own Kaggle account. You can close this tab; we will email you when it is done.'
            : 'We are setting up a private notebook in your Kaggle account. This takes a few minutes.'
        }
      />
      <CardContent className="flex flex-col gap-6">
        <KaggleStages current={stageOf(launched, job.runtime_info?.kaggle_status)} />
        <MetaRow
          className="border-t pt-5"
          items={[
            { label: 'Base model', value: <span className="font-mono text-xs">{job.base_model_id}</span> },
            ...(job.est_minutes ? [{ label: 'Usually takes', value: `${formatDuration(job.est_minutes, 0)} on a T4` }] : []),
          ]}
        />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3 border-t pt-5">
          <CancelTrainingButton projectId={project.id} jobId={job.id} />
          <KaggleJobInfo job={job} />
        </div>
      </CardContent>
    </Card>
  )
}

type Stage = 0 | 1 | 2 | 3

/** Before the kernel calls /start, the poller records Kaggle's own status (QUEUED / RUNNING) on the job. */
function stageOf(launched: boolean, kaggleStatus: unknown): Stage {
  if (!launched) return 0
  if (kaggleStatus === 'RUNNING') return 2
  return 1
}

const STAGES = [
  { title: 'Sending the job to Kaggle', hint: 'Creating a private notebook in your account.' },
  { title: 'Waiting for a free GPU', hint: 'Kaggle queues runs until a T4 is free. Usually a few minutes, sometimes longer when Kaggle is busy.' },
  { title: 'Setting up', hint: 'Installing the training libraries and loading the model. About 3 to 8 minutes.' },
  { title: 'Training', hint: 'Progress and the loss chart appear on this page as soon as the first steps finish.' },
] as const

function KaggleStages({ current }: { current: Stage }) {
  return (
    <ol aria-label="Kaggle progress" className="flex flex-col">
      {STAGES.map((stage, i) => {
        const state = i < current ? 'done' : i === current ? 'active' : 'todo'
        const last = i === STAGES.length - 1
        return (
          <li key={stage.title} aria-current={state === 'active' ? 'step' : undefined} className={cn('relative flex gap-3', !last && 'pb-4')}>
            {!last && <span aria-hidden className={cn('absolute top-6 bottom-0.5 left-[9.5px] w-px', state === 'done' ? 'bg-primary/60' : 'bg-border')} />}
            <StepMarker state={state} n={i + 1} size="sm" pulse />
            <div className="flex min-w-0 flex-col gap-0.5">
              <span className={cn('text-[0.8125rem] leading-5', state === 'todo' ? 'text-muted-foreground' : state === 'active' ? 'font-semibold' : 'font-medium')}>
                {stage.title}
                <span className="sr-only">{state === 'done' ? ' (done)' : state === 'active' ? ' (in progress)' : ''}</span>
              </span>
              {state === 'active' && (
                <span role="status" aria-live="polite" className="text-caption text-muted-foreground">
                  {stage.hint}
                </span>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
