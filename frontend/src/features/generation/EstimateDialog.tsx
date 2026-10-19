import { Clock } from 'lucide-react'
import { toast } from 'sonner'

import { Callout } from '@/components/Callout'
import { ErrorState } from '@/components/ErrorState'
import { StatRow } from '@/components/StatRow'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { useEstimate, useStartGeneration } from '@/features/generation/api'
import { ApiError } from '@/lib/api/client'
import { formatDuration } from '@/lib/format'

const GENERATE_ERRORS: Record<string, string> = {
  preview_required: 'Generate a preview with your current style first.',
  key_required: 'Connect a working API key in Settings first.',
  style_required: 'Save your style first.',
  generation_busy: 'A generation run is already in progress.',
}

type Props = { projectId: string; open: boolean; onOpenChange: (open: boolean) => void }

export function EstimateDialog({ projectId, open, onOpenChange }: Props) {
  const estimate = useEstimate(projectId, open)
  const start = useStartGeneration(projectId)
  const e = estimate.data
  const startError = start.error instanceof ApiError ? (GENERATE_ERRORS[start.error.code] ?? start.error.message) : start.error?.message

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Generate the full dataset?</DialogTitle>
          <DialogDescription>Here is roughly what this run will use. You can stop it at any time, and progress is saved.</DialogDescription>
        </DialogHeader>

        {estimate.isPending ? (
          <div aria-busy="true" aria-label="Loading estimate" className="flex flex-col gap-3">
            <Skeleton className="h-10" />
            <div className="grid grid-cols-2 gap-4">
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
            </div>
          </div>
        ) : estimate.isError ? (
          <ErrorState message={estimate.error.message} onRetry={() => estimate.refetch()} />
        ) : (
          e && (
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between gap-3 border-b pb-4">
                <span className="flex items-center gap-2 text-eyebrow">
                  <Clock className="size-3.5" aria-hidden /> Estimated time
                </span>
                <span className="text-metric text-lg">{formatDuration(e.est_minutes, e.est_days)}</span>
              </div>
              <div className="flex flex-col gap-4">
                <StatRow
                  items={[
                    { label: 'Sections to read', value: e.chunks.toLocaleString() },
                    { label: 'Target pairs', value: e.target_pairs.toLocaleString() },
                  ]}
                />
                <StatRow
                  className="border-t pt-4"
                  items={[
                    { label: 'AI requests', value: e.est_requests.toLocaleString() },
                    { label: 'Tokens', value: e.est_tokens.toLocaleString() },
                  ]}
                />
              </div>
              {e.supported_pairs < e.target_pairs && (
                <Callout tone="info">
                  Your documents support about {e.supported_pairs.toLocaleString()} pairs, fewer than the target.
                </Callout>
              )}
              {e.est_days > 1 && (
                <Callout tone="info">
                  Multi-day runs are normal on free keys: progress is saved and it resumes by itself. Tip: connect a Gemini
                  key to finish faster.
                </Callout>
              )}
              {e.fits_daily_quota ? (
                <Callout tone="success">Fits within your free daily quota.</Callout>
              ) : (
                <Callout tone="warning">
                  This is more than your free daily quota, so the run will pause when the quota is used and continue after it
                  resets.
                </Callout>
              )}
            </div>
          )
        )}

        {startError && (
          <Callout tone="destructive" role="alert">
            {startError}
          </Callout>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!e || start.isPending}
            onClick={() =>
              start.mutate(undefined, {
                onSuccess: () => {
                  toast.success('Generation started')
                  onOpenChange(false)
                },
              })
            }
          >
            {start.isPending ? 'Starting…' : 'Start generating'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
