import { Loader2 } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import type { Project } from '@/features/projects/api'
import { PanelHeader } from '@/features/training/PanelHeader'
import { ProgressWithEta } from '@/features/training/ProgressWithEta'

export function EvaluatingPanel({ project }: { project: Project }) {
  const job = project.active_job
  const evaluation = project.evaluation
  return (
    <Card>
      <PanelHeader
        icon={Loader2}
        spin
        tone="info"
        title="Evaluating your model"
        description={
          job?.backend === 'kaggle'
            ? 'Running evaluation on your Kaggle account… You can close this tab.'
            : 'Running evaluation in your notebook… Keep the Colab tab open until it finishes.'
        }
      />
      <CardContent className="flex flex-col gap-5">
        {job && job.max_steps > 0 ? (
          <ProgressWithEta current={job.current_step} max={job.max_steps} label="Training finished" statusText="Training finished" />
        ) : (
          <Progress aria-label="Evaluation progress" className="h-1.5" />
        )}
        <p role="status" aria-live="polite" className="border-t pt-4 text-sm text-muted-foreground">
          {evaluation?.state === 'scoring'
            ? 'Scoring answers from the base and the tuned model…'
            : 'Training is done. Now we compare your tuned model with the original and save your files.'}
        </p>
      </CardContent>
    </Card>
  )
}
