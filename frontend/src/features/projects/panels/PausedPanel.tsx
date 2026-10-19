import { CheckCircle2, Download, ExternalLink, FlaskConical, PauseCircle } from 'lucide-react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Callout } from '@/components/Callout'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useMeta } from '@/features/meta/api'
import { usePlaygroundStatus } from '@/features/playground/api'
import type { Project } from '@/features/projects/api'
import { useCheckpointDownload } from '@/features/training/api'
import { KaggleJobInfo } from '@/features/training/KaggleJobInfo'
import { CancelTrainingButton } from '@/features/training/CancelTrainingButton'
import { PanelHeader } from '@/features/training/PanelHeader'
import { TokenReveal } from '@/features/training/TokenReveal'
import { useRevealedToken } from '@/features/training/token-store'
import { CheckpointInfo, JobLossChart } from '@/features/training/TrainingPanel'
import { trainingPercent } from '@/features/training/eta'
import { Progress } from '@/components/ui/progress'
import { useNow } from '@/lib/useNow'

/** Used only when the server sent no `status_message` (the server text comes from the design doc). */
const FALLBACK_BY_REASON: Record<string, string> = {
  session_ended: 'Your Colab session ended. Progress is saved. Open the notebook and run it again to continue.',
  idle_timeout: 'Colab disconnected because the tab was idle. Run the notebook again and keep the tab open.',
  no_gpu: 'Colab has no free GPU for your account right now. Progress is saved. Try again later.',
  stopped: 'Training stopped. Progress is saved. Run the notebook again to continue.',
  heartbeat_timeout: 'Training stopped. Progress is saved. Run the notebook again to continue.',
  user_stopped: 'You stopped the notebook. Progress is saved. Run it again to continue.',
}

export function PausedPanel({ project }: { project: Project }) {
  const job = project.active_job
  const now = useNow(5000)
  const meta = useMeta()
  const revealed = useRevealedToken(job?.id)
  const download = useCheckpointDownload(project.id, job?.id ?? '')
  const playground = usePlaygroundStatus(project.id)
  const notebookUrl = revealed?.notebookUrl ?? meta.data?.notebook_url ?? null
  const reason = project.status_reason
  const message =
    project.status_message ?? (reason ? (FALLBACK_BY_REASON[reason] ?? `Reason: ${reason.replace(/_/g, ' ')}`) : null)
  const savedStep = job ? (job.checkpoint_step ?? job.current_step) : 0
  const saved = job ? trainingPercent(savedStep, job.max_steps) : 0
  const kaggle = job?.backend === 'kaggle'
  const canTest = playground.data?.available === true

  function onDownload() {
    download.mutate(undefined, {
      onSuccess: ({ url }) => window.open(url, '_blank', 'noopener,noreferrer'),
      onError: (err) => toast.error(err.message),
    })
  }

  return (
    <Card className="border-warning/40">
      <PanelHeader
        icon={PauseCircle}
        tone="warning"
        title="Training is paused"
        description={kaggle ? 'Progress is saved. This can happen on the free Kaggle GPU.' : 'Progress is saved. This is normal on free Colab.'}
      />
      <CardContent className="flex flex-col gap-6">
        {message && (
          <Callout tone="warning" role="status">
            {message}
          </Callout>
        )}

        {job && (
          <div className="flex flex-col gap-3">
            <div className="flex items-end justify-between gap-4">
              <span className="text-metric text-5xl leading-none">{saved}%</span>
              <span className="flex items-center gap-1.5 pb-1 text-sm font-medium">
                <CheckCircle2 className="size-4 text-success" aria-hidden /> Progress saved
              </span>
            </div>
            <Progress value={saved} aria-label="Progress saved" className="h-1.5 bg-success/15" indicatorClassName="bg-success" />
            <p className="text-caption text-muted-foreground tabular-nums">
              <CheckpointInfo job={job} now={now} />
            </p>
          </div>
        )}

        <div className="flex flex-col gap-3">
          <h3 className="text-card-title">What to do next</h3>
          <p className="text-sm text-muted-foreground">
            {kaggle
              ? reason === 'no_gpu'
                ? 'Your Kaggle GPU hours for this week are used up. Training restarts by itself when your quota resets, or cancel and train on Colab.'
                : 'Training restarts automatically on your Kaggle account from the last saved checkpoint. You do not need to do anything.'
              : 'To continue, run the notebook again. Training picks up from the last saved checkpoint.'}
          </p>
          {job &&
            (kaggle ? (
              <KaggleJobInfo job={job} />
            ) : (
              <>
                {notebookUrl && (
                  <Button asChild size="lg" className="self-start">
                    <a href={notebookUrl} target="_blank" rel="noopener noreferrer">
                      <ExternalLink aria-hidden /> Open the notebook again
                    </a>
                  </Button>
                )}
                <p className="text-caption text-muted-foreground">
                  Use the same job token when the notebook asks for it. If you lost it, make a new one below.
                </p>
                <TokenReveal projectId={project.id} job={job} notebookUrl={notebookUrl} />
              </>
            ))}
        </div>

        {job && (
          <>
            <div className="flex flex-col gap-2">
              <h3 className="text-card-title">Training loss so far</h3>
              <JobLossChart projectId={project.id} job={job} />
            </div>

            <div className="flex flex-wrap items-center gap-3 border-t pt-5">
              <Button variant="outline" disabled={!job.checkpoint_step || download.isPending} onClick={onDownload}>
                <Download aria-hidden /> {download.isPending ? 'Preparing…' : 'Download latest checkpoint'}
              </Button>
              {canTest && (
                <Button asChild variant="outline">
                  <Link to={`/projects/${project.id}/playground`}>
                    <FlaskConical aria-hidden /> Test this checkpoint in the playground
                  </Link>
                </Button>
              )}
              <span className="sm:ml-auto">
                <CancelTrainingButton projectId={project.id} jobId={job.id} />
              </span>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
