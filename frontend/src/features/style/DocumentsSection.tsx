import { ChevronDown, ChevronRight, FileText } from 'lucide-react'
import { useId, useState } from 'react'

import { ChunkViewer } from '@/features/documents/ChunkViewer'
import { UploadPanel } from '@/features/documents/UploadPanel'
import type { Project } from '@/features/projects/api'

/** Collapsible: add more documents and check how they were split. Content mounts only when opened. */
export function DocumentsSection({ project }: { project: Project }) {
  const [open, setOpen] = useState(false)
  const bodyId = useId()
  const { documents, chunks } = project.counts
  const Chevron = open ? ChevronDown : ChevronRight

  return (
    <section className="flex flex-col gap-4">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 rounded-xl border bg-card p-4 text-left shadow-xs transition-colors outline-none hover:bg-accent/40 focus-visible:ring-[3px] focus-visible:ring-ring/50 sm:px-5"
      >
        <span aria-hidden className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
          <FileText className="size-5" />
        </span>
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="text-card-title">Documents</span>
          <span className="text-sm text-muted-foreground">
            {documents} {documents === 1 ? 'document' : 'documents'} split into {chunks} {chunks === 1 ? 'section' : 'sections'}.
            Open to add more or check the text.
          </span>
        </span>
        <Chevron className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      </button>
      <div id={bodyId} hidden={!open} className="flex flex-col gap-6">
        {open && (
          <>
            <UploadPanel project={project} embedded />
            <ChunkViewer projectId={project.id} />
          </>
        )}
      </div>
    </section>
  )
}
