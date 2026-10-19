import { Link, useParams } from 'react-router'

import { ErrorState } from '@/components/ErrorState'
import { Skeleton } from '@/components/ui/skeleton'
import { ReviewTable } from '@/features/dataset/ReviewTable'
import { useProject } from '@/features/projects/api'
import { ApiError } from '@/lib/api/client'
import { useProjectEvents } from '@/lib/sse'

export function DatasetReview() {
  const { id = '' } = useParams()
  const project = useProject(id)
  useProjectEvents(id)

  if (project.isPending) {
    return (
      <div aria-busy="true" aria-label="Loading project" className="flex flex-col gap-6">
        <div className="flex flex-col gap-3">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-9 w-64" />
        </div>
        <Skeleton className="h-20 rounded-xl" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    )
  }
  if (project.isError) {
    const notFound = project.error instanceof ApiError && project.error.status === 404
    return (
      <div className="flex flex-col gap-6">
        <ErrorState
          title={notFound ? 'Project not found' : undefined}
          message={project.error.message}
          onRetry={notFound ? undefined : () => project.refetch()}
        />
        <Link to="/projects" className="w-fit text-sm font-medium text-primary underline underline-offset-4">
          Back to projects
        </Link>
      </div>
    )
  }
  return <ReviewTable project={project.data} />
}
