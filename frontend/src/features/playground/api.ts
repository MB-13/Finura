import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/lib/api/client'
import type { components } from '@/lib/api/schema'
import { qk } from '@/lib/query-keys'

export type PlaygroundStatus = components['schemas']['PlaygroundStatus']
export type ChatMessage = components['schemas']['Message']
export type ChatOptions = Pick<components['schemas']['ChatIn'], 'use_rag' | 'compare_base' | 'temperature' | 'max_tokens'>

export const STATUS_POLL_MS = 3000

/** Playground status. Polls every ~3 s while the model is loading (or while `poll` is forced). */
const PREPARING_POLL_MS = 15_000

export function usePlaygroundStatus(projectId: string, { enabled = true, poll = false }: { enabled?: boolean; poll?: boolean } = {}) {
  return useQuery({
    queryKey: qk.playgroundStatus(projectId),
    enabled,
    queryFn: async () =>
      unwrap(await api.GET('/projects/{project_id}/playground/status', { params: { path: { project_id: projectId } } })),
    // also keep checking while the adapter is being converted, so the chat opens on its own
    refetchInterval: (query) => {
      const data = query.state.data
      if (poll || data?.state === 'warming') return STATUS_POLL_MS
      return data?.reason_code === 'preparing' ? PREPARING_POLL_MS : false
    },
  })
}

export function useWarmup(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      unwrap(await api.POST('/projects/{project_id}/playground/warmup', { params: { path: { project_id: projectId } } })),
    onSuccess: (status) => queryClient.setQueryData(qk.playgroundStatus(projectId), status),
  })
}
