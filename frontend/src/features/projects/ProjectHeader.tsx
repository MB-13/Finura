import { MoreVertical, Pencil, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { useRenameProject, type Project } from '@/features/projects/api'
import { DeleteProjectDialog } from '@/features/projects/DeleteProjectDialog'
import { statusHint } from '@/features/projects/steps'

function RenameForm({ project, onDone }: { project: Project; onDone: () => void }) {
  const [name, setName] = useState(project.name)
  const rename = useRenameProject(project.id)

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed || trimmed === project.name) return onDone()
    rename.mutate(trimmed, {
      onSuccess: onDone,
      onError: (err) => toast.error(err.message),
    })
  }

  return (
    <form onSubmit={onSubmit} className="flex min-w-0 flex-1 basis-64 flex-wrap items-center gap-2">
      <Input
        autoFocus
        aria-label="Project name"
        value={name}
        maxLength={120}
        className="h-10 w-full max-w-md text-lg font-semibold"
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === 'Escape' && onDone()}
      />
      <Button type="submit" size="sm" disabled={rename.isPending}>
        Save
      </Button>
      <Button type="button" size="sm" variant="ghost" onClick={onDone}>
        Cancel
      </Button>
    </form>
  )
}

export function ProjectHeader({ project }: { project: Project }) {
  const [editing, setEditing] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const navigate = useNavigate()
  const renameButton = useRef<HTMLButtonElement>(null)
  const restoreFocus = useRef(false)
  const canRename = project.allowed_actions.includes('rename')
  const canDelete = project.allowed_actions.includes('delete')

  function stopEditing() {
    restoreFocus.current = true
    setEditing(false)
  }

  // the focused Save / Cancel / input unmount with the form, so hand focus back to the Rename button
  useEffect(() => {
    if (!editing && restoreFocus.current) {
      restoreFocus.current = false
      renameButton.current?.focus()
    }
  }, [editing])

  const actions = (
    <>
      {canRename && !editing && (
        <Button ref={renameButton} variant="outline" size="sm" aria-label="Rename project" onClick={() => setEditing(true)}>
          <Pencil aria-hidden /> <span aria-hidden className="max-sm:hidden">Rename</span>
        </Button>
      )}
      {canDelete && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="icon-sm" aria-label="Project actions">
              <MoreVertical aria-hidden />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem variant="destructive" onSelect={() => setConfirmDelete(true)}>
              <Trash2 aria-hidden /> Delete project
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </>
  )

  return (
    <>
      <PageHeader
        back={{ to: '/projects', label: 'All projects' }}
        title={project.name}
        editor={editing ? <RenameForm project={project} onDone={stopEditing} /> : undefined}
        badge={<StatusBadge status={project.status} />}
        description={statusHint[project.status]}
        actions={actions}
      />
      <DeleteProjectDialog
        project={confirmDelete ? project : null}
        onOpenChange={setConfirmDelete}
        onDeleted={() => void navigate('/projects')}
      />
    </>
  )
}
