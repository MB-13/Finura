import { MoreVertical, Trash2 } from 'lucide-react'
import { Link } from 'react-router'

import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import type { ProjectSummary } from '@/features/projects/api'
import { STEPS, statusHint, stepIndexByStatus } from '@/features/projects/steps'
import { formatRelative } from '@/lib/format'
import { cn } from '@/lib/utils'

export type ProjectLayout = 'list' | 'grid'

type Props = { project: ProjectSummary; onDelete: (project: ProjectSummary) => void; layout?: ProjectLayout }

/** Six quiet segments, one per step: done = brand, current = half brand, later = muted. */
function StepStrip({ project, index, complete, failed }: { project: ProjectSummary; index: number | null; complete: boolean; failed: boolean }) {
  const done = complete ? STEPS.length : (index ?? 0)
  const label = failed ? 'Needs attention' : complete ? 'All steps complete' : `Step ${done + 1} of ${STEPS.length}`
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div
        role="progressbar"
        aria-label={`${project.name} progress`}
        aria-valuemin={0}
        aria-valuemax={STEPS.length}
        aria-valuenow={failed ? 0 : done}
        aria-valuetext={label}
        className="flex gap-1"
      >
        {STEPS.map((step, i) => (
          <span
            key={step}
            aria-hidden
            className={cn(
              'h-1 min-w-0 flex-1 rounded-full',
              failed ? 'bg-destructive/25' : i < done ? 'bg-primary' : i === done ? 'bg-primary/40' : 'bg-border',
            )}
          />
        ))}
      </div>
      <span className="truncate font-mono text-[0.6875rem] text-muted-foreground tabular-nums">
        {failed ? label : complete ? label : `${done + 1}/${STEPS.length} · ${STEPS[done]}`}
      </span>
    </div>
  )
}

export function ProjectCard({ project, onDelete, layout = 'grid' }: Props) {
  const idx = stepIndexByStatus[project.status]
  const failed = project.status === 'failed'
  const complete = project.status === 'ready'
  const hint = failed && project.status_message ? project.status_message : statusHint[project.status]
  const model = project.base_model_id?.split('/').pop()

  const menu = (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative z-10 size-8 shrink-0 text-muted-foreground" aria-label={`Actions for ${project.name}`}>
          <MoreVertical aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem variant="destructive" onSelect={() => onDelete(project)}>
          <Trash2 aria-hidden /> Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
  const updated = (
    <time dateTime={project.updated_at} className="font-mono text-[0.75rem] whitespace-nowrap text-muted-foreground tabular-nums">
      <span className="sr-only">Updated </span>
      {formatRelative(project.updated_at)}
    </time>
  )
  const title = (
    <Link
      to={`/projects/${project.id}`}
      className="rounded-sm outline-none after:absolute after:inset-0 after:content-[''] focus-visible:after:ring-[3px] focus-visible:after:ring-ring/50 focus-visible:after:ring-inset"
    >
      {project.name}
    </Link>
  )

  if (layout === 'list') {
    return (
      <div className="group relative grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-3 px-4 py-3.5 transition-colors hover:bg-accent/40 md:grid-cols-[minmax(0,1fr)_7.5rem_9.5rem_8rem_5rem_2rem] md:gap-x-5">
        <div className="min-w-0">
          <h2 className="truncate text-card-title">{title}</h2>
          <p className="mt-0.5 truncate text-caption text-muted-foreground">{hint}</p>
        </div>
        <div className="col-span-2 flex items-center gap-3 md:contents">
          <StatusBadge status={project.status} />
          <span className="ml-auto md:hidden">{updated}</span>
        </div>
        <div className="col-span-2 md:col-span-1">
          <StepStrip project={project} index={idx} complete={complete} failed={failed} />
        </div>
        <span className="hidden truncate font-mono text-[0.75rem] text-muted-foreground md:block" title={project.base_model_id ?? undefined}>
          {model ?? 'No model yet'}
        </span>
        <span className="hidden text-right md:block">{updated}</span>
        <div className="col-start-2 row-start-1 -mr-2 md:col-auto md:row-auto md:mr-0">{menu}</div>
      </div>
    )
  }

  return (
    <div className="group relative flex h-full flex-col gap-3 rounded-xl border bg-card p-4 shadow-card transition-colors hover:border-primary/40 focus-within:ring-[3px] focus-within:ring-ring/50">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-1.5">
          <span className="text-eyebrow truncate">{model ?? 'No model yet'}</span>
          <h2 className="min-w-0 truncate text-card-title">{title}</h2>
        </div>
        <div className="-mt-1 -mr-2">{menu}</div>
      </div>
      <p className="line-clamp-2 text-sm text-muted-foreground">{hint}</p>
      <div className="mt-auto flex flex-col gap-3">
        <StepStrip project={project} index={idx} complete={complete} failed={failed} />
        <div className="flex items-center justify-between gap-3 border-t pt-3">
          <StatusBadge status={project.status} />
          {updated}
        </div>
      </div>
    </div>
  )
}
