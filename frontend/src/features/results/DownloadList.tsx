import { Download, FileArchive, FileCode2 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { toast } from 'sonner'

import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useArtifactDownload, useArtifacts, type Artifact } from '@/features/training/api'
import { formatBytes } from '@/lib/format'
import { useNow } from '@/lib/useNow'

const KIND_COPY: Partial<Record<Artifact['kind'], { name: string; help: string; icon: LucideIcon }>> = {
  adapter_safetensors: { name: 'LoRA adapter (zip)', help: 'A small file with what your model learned. Use it with the original base model.', icon: FileArchive },
  adapter_gguf: { name: 'Adapter for llama.cpp (GGUF)', help: 'The same adapter in GGUF format, for llama.cpp and Ollama.', icon: FileCode2 },
}

export function DownloadList({ projectId }: { projectId: string }) {
  const artifacts = useArtifacts(projectId)
  const download = useArtifactDownload(projectId)
  const now = useNow(60_000)

  if (artifacts.isPending)
    return (
      <div aria-busy="true" aria-label="Loading downloads" className="flex flex-col gap-3">
        <Skeleton className="h-14" />
        <Skeleton className="h-14" />
      </div>
    )
  if (artifacts.isError) return <ErrorState message={artifacts.error.message} onRetry={() => artifacts.refetch()} />

  const items = artifacts.data.filter((a) => KIND_COPY[a.kind])
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">No files to download yet. They appear here once training has uploaded them.</p>
  }

  return (
    <ul className="flex flex-col divide-y" aria-label="Downloads">
      {items.map((a) => {
        const copy = KIND_COPY[a.kind]!
        const Icon = copy.icon
        const expired = a.expires_at !== null && new Date(a.expires_at).getTime() < now
        const busy = download.isPending && download.variables === a.id
        return (
          <li key={a.id} className="flex flex-wrap items-center gap-x-4 gap-y-3 py-3.5 first:pt-0 last:pb-0">
            <Icon className="size-5 shrink-0 text-muted-foreground" strokeWidth={1.5} aria-hidden />
            <div className="min-w-0 flex-1 basis-56">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-card-title">{copy.name}</span>
                <span className="text-metric text-xs text-muted-foreground">{formatBytes(a.size_bytes)}</span>
              </div>
              <p className="mt-0.5 text-caption text-muted-foreground">
                {expired ? 'This file has expired and was deleted.' : copy.help}
                {!expired && a.expires_at && ` Available until ${new Date(a.expires_at).toLocaleDateString()}.`}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={expired || busy}
              aria-label={`Download ${copy.name}`}
              onClick={() =>
                download.mutate(a.id, {
                  onSuccess: ({ url }) => window.open(url, '_blank', 'noopener,noreferrer'),
                  onError: (err) => toast.error(err.message),
                })
              }
            >
              <Download aria-hidden /> {busy ? 'Preparing…' : 'Download'}
            </Button>
          </li>
        )
      })}
    </ul>
  )
}
