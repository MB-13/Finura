import { LifeBuoy, RotateCw } from 'lucide-react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Callout } from '@/components/Callout'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useRetryProject, type Project } from '@/features/projects/api'

export function FailedPanel({ project }: { project: Project }) {
  const retry = useRetryProject(project.id)
  const canRetry = project.allowed_actions.includes('retry')
  return (
    <Card className="border-destructive/30">
      <CardHeader>
        <CardTitle>Something went wrong</CardTitle>
        <CardDescription>
          {canRetry
            ? 'Your documents and settings are safe. Try the step again, and it usually works.'
            : 'Your documents and settings are safe.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <Callout tone="destructive" role="alert" title="What happened">
          {project.status_message ?? 'The last step failed. You can try again.'}
        </Callout>
        <div className="flex flex-col gap-3 border-t pt-5 sm:flex-row sm:items-center">
          {canRetry && (
            <Button disabled={retry.isPending} onClick={() => retry.mutate(undefined, { onError: (err) => toast.error(err.message) })}>
              <RotateCw aria-hidden /> {retry.isPending ? 'Retrying…' : 'Retry'}
            </Button>
          )}
          <Link
            to="/docs"
            className="inline-flex items-center gap-1.5 rounded-md text-sm font-medium text-primary underline-offset-4 hover:underline"
          >
            <LifeBuoy className="size-4" aria-hidden /> Read the troubleshooting guide
          </Link>
        </div>
      </CardContent>
    </Card>
  )
}
