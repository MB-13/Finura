import { Link, useParams } from 'react-router'

import { ErrorState } from '@/components/ErrorState'
import { PageHeader } from '@/components/PageHeader'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError } from '@/lib/api/client'
import { useProject } from '@/features/projects/api'
import { ProjectHeader } from '@/features/projects/ProjectHeader'
import { ProjectPanel } from '@/features/projects/ProjectPanel'
import { ProjectStepper } from '@/features/projects/ProjectStepper'
import { useProjectEvents } from '@/lib/sse'

/** Step rail (desktop) / compact progress (mobile) next to the active panel. */
const LAYOUT = 'grid gap-6 lg:grid-cols-[11rem_minmax(0,1fr)] lg:gap-10'

export function ProjectWorkspace() {
  const { id = '' } = useParams()
  const project = useProject(id)
  useProjectEvents(id)

  if (project.isPending) {
    return (
      <div aria-busy="true" aria-label="Loading project" className="flex flex-col gap-6">
        <div className="flex flex-col gap-3">
          <Skeleton className="h-4 w-24" />
          <div className="flex items-center gap-3">
            <Skeleton className="h-8 w-64 max-w-full" />
            <Skeleton className="h-6 w-24 rounded-full" />
          </div>
          <Skeleton className="h-5 w-72 max-w-full" />
        </div>
        <div className={LAYOUT}>
          <Skeleton className="h-16 rounded-xl lg:h-72" />
          <div className="flex flex-col gap-4 rounded-xl border bg-card p-6 shadow-xs">
            <Skeleton className="h-6 w-1/3" />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-10 w-40" />
          </div>
        </div>
      </div>
    )
  }

  if (project.isError) {
    const notFound = project.error instanceof ApiError && project.error.status === 404
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title={notFound ? 'Project not found' : 'Project'} back={{ to: '/projects', label: 'All projects' }} />
        <ErrorState
          title={notFound ? 'This project does not exist' : undefined}
          message={notFound ? 'It may have been deleted, or the link is wrong.' : project.error.message}
          onRetry={notFound ? undefined : () => project.refetch()}
        />
        {notFound && (
          <Link to="/projects" className="w-fit text-sm font-medium text-primary underline underline-offset-4">
            Back to projects
          </Link>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <ProjectHeader project={project.data} />
      <div className={LAYOUT}>
        <ProjectStepper status={project.data.status} />
        <div className="min-w-0">
          <ProjectPanel project={project.data} />
        </div>
      </div>
    </div>
  )
}
