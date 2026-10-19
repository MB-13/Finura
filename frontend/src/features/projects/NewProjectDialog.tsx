import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useCreateProject } from '@/features/projects/api'
import { ApiError } from '@/lib/api/client'

type Props = { open: boolean; onOpenChange: (open: boolean) => void }

/** Controlled by the page so the "New project" buttons (header, empty state) share one dialog. */
export function NewProjectDialog({ open, onOpenChange: setOpen }: Props) {
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const create = useCreateProject()
  const navigate = useNavigate()

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      setError('Give your project a name.')
      return
    }
    setError(null)
    create.mutate(trimmed, {
      onSuccess: (project) => {
        setOpen(false)
        setName('')
        void navigate(`/projects/${project.id}`)
      },
      onError: (err) => {
        setError(err instanceof ApiError ? (err.fieldErrors['name']?.[0] ?? err.message) : err.message)
      },
    })
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) setError(null)
      }}
    >
      <DialogContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
          <DialogHeader>
            <DialogTitle>New project</DialogTitle>
            <DialogDescription>A project holds your documents and the model you train from them.</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="project-name">Project name</Label>
            <Input
              id="project-name"
              value={name}
              maxLength={120}
              autoComplete="off"
              autoFocus
              placeholder="e.g. Customer support bot"
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? 'project-name-error' : undefined}
              onChange={(e) => setName(e.target.value)}
            />
            <p className="text-caption text-muted-foreground">Next you&apos;ll upload the documents your model should learn from.</p>
            {error && (
              <p id="project-name-error" role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? 'Creating…' : 'Create project'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
