import { Zap } from 'lucide-react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Callout } from '@/components/Callout'
import { Button } from '@/components/ui/button'
import { gpuHoursLeft, useKaggle } from '@/features/compute/api'
import { useSwitchToKaggle } from '@/features/training/api'
import { CREATE_ERRORS } from '@/features/training/model-copy'
import { ApiError } from '@/lib/api/client'

/** Offered while a Colab job waits for its notebook: run the same job automatically on Kaggle instead. */
export function SwitchToKaggle({ projectId, jobId }: { projectId: string; jobId: string }) {
  const kaggle = useKaggle()
  const switchJob = useSwitchToKaggle(projectId)
  const account = kaggle.data
  const ready = account?.status === 'ok'
  const hoursLeft = account && ready ? gpuHoursLeft(account) : null

  return (
    <Callout
      icon={Zap}
      tone="info"
      title="Skip the notebook: train automatically on Kaggle"
      action={
        ready ? (
          <Button
            size="sm"
            disabled={switchJob.isPending}
            onClick={() =>
              switchJob.mutate(jobId, {
                onSuccess: () => toast.success('Starting on Kaggle'),
                onError: (err) =>
                  toast.error(err instanceof ApiError && err.code && CREATE_ERRORS[err.code] ? CREATE_ERRORS[err.code] : err.message),
              })
            }
          >
            {switchJob.isPending ? 'Switching…' : 'Run on Kaggle instead'}
          </Button>
        ) : (
          <Link to="/settings" className="text-sm font-medium underline underline-offset-4">
            {account ? 'Your Kaggle account needs attention: open Settings' : 'Connect Kaggle in Settings to train automatically'}
          </Link>
        )
      }
    >
      Same model and settings, on a free T4 GPU in your own Kaggle account. Nothing to run, and you can close this tab.
      {hoursLeft !== null && ` ${hoursLeft} GPU hours left this week.`}
    </Callout>
  )
}
