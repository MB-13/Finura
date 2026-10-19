import { AlertTriangle, CheckCircle2, Clock, Loader2 } from 'lucide-react'

import { ErrorState } from '@/components/ErrorState'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { useDocuments, type DocumentWithChunks } from '@/features/documents/api'
import { FileRow } from '@/features/documents/FileRow'
import type { Project } from '@/features/projects/api'
import { cn } from '@/lib/utils'

const statusLabel: Record<DocumentWithChunks['status'], string> = {
  pending_upload: 'Waiting for upload',
  uploaded: 'Queued',
  parsing: 'Reading…',
  parsed: 'Done',
  failed: 'Failed',
}

function StatusChip({ status }: { status: DocumentWithChunks['status'] }) {
  const Icon = status === 'parsed' ? CheckCircle2 : status === 'failed' ? AlertTriangle : status === 'parsing' ? Loader2 : Clock
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap',
        status === 'parsed' && 'bg-success-muted text-success-muted-foreground',
        status === 'failed' && 'bg-destructive-muted text-destructive-muted-foreground',
        status === 'parsing' && 'bg-info-muted text-info-muted-foreground',
        (status === 'uploaded' || status === 'pending_upload') && 'bg-muted text-muted-foreground',
      )}
    >
      <Icon className={cn('size-3.5', status === 'parsing' && 'motion-safe:animate-spin')} aria-hidden />
      {statusLabel[status]}
    </span>
  )
}

export function ProcessingPanel({ project }: { project: Project }) {
  const documents = useDocuments(project.id)
  const docs = documents.data ?? []
  const done = docs.filter((d) => d.status === 'parsed').length
  const percent = docs.length > 0 ? Math.round((done / docs.length) * 100) : 0

  return (
    <Card>
      <CardHeader>
        <CardTitle>Reading your documents</CardTitle>
        <CardDescription>
          We&apos;re extracting the text and splitting it into sections. This page updates by itself, so you can leave it open or come back later.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <div className="flex flex-col gap-1.5">
          <div role="status" aria-live="polite" className="text-sm font-medium">
            {documents.isSuccess ? `${done} of ${docs.length} documents processed` : 'Checking your documents…'}
          </div>
          <Progress value={percent} aria-label="Documents processed" />
        </div>
        {documents.isPending ? (
          <div aria-busy="true" aria-label="Loading documents" className="flex flex-col gap-2">
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
          </div>
        ) : documents.isError ? (
          <ErrorState message={documents.error.message} onRetry={() => documents.refetch()} />
        ) : docs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No documents found for this project.</p>
        ) : (
          <ul className="divide-y border-y" aria-label="Document processing status">
            {docs.map((doc) => (
              <FileRow
                key={doc.id}
                filename={doc.filename}
                tone={doc.status === 'failed' ? 'error' : 'default'}
                meta={[
                  doc.page_count !== null ? `${doc.page_count} pages` : null,
                  doc.ocr_pages > 0 ? `${doc.ocr_pages} read with OCR` : null,
                  doc.status === 'parsed' ? `${doc.chunk_count} sections` : null,
                  doc.status === 'failed' ? doc.error : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
                trailing={<StatusChip status={doc.status} />}
              />
            ))}
          </ul>
        )}
        <p className="text-sm text-muted-foreground">Next: you&apos;ll describe how your model should answer.</p>
      </CardContent>
    </Card>
  )
}
