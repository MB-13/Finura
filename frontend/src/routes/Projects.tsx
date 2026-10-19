import { FileText, LayoutGrid, List, MessageSquare, Plus, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'
import { Navigate, useLocation } from 'react-router'

import { ErrorState } from '@/components/ErrorState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useMe } from '@/features/me/api'
import { useProjects, type ProjectSummary } from '@/features/projects/api'
import { DeleteProjectDialog } from '@/features/projects/DeleteProjectDialog'
import { NewProjectDialog } from '@/features/projects/NewProjectDialog'
import { ProjectCard, type ProjectLayout } from '@/features/projects/ProjectCard'
import { cn } from '@/lib/utils'

const LAYOUT_KEY = 'doctune-projects-layout'

function readLayout(): ProjectLayout {
  try {
    return localStorage.getItem(LAYOUT_KEY) === 'grid' ? 'grid' : 'list'
  } catch {
    return 'list'
  }
}

const FLOW = [
  { icon: FileText, label: 'Upload', text: 'Add your documents' },
  { icon: SlidersHorizontal, label: 'Style', text: 'Describe the answers' },
  { icon: MessageSquare, label: 'Chat', text: 'Try your model' },
]

function LayoutToggle({ value, onChange }: { value: ProjectLayout; onChange: (v: ProjectLayout) => void }) {
  const options = [
    { v: 'list' as const, label: 'List view', icon: List },
    { v: 'grid' as const, label: 'Grid view', icon: LayoutGrid },
  ]
  return (
    <div role="group" aria-label="Layout" className="inline-flex rounded-md border p-0.5">
      {options.map(({ v, label, icon: Icon }) => (
        <button
          key={v}
          type="button"
          aria-label={label}
          aria-pressed={value === v}
          onClick={() => onChange(v)}
          className={cn(
            'flex size-7 items-center justify-center rounded-sm outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50',
            value === v ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          <Icon className="size-4" aria-hidden />
        </button>
      ))}
    </div>
  )
}

export function Projects() {
  const projects = useProjects()
  const me = useMe()
  const location = useLocation()
  const [newOpen, setNewOpen] = useState(false)
  const [toDelete, setToDelete] = useState<ProjectSummary | null>(null)
  const [layout, setLayout] = useState<ProjectLayout>(readLayout)
  function changeLayout(next: ProjectLayout) {
    setLayout(next)
    try {
      localStorage.setItem(LAYOUT_KEY, next)
    } catch {
      // layout just will not persist
    }
  }
  const items = projects.data?.pages.flatMap((page) => page.items) ?? []

  // first sign-in: show onboarding once (finishing or skipping it sets onboarding_done)
  const skipped = (location.state as { skipOnboarding?: boolean } | null)?.skipOnboarding === true
  if (me.data && !me.data.onboarding_done && !skipped) return <Navigate to="/onboarding" replace />

  const newButton = (
    <Button onClick={() => setNewOpen(true)}>
      <Plus aria-hidden /> New project
    </Button>
  )
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Projects"
        description="Each project turns a set of documents into a model that answers in your style."
        actions={newButton}
      />

      {projects.isPending ? (
        <ul aria-busy="true" aria-label="Loading projects" className="divide-y rounded-xl border bg-card shadow-card">
          {[0, 1, 2, 3].map((i) => (
            <li key={i} className="flex items-center gap-4 px-4 py-3.5">
              <div className="flex min-w-0 flex-1 flex-col gap-2">
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className="h-3 w-2/3" />
              </div>
              <Skeleton className="hidden h-5 w-24 rounded-full sm:block" />
              <Skeleton className="hidden h-2 w-36 md:block" />
            </li>
          ))}
        </ul>
      ) : projects.isError ? (
        <ErrorState title="Couldn't load your projects" message={projects.error.message} onRetry={() => projects.refetch()} />
      ) : items.length === 0 ? (
        <section aria-label="Get started" className="overflow-hidden rounded-xl border bg-card shadow-card">
          <div className="flex flex-col items-start gap-4 p-6 sm:p-8">
            <span className="text-eyebrow">Get started</span>
            <div className="flex max-w-xl flex-col gap-2">
              <h2 className="text-section-title">No projects yet</h2>
              <p className="text-body text-muted-foreground">
                Upload your documents, describe how the model should answer, and train it on your own free GPU. Fine-tuning teaches style; facts come from your documents in the playground.
              </p>
            </div>
            <Button size="lg" onClick={() => setNewOpen(true)}>
              <Plus aria-hidden /> Create your first project
            </Button>
          </div>
          <ol className="grid divide-y border-t sm:grid-cols-3 sm:divide-x sm:divide-y-0">
            {FLOW.map(({ icon: Icon, label, text }, i) => (
              <li key={label} className="flex items-center gap-3 px-6 py-4 sm:px-8">
                <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                <div className="min-w-0">
                  <div className="text-eyebrow">
                    <span className="tabular-nums">0{i + 1}</span> · {label}
                  </div>
                  <div className="text-sm">{text}</div>
                </div>
              </li>
            ))}
          </ol>
        </section>
      ) : (
        <>
          <div className="flex items-center justify-between gap-3">
            <span className="text-eyebrow">
              <span className="tabular-nums">{items.length}</span> {items.length === 1 ? 'project' : 'projects'}
              {projects.hasNextPage ? '+' : ''}
            </span>
            <LayoutToggle value={layout} onChange={changeLayout} />
          </div>
          {layout === 'list' ? (
            <ul className="divide-y overflow-hidden rounded-xl border bg-card shadow-card">
              {items.map((project) => (
                <li key={project.id}>
                  <ProjectCard project={project} onDelete={setToDelete} layout="list" />
                </li>
              ))}
            </ul>
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {items.map((project) => (
                <li key={project.id}>
                  <ProjectCard project={project} onDelete={setToDelete} layout="grid" />
                </li>
              ))}
            </ul>
          )}
          {projects.hasNextPage && (
            <Button
              variant="outline"
              className="self-center"
              disabled={projects.isFetchingNextPage}
              onClick={() => projects.fetchNextPage()}
            >
              {projects.isFetchingNextPage ? 'Loading…' : 'Load more'}
            </Button>
          )}
        </>
      )}

      <NewProjectDialog open={newOpen} onOpenChange={setNewOpen} />
      <DeleteProjectDialog project={toDelete} onOpenChange={(open) => !open && setToDelete(null)} />
    </div>
  )
}
