import { NotebookPen } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { useMeta } from '@/features/meta/api'
import type { Project } from '@/features/projects/api'
import { KaggleRunPanel } from '@/features/training/KaggleRunPanel'
import { CancelTrainingButton } from '@/features/training/CancelTrainingButton'
import { ColabSteps } from '@/features/training/ColabSteps'
import { PanelHeader } from '@/features/training/PanelHeader'
import { SwitchToKaggle } from '@/features/training/SwitchToKaggle'
import { TokenReveal } from '@/features/training/TokenReveal'
import { useRevealedToken } from '@/features/training/token-store'
import { formatDuration } from '@/lib/format'

export function RunNotebookPanel({ project }: { project: Project }) {
  if (project.active_job?.backend === 'kaggle') return <KaggleRunPanel project={project} />
  return <ColabRunPanel project={project} />
}

function ColabRunPanel({ project }: { project: Project }) {
  const job = project.active_job
  const revealed = useRevealedToken(job?.id)
  const meta = useMeta()
  const notebookUrl = revealed?.notebookUrl ?? meta.data?.notebook_url ?? null

  return (
    <Card>
      <PanelHeader
        icon={NotebookPen}
        title="Run the training notebook"
        description="Training runs on a free GPU in your own Google Colab account. It takes four quick steps."
      />
      <CardContent className="flex flex-col gap-6">
        {job ? (
          <>
            {job.state === 'created' && <SwitchToKaggle projectId={project.id} jobId={job.id} />}
            <ColabSteps notebookUrl={notebookUrl} tokenSlot={<TokenReveal projectId={project.id} job={job} notebookUrl={notebookUrl} />} />
            <div role="status" aria-live="polite" className="flex items-center gap-3 border-t pt-5 text-sm">
              <span aria-hidden className="relative flex size-2.5 shrink-0">
                <span className="absolute inline-flex size-full rounded-full bg-info opacity-60 motion-safe:animate-ping" />
                <span className="relative inline-flex size-2.5 rounded-full bg-info" />
              </span>
              Waiting for the notebook to connect…
            </div>
            <p className="text-caption text-muted-foreground tabular-nums">
              {job.est_minutes ? `Training usually takes ${formatDuration(job.est_minutes, 0)} on a T4. ` : ''}
              Model: <span className="font-mono text-foreground">{job.base_model_id}</span>
            </p>
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
