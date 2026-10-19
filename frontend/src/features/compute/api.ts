import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/lib/api/client'
import type { components } from '@/lib/api/schema'
import { qk } from '@/lib/query-keys'

export type KaggleAccount = components['schemas']['KaggleAccountOut']
export type KaggleStatus = KaggleAccount['status']

/** Validation runs in a worker: poll every 2 s for up to 60 s while the status is `unchecked`. */
export const KAGGLE_POLL_INTERVAL_MS = 2000
export const KAGGLE_POLL_WINDOW_MS = 60_000

export function startKagglePolling(queryClient: QueryClient) {
  queryClient.setQueryData(qk.kagglePollUntil(), Date.now() + KAGGLE_POLL_WINDOW_MS)
}

/** `null` means no Kaggle account is connected. */
export function useKaggle(enabled = true) {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: qk.kaggle(),
    enabled,
    queryFn: async (): Promise<KaggleAccount | null> => unwrap(await api.GET('/compute/kaggle')) ?? null,
    refetchInterval: (query) => {
      if (query.state.data?.status !== 'unchecked') return false
      let until = queryClient.getQueryData<number>(qk.kagglePollUntil())
      if (until === undefined) {
        startKagglePolling(queryClient) // page opened while a check was already running
        until = Date.now() + KAGGLE_POLL_WINDOW_MS
      }
      return Date.now() < until ? KAGGLE_POLL_INTERVAL_MS : false
    },
  })
}

export function useConnectKaggle() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: components['schemas']['KaggleAccountPut']) => unwrap(await api.PUT('/compute/kaggle', { body })),
    onSuccess: (account) => {
      startKagglePolling(queryClient)
      queryClient.setQueryData(qk.kaggle(), account)
    },
  })
}

export function useRecheckKaggle() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => unwrap(await api.POST('/compute/kaggle/check')),
    onSuccess: (account) => {
      startKagglePolling(queryClient)
      queryClient.setQueryData(qk.kaggle(), account)
    },
  })
}

export function useDisconnectKaggle() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      unwrap(await api.DELETE('/compute/kaggle'))
    },
    onSuccess: () => {
      queryClient.setQueryData(qk.kaggle(), null)
      queryClient.removeQueries({ queryKey: qk.kagglePollUntil() })
    },
  })
}

export function kaggleStatusLabel(status: KaggleStatus): string {
  switch (status) {
    case 'unchecked':
      return 'Checking…'
    case 'ok':
      return 'Connected'
    case 'invalid':
      return 'Invalid token'
    case 'no_gpu_quota':
      return 'No GPU quota'
  }
}

/** GPU hours left this week, rounded to one decimal; null when Kaggle did not report quota. */
export function gpuHoursLeft(account: KaggleAccount): number | null {
  if (account.gpu_hours_total === null || account.gpu_hours_used === null) return null
  return Math.max(0, Math.round((account.gpu_hours_total - account.gpu_hours_used) * 10) / 10)
}
