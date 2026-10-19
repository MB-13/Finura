import { ExternalLink, RotateCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import type { TrainingJob } from '@/features/training/api'
import { cn } from '@/lib/utils'

export const MAX_LAUNCH_ATTEMPTS = 3

/** "View on Kaggle" link plus the automatic-restart note, shared by the Kaggle job panels. */
export function KaggleJobInfo({ job, className }: { job: TrainingJob; className?: string }) {
  if (!job.external_url && job.launch_attempts <= 1) return null
  return (
    <div className={cn('flex flex-wrap items-center gap-x-4 gap-y-3', className)}>
      {job.external_url && (
        <Button asChild variant="outline" size="sm">
          <a href={job.external_url} target="_blank" rel="noopener noreferrer">
            <ExternalLink aria-hidden /> View on Kaggle
          </a>
        </Button>
      )}
      {job.launch_attempts > 1 && (
        <p role="status" className="flex items-start gap-2 text-caption text-muted-foreground">
          <RotateCw className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          Restarted automatically after the Kaggle session ended (attempt {job.launch_attempts} of {MAX_LAUNCH_ATTEMPTS}).
        </p>
      )}
    </div>
  )
}
