import { Search } from 'lucide-react'
import { useId, useState } from 'react'

import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useChunks } from '@/features/documents/api'
import type { components } from '@/lib/api/schema'
import { useDebouncedValue } from '@/lib/useDebouncedValue'

type Chunk = components['schemas']['ChunkOut']

function pageRange(chunk: Chunk): string | null {
  if (chunk.page_start === null) return null
  if (chunk.page_end === null || chunk.page_end === chunk.page_start) return `p. ${chunk.page_start}`
  return `pp. ${chunk.page_start}-${chunk.page_end}`
}

function ChunkItem({ chunk }: { chunk: Chunk }) {
  const [expanded, setExpanded] = useState(false)
  const textId = useId()
  const pages = pageRange(chunk)
  return (
    <li className="flex flex-col gap-2 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-caption text-muted-foreground">
        <span className="font-medium text-foreground">{chunk.section_path || 'Untitled section'}</span>
        {pages && <span>{pages}</span>}
        <span>{chunk.token_count} tokens</span>
      </div>
      <p id={textId} className={expanded ? 'text-sm whitespace-pre-wrap' : 'line-clamp-3 text-sm whitespace-pre-wrap'}>
        {chunk.text}
      </p>
      <Button
        variant="link"
        size="sm"
        className="h-auto self-start p-0"
        aria-expanded={expanded}
        aria-controls={textId}
        onClick={() => setExpanded((v) => !v)}
      >
        {expanded ? 'Show less' : 'Show more'}
      </Button>
    </li>
  )
}

export function ChunkViewer({ projectId }: { projectId: string }) {
  const [search, setSearch] = useState('')
  const q = useDebouncedValue(search.trim(), 300)
  const chunks = useChunks(projectId, { q })
  const inputId = useId()
  const items = chunks.data?.pages.flatMap((p) => p.items) ?? []

  return (
    <section className="flex flex-col gap-3" aria-label="Document sections">
      <div className="flex flex-col gap-2">
        <Label htmlFor={inputId}>Search sections</Label>
        <div className="relative">
          <Search className="pointer-events-none absolute top-2.5 left-3 size-4 text-muted-foreground" aria-hidden />
          <Input
            id={inputId}
            type="search"
            className="pl-9"
            placeholder="Search your documents"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {chunks.isPending ? (
        <div aria-busy="true" aria-label="Loading sections" className="flex flex-col gap-2">
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
        </div>
      ) : chunks.isError ? (
        <ErrorState message={chunks.error.message} onRetry={() => chunks.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Search}
          title={q ? 'No sections match your search' : 'No sections yet'}
          description={q ? 'Try a different word.' : undefined}
        />
      ) : (
        <>
          <ul className="flex flex-col gap-2">
            {items.map((chunk) => (
              <ChunkItem key={chunk.id} chunk={chunk} />
            ))}
          </ul>
          {chunks.hasNextPage && (
            <Button variant="outline" className="self-center" disabled={chunks.isFetchingNextPage} onClick={() => chunks.fetchNextPage()}>
              {chunks.isFetchingNextPage ? 'Loading…' : 'Load more'}
            </Button>
          )}
        </>
      )}
    </section>
  )
}
