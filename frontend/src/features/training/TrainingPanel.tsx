import { Cpu, Loader2 } from 'lucide-react'

import { ErrorState } from '@/components/ErrorState'
import { Callout } from '@/components/Callout'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import type { Project } from '@/features/projects/api'
import { useMetrics, type TrainingJob } from '@/features/training/api'
import { CancelTrainingButton } from '@/features/training/CancelTrainingButton'
import { estimateEtaSeconds } from '@/features/training/eta'
import { KaggleJobInfo } from '@/features/training/KaggleJobInfo'
import { LossChart } from '@/features/training/LossChart'
import { MetaRow } from '@/features/training/MetaRow'
import { PanelHeader } from '@/features/training/PanelHeader'
import { ProgressWithEta } from '@/features/training/ProgressWithEta'
import { formatAgo } from '@/lib/format'
import { useNow } from '@/lib/useNow'

function gpuLabel(job: TrainingJob): string | null {
  const name = job.runtime_info?.['gpu_name']
  if (typeof name !== 'string' || !name) return null
  const vram = job.runtime_info?.['vram_gb']
  return typeof vram === 'number' ? `${name} · ${vram} GB` : name
}

export function CheckpointInfo({ job, now }: { job: TrainingJob; now: number }) {
  if (!job.checkpoint_step) return <span>None yet. The first is saved after a few minutes.</span>
  return (
    <span>
      Saved at step {job.checkpoint_step.toLocaleString()}
      {job.checkpoint_uploaded_at && ` · ${formatAgo(job.checkpoint_uploaded_at, now)}`}
    </span>
  )
}

/** Loss curve for a job: fetched once, then extended by the `train_metrics` stream. */
export function JobLossChart({ projectId, job }: { projectId: string; job: TrainingJob }) {
  const metrics = useMetrics(projectId, job.id)
  if (metrics.isPending) return <Skeleton aria-busy="true" aria-label="Loading loss chart" className="h-56" />
  if (metrics.isError) return <ErrorState message={metrics.error.message} onRetry={() => metrics.refetch()} />
  return <LossChart points={metrics.data} maxSteps={job.max_steps} />
}

export function TrainingPanel({ project }: { project: Project }) {
  const job = project.active_job
  const now = useNow()
  const metrics = useMetrics(project.id, job?.id)
  const kaggle = job?.backend === 'kaggle'
  const eta = job ? estimateEtaSeconds(metrics.data ?? [], job.current_step, job.max_steps) : null

  return (
    <Card>
      <PanelHeader
        icon={Loader2}
        spin
        tone="info"
        title="Training your model"
        description={kaggle ? 'Training runs on your Kaggle account. This page updates by itself.' : 'Your notebook is training now. This page updates by itself.'}
      />
      <CardContent className="flex flex-col gap-6">
        {job ? (
          <>
            <ProgressWithEta current={job.current_step} max={job.max_steps} etaSeconds={eta} />
            <MetaRow
              className="border-t pt-4"
              items={[
                {
                  label: 'GPU',
                  value: (
                    <span className="inline-flex items-center gap-1.5">
                      <Cpu className="size-3.5 text-muted-foreground" aria-hidden /> {gpuLabel(job) ?? 'Waiting for details'}
                    </span>
                  ),
                },
                { label: 'Heartbeat', value: job.last_heartbeat_at ? `Updated ${formatAgo(job.last_heartbeat_at, now)}` : 'No update yet' },
                { label: 'Last checkpoint', value: <CheckpointInfo job={job} now={now} /> },
              ]}
            />
            <div className="flex flex-col gap-3 border-t pt-5">
              <h3 className="text-card-title">Training loss</h3>
              <JobLossChart projectId={project.id} job={job} />
            </div>
            {kaggle ? (
              <>
                <KaggleJobInfo job={job} className="border-t pt-5" />
                <Callout tone="info">You can close this tab. If the Kaggle session ends, progress is saved and training restarts by itself.</Callout>
              </>
            ) : (
              <Callout tone="info">Keep the Colab tab open. If the session ends, progress is saved and you can pick up where you left off.</Callout>
            )}
            <div className="flex border-t pt-5">
              <CancelTrainingButton projectId={project.id} jobId={job.id} />
            </div>
          </>
        ) : (
          <p role="status" className="text-sm text-muted-foreground">
            Loading your training job…
          </p>
        )}
      </CardContent>
    </Card>
  )
}
