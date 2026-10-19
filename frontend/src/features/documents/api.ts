import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'

import { putToSignedUrl, type DocumentWithChunks } from '@/features/documents/upload'
import { api, unwrap } from '@/lib/api/client'
import { qk, type ChunkParams } from '@/lib/query-keys'

export type { DocumentWithChunks }

export function useDocuments(projectId: string) {
  return useQuery({
    queryKey: qk.documents(projectId),
    queryFn: async () =>
      unwrap(await api.GET('/projects/{project_id}/documents', { params: { path: { project_id: projectId } } })),
  })
}

export function useDeleteDocument(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (documentId: string) => {
      unwrap(
        await api.DELETE('/projects/{project_id}/documents/{document_id}', {
          params: { path: { project_id: projectId, document_id: documentId } },
        }),
      )
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.documents(projectId) })
      void queryClient.invalidateQueries({ queryKey: qk.project(projectId) })
    },
  })
}

const CHUNK_PAGE_SIZE = 20

export function useChunks(projectId: string, params: ChunkParams = {}) {
  return useInfiniteQuery({
    queryKey: qk.chunks(projectId, params),
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET('/projects/{project_id}/chunks', {
          params: {
            path: { project_id: projectId },
            query: {
              document_id: params.documentId,
              q: params.q || undefined,
              limit: CHUNK_PAGE_SIZE,
              cursor: pageParam,
            },
          },
        }),
      ),
    // opaque cursor: pass next_cursor straight back
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
}

export type UploadState = 'uploading' | 'confirming' | 'done' | 'error'
export type UploadItem = {
  key: string
  filename: string
  size: number
  progress: number
  state: UploadState
  error?: string
}

let counter = 0

/** Upload flow per file: create document -> PUT to R2 (progress) -> confirm with API. */
export function useUploadDocument(projectId: string) {
  const queryClient = useQueryClient()
  const [items, setItems] = useState<UploadItem[]>([])

  const patch = useCallback((key: string, change: Partial<UploadItem>) => {
    setItems((all) => all.map((item) => (item.key === key ? { ...item, ...change } : item)))
  }, [])

  const mutation = useMutation({
    mutationFn: async ({ file, key }: { file: File; key: string }) => {
      const created = unwrap(
        await api.POST('/projects/{project_id}/documents', {
          params: { path: { project_id: projectId } },
          body: { filename: file.name, size_bytes: file.size },
        }),
      )
      await putToSignedUrl(created.upload, file, (progress) => patch(key, { progress }))
      patch(key, { state: 'confirming', progress: 100 })
      return unwrap(
        await api.POST('/projects/{project_id}/documents/{document_id}/complete', {
          params: { path: { project_id: projectId, document_id: created.document.id } },
        }),
      )
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: qk.documents(projectId) })
      void queryClient.invalidateQueries({ queryKey: qk.project(projectId) })
    },
  })

  const upload = useCallback(
    async (files: File[]) => {
      const queued = files.map((file) => ({
        file,
        item: { key: `upload-${++counter}`, filename: file.name, size: file.size, progress: 0, state: 'uploading' as const },
      }))
      setItems((all) => [...all, ...queued.map((q) => q.item)])
      // sequential keeps progress readable and the server-side project cap check deterministic
      for (const { file, item } of queued) {
        try {
          await mutation.mutateAsync({ file, key: item.key })
          patch(item.key, { state: 'done' })
        } catch (err) {
          patch(item.key, { state: 'error', error: err instanceof Error ? err.message : 'Upload failed' })
        }
      }
    },
    [mutation, patch],
  )

  const dismiss = useCallback((key: string) => setItems((all) => all.filter((i) => i.key !== key)), [])
  const clearFinished = useCallback(() => setItems((all) => all.filter((i) => i.state === 'uploading' || i.state === 'confirming')), [])

  return { items, upload, dismiss, clearFinished, isUploading: items.some((i) => i.state === 'uploading' || i.state === 'confirming') }
}
