import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/lib/api/client'
import type { components } from '@/lib/api/schema'
import { qk } from '@/lib/query-keys'

export type Provider = components['schemas']['Provider']
export type ProviderInfo = components['schemas']['ProviderOut']
export type ProviderKey = components['schemas']['ProviderKeyOut']
export type KeyStatus = components['schemas']['KeyStatus']

/** Verification runs async on the server: poll every 2 s for up to 20 s while a key is unverified. */
const POLL_INTERVAL_MS = 2000
const POLL_WINDOW_MS = 20_000

export function startKeyPolling(queryClient: QueryClient) {
  queryClient.setQueryData(qk.keysPollUntil(), Date.now() + POLL_WINDOW_MS)
}

export function useProviders() {
  return useQuery({
    queryKey: qk.providers(),
    staleTime: 5 * 60_000,
    queryFn: async () => unwrap(await api.GET('/providers')),
  })
}

export function useKeys() {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: qk.keys(),
    queryFn: async () => unwrap(await api.GET('/keys')),
    refetchInterval: (query) => {
      const until = queryClient.getQueryData<number>(qk.keysPollUntil()) ?? 0
      const pending = query.state.data?.some((k) => k.status === 'unverified') ?? false
      return pending && Date.now() < until ? POLL_INTERVAL_MS : false
    },
  })
}

function useKeyMutation<V, R>(fn: (vars: V) => Promise<R>, poll: boolean) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      if (poll) startKeyPolling(queryClient)
      void queryClient.invalidateQueries({ queryKey: qk.keys() })
    },
  })
}

export function useSaveKey() {
  return useKeyMutation(
    async (v: { provider: Provider; body: components['schemas']['KeyPut'] }) =>
      unwrap(await api.PUT('/keys/{provider}', { params: { path: { provider: v.provider } }, body: v.body })),
    true,
  )
}

export function usePatchKey() {
  return useKeyMutation(
    async (v: { provider: Provider; body: components['schemas']['KeyPatch'] }) =>
      unwrap(await api.PATCH('/keys/{provider}', { params: { path: { provider: v.provider } }, body: v.body })),
    false,
  )
}

export function useDeleteKey() {
  return useKeyMutation(async (provider: Provider) => {
    unwrap(await api.DELETE('/keys/{provider}', { params: { path: { provider } } }))
  }, false)
}

export function useVerifyKey() {
  return useKeyMutation(
    async (provider: Provider) => unwrap(await api.POST('/keys/{provider}/verify', { params: { path: { provider } } })),
    true,
  )
}
