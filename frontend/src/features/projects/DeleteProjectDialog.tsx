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
import { useDeleteProject } from '@/features/projects/api'

type Props = {
  project: { id: string; name: string } | null
  onOpenChange: (open: boolean) => void
  onDeleted?: () => void
}

export function DeleteProjectDialog({ project, onOpenChange, onDeleted }: Props) {
  const del = useDeleteProject()

  return (
    <AlertDialog open={project !== null} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this project?</AlertDialogTitle>
          <AlertDialogDescription>
            &ldquo;{project?.name}&rdquo; and its documents, dataset and model files will be permanently deleted. This
            can&apos;t be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={del.isPending}
            onClick={(e) => {
              e.preventDefault()
              if (!project) return
              del.mutate(project.id, {
                onSuccess: () => {
                  toast.success('Project deleted')
                  onOpenChange(false)
                  onDeleted?.()
                },
                onError: (err) => toast.error(err.message),
              })
            }}
          >
            {del.isPending ? 'Deleting…' : 'Delete project'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
