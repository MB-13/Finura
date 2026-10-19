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
import { Button } from '@/components/ui/button'
import { useCancelTraining } from '@/features/training/api'

export function CancelTrainingButton({ projectId, jobId }: { projectId: string; jobId: string }) {
  const [open, setOpen] = useState(false)
  const cancel = useCancelTraining(projectId, jobId)

  return (
    <>
      <Button variant="outline" className="self-start" onClick={() => setOpen(true)}>
        Cancel training
      </Button>
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Cancel training?</AlertDialogTitle>
            <AlertDialogDescription>
              The job token stops working and you go back to dataset review. Your dataset is kept, and you can set up training again.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep training</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={cancel.isPending}
              onClick={(e) => {
                e.preventDefault()
                cancel.mutate(undefined, {
                  onSuccess: () => {
                    setOpen(false)
                    toast.success('Training cancelled')
                  },
                  onError: (err) => toast.error(err.message),
                })
              }}
            >
              {cancel.isPending ? 'Cancelling…' : 'Cancel training'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
