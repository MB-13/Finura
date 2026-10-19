import { AlertTriangle, CheckCircle2, Loader2, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Callout } from '@/components/Callout'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { useDeleteDocument, useDocuments, useUploadDocument, type UploadItem } from '@/features/documents/api'
import { FileDropzone } from '@/features/documents/FileDropzone'
import { FileRow } from '@/features/documents/FileRow'
import { formatMb, validateFile } from '@/features/documents/upload'
import { useMeta } from '@/features/meta/api'
import { useProcessProject, type Project } from '@/features/projects/api'
import { formatBytes } from '@/lib/format'
import { cn } from '@/lib/utils'

const DEFAULT_LIMITS = { file_mb: 20, project_mb: 50 }
const MB = 1024 * 1024

function uploadLabel(item: UploadItem): string {
  switch (item.state) {
    case 'uploading':
      return `Uploading ${item.progress}%`
    case 'confirming':
      return 'Checking file…'
    case 'done':
      return 'Uploaded'
    case 'error':
      return item.error ?? 'Upload failed'
  }
}

type Props = {
  project: Project
  /** Render without the surrounding card/title (inside another card). */
  embedded?: boolean
}

export function UploadPanel({ project, embedded = false }: Props) {
  const meta = useMeta()
  const limits = meta.data?.limits ?? DEFAULT_LIMITS
  const documents = useDocuments(project.id)
  const uploads = useUploadDocument(project.id)
  const removeDoc = useDeleteDocument(project.id)
  const process = useProcessProject(project.id)
  const [rejections, setRejections] = useState<string[]>([])

  const can = (action: string) => project.allowed_actions.includes(action)
  const canUpload = can('upload')
  const inFlightBytes = uploads.items
    .filter((i) => i.state === 'uploading' || i.state === 'confirming')
    .reduce((sum, i) => sum + i.size, 0)
  const usedPercent = Math.min(100, (project.total_bytes / (limits.project_mb * MB)) * 100)

  function onFiles(files: File[]) {
    const accepted: File[] = []
    const errors: string[] = []
    let used = project.total_bytes + inFlightBytes
    for (const file of files) {
      const problem = validateFile(file, limits, used)
      if (problem) errors.push(problem)
      else {
        accepted.push(file)
        used += file.size
      }
    }
    setRejections(errors)
    if (accepted.length > 0) void uploads.upload(accepted)
  }

  const visibleUploads = uploads.items.filter((i) => i.state !== 'done')
  const finished = uploads.items.filter((i) => i.state === 'done').length
  const live = uploads.isUploading
    ? `Uploading, ${finished} of ${uploads.items.length} files done`
    : finished > 0
      ? `${finished} ${finished === 1 ? 'file' : 'files'} uploaded`
      : ''
  const docs = (documents.data ?? []).filter((d) => !(uploads.isUploading && d.status === 'pending_upload'))

  const body = (
    <div className="flex flex-col gap-5">
      <FileDropzone
        onFiles={onFiles}
        disabled={!canUpload}
        hint={canUpload ? `PDF, DOCX, TXT or MD · up to ${limits.file_mb} MB each` : 'Uploads are closed for this project.'}
      />

      <div className="flex flex-col gap-1.5">
        <div className="flex items-baseline justify-between gap-3 text-sm">
          <span className="font-medium">Project size</span>
          <span className="text-metric text-xs text-muted-foreground">
            {formatMb(project.total_bytes)} / {limits.project_mb} MB
          </span>
        </div>
        <Progress
          value={usedPercent}
          aria-label="Project size used"
          indicatorClassName={cn(usedPercent >= 90 && 'bg-warning')}
        />
      </div>

      <div role="status" aria-live="polite" className="sr-only">
        {live}
      </div>

      {rejections.length > 0 && (
        <Callout tone="destructive" role="alert" title="Some files were not added">
          <ul className="list-inside list-disc">
            {rejections.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </Callout>
      )}

      {documents.isPending ? (
        <div aria-busy="true" aria-label="Loading documents" className="flex flex-col gap-2">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      ) : documents.isError ? (
        <ErrorState message={documents.error.message} onRetry={() => documents.refetch()} />
      ) : docs.length === 0 && visibleUploads.length === 0 ? (
        <p className="rounded-xl border border-dashed px-4 py-5 text-center text-sm text-muted-foreground">
          No documents yet. Add at least one to continue.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          <h3 className="text-eyebrow">
            Your documents ({docs.length + visibleUploads.length})
          </h3>
          <ul className="divide-y border-y" aria-label="Documents">
            {visibleUploads.map((item) => (
              <FileRow
                key={item.key}
                filename={item.filename}
                tone={item.state === 'error' ? 'error' : 'default'}
                meta={
                  <span className="inline-flex items-center gap-1">
                    {item.state === 'error' && <AlertTriangle className="size-3.5 shrink-0" aria-hidden />}
                    {uploadLabel(item)}
                  </span>
                }
                trailing={
                  item.state === 'error' ? (
                    <Button variant="ghost" size="icon" className="size-8" aria-label={`Dismiss ${item.filename}`} onClick={() => uploads.dismiss(item.key)}>
                      <X aria-hidden />
                    </Button>
                  ) : (
                    <Loader2 className="size-4 text-primary motion-safe:animate-spin" aria-hidden />
                  )
                }
              >
                {item.state !== 'error' && (
                  <Progress value={item.progress} className="h-1.5" aria-label={`Upload progress for ${item.filename}`} />
                )}
              </FileRow>
            ))}
            {docs.map((doc) => (
              <FileRow
                key={doc.id}
                filename={doc.filename}
                tone={doc.status === 'failed' ? 'error' : 'default'}
                meta={
                  <>
                    {formatBytes(doc.size_bytes)}
                    {doc.status === 'pending_upload' && ' · upload incomplete'}
                    {doc.status === 'failed' && ` · ${doc.error ?? 'failed'}`}
                  </>
                }
                trailing={
                  <>
                    {doc.status === 'uploaded' && (
                      <span className="hidden items-center gap-1 text-caption text-success-muted-foreground sm:inline-flex">
                        <CheckCircle2 className="size-3.5" aria-hidden /> Uploaded
                      </span>
                    )}
                    {can('remove_document') && (
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Remove ${doc.filename}`}
                        disabled={removeDoc.isPending}
                        onClick={() => removeDoc.mutate(doc.id, { onError: (err) => toast.error(err.message) })}
                      >
                        <Trash2 aria-hidden />
                      </Button>
                    )}
                  </>
                }
              />
            ))}
          </ul>
        </div>
      )}

      {can('process') && (
        <div className="flex flex-col gap-3 border-t pt-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">
            Next, we read your files and split them into sections. Then you describe how the model should answer.
          </p>
          <Button
            className="shrink-0"
            disabled={process.isPending || uploads.isUploading}
            onClick={() => process.mutate(undefined, { onError: (err) => toast.error(err.message) })}
          >
            {process.isPending ? 'Starting…' : 'Process documents'}
          </Button>
        </div>
      )}
    </div>
  )

  if (embedded) return body

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upload your documents</CardTitle>
        <CardDescription>
          These are what your model learns to answer from. PDF, DOCX, TXT or Markdown, up to {limits.file_mb} MB per file and{' '}
          {limits.project_mb} MB per project.
        </CardDescription>
      </CardHeader>
      <CardContent>{body}</CardContent>
    </Card>
  )
}
