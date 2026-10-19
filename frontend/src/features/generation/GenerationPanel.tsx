import { Clock, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Callout } from '@/components/Callout'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { MetaRow } from '@/features/training/MetaRow'
import { useCancelRun, useFinishRun } from '@/features/generation/api'
import { useLatestNotice } from '@/features/generation/useNotice'
import type { Project } from '@/features/projects/api'
import type { Run } from '@/features/style/api'
import { cn } from '@/lib/utils'

const stateLabel: Record<Run['state'], string> = {
  queued: 'Waiting to start',
  running: 'Generating',
  waiting_quota: 'Waiting for free quota',
  finalizing: 'Scoring and splitting',
  done: 'Done',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

/** Matches the backend's minimum of judged pairs; below this the button would only return an error. */
export const FINISH_EARLY_MIN_PAIRS = 20

function formatResume(iso: string): string {
  return new Date(iso).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })
}

export function GenerationPanel({ project }: { project: Project }) {
  const run = project.active_run
  const notice = useLatestNotice(project.id)
  const cancel = useCancelRun(project.id)
  const finish = useFinishRun(project.id)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [finishOpen, setFinishOpen] = useState(false)

  const total = run?.total_chunks ?? 0
  const done = run?.done_chunks ?? 0
  const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0
  const waiting = run?.state === 'waiting_quota'
  const canFinish =
    !!run &&
    project.allowed_actions.includes('finish_generation') &&
    (run.state === 'running' || run.state === 'waiting_quota') &&
    run.pairs_generated >= FINISH_EARLY_MIN_PAIRS

  const provider = project.gen_provider
    ? [project.gen_provider.charAt(0).toUpperCase() + project.gen_provider.slice(1), project.gen_model].filter(Boolean).join(' · ')
    : null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Loader2 className="size-5 text-primary motion-safe:animate-spin" aria-hidden /> Generating your dataset
        </CardTitle>
        <CardDescription>
          We&apos;re reading your documents and writing question and answer pairs in your style. Multi-day runs are normal on free keys. Progress is saved, so you can close this tab and come back. Next, you&apos;ll review the dataset before training.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {run ? (
          <div className="flex flex-col gap-4">
            <div className="flex items-end justify-between gap-4">
              <span className="text-metric text-5xl leading-none">{percent}%</span>
              <span className="text-metric pb-1 text-sm text-muted-foreground">
                {done} of {total} sections
              </span>
            </div>
            <Progress value={percent} className="h-1.5" aria-label="Generation progress" />
            <MetaRow
              role="status"
              aria-live="polite"
              className="border-t pt-4"
              items={[
                { label: 'Output', value: <span className="text-metric text-sm">{run.pairs_generated.toLocaleString()} pairs generated</span> },
                {
                  label: 'Status',
                  value: (
                    <span className="inline-flex items-center gap-1.5">
                      <span aria-hidden className={cn('size-1.5 rounded-full', waiting ? 'bg-warning' : 'bg-info')} />
                      {stateLabel[run.state]}
                    </span>
                  ),
                },
                ...(provider ? [{ label: 'Writing with', value: <span className="font-mono text-xs">{provider}</span> }] : []),
              ]}
            />
          </div>
        ) : (
          <p role="status" className="text-sm text-muted-foreground">
            Starting up…
          </p>
        )}

        {waiting && (
          <Callout tone="info" icon={Clock} title="Paused until your free quota resets">
            {run?.resume_at && <p>It will continue automatically at {formatResume(run.resume_at)}.</p>}
            {notice && <p className="text-muted-foreground">{notice.text}</p>}
            <p className="text-muted-foreground">Nothing to do right now. Tip: connect a Gemini key to finish faster.</p>
          </Callout>
        )}
        {!waiting && notice && (
          <Callout tone="info" role="status">
            {notice.text}
          </Callout>
        )}

        {run && (
          <div className="flex flex-col gap-3 border-t pt-5">
            <div className="flex flex-col gap-2 sm:flex-row">
              {canFinish && <Button onClick={() => setFinishOpen(true)}>Use pairs so far</Button>}
              <Button variant="outline" onClick={() => setConfirmOpen(true)}>
                Cancel generation
              </Button>
            </div>
            {canFinish && (
              <p className="text-caption text-muted-foreground">
                &ldquo;Use pairs so far&rdquo; stops now and builds your dataset from what is ready. A smaller dataset still trains.
              </p>
            )}
          </div>
        )}
      </CardContent>

      <AlertDialog open={finishOpen} onOpenChange={setFinishOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Finish with the pairs so far?</AlertDialogTitle>
            <AlertDialogDescription>
              Generation stops now and the remaining {Math.max(0, total - done)} sections are skipped. Your dataset is
              built from the {run?.pairs_generated.toLocaleString()} pairs generated so far, keeping only those that
              passed the quality check. A smaller dataset still trains, but the model learns your style less firmly.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep generating</AlertDialogCancel>
            <AlertDialogAction
              disabled={finish.isPending}
              onClick={(e) => {
                e.preventDefault()
                if (!run) return
                finish.mutate(run.id, {
                  onSuccess: () => {
                    setFinishOpen(false)
                    toast.success('Building your dataset from the pairs so far')
                  },
                  onError: (err) => toast.error(err.message),
                })
              }}
            >
              {finish.isPending ? 'Finishing…' : 'Use pairs so far'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Cancel generation?</AlertDialogTitle>
            <AlertDialogDescription>
              The run stops. You can adjust your style and start again later.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep generating</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={cancel.isPending}
              onClick={(e) => {
                e.preventDefault()
                if (!run) return
                cancel.mutate(run.id, {
                  onSuccess: () => {
                    setConfirmOpen(false)
                    toast.success('Generation cancelled')
                  },
                  onError: (err) => toast.error(err.message),
                })
              }}
            >
              {cancel.isPending ? 'Cancelling…' : 'Cancel generation'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}
