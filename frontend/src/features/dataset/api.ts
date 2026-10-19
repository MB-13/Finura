import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type InfiniteData, type QueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/lib/api/client'
import type { components } from '@/lib/api/schema'
import { qk, type PairFilters } from '@/lib/query-keys'

export type Pair = components['schemas']['PairOut']
export type PairPatch = components['schemas']['PairPatch']
export type PairCreate = components['schemas']['PairCreate']
export type BulkAction = components['schemas']['BulkIn']['action']
export type DatasetStats = components['schemas']['DatasetStats']
export type DatasetVersion = components['schemas']['DatasetVersionOut']
type PairPage = components['schemas']['Page_PairOut_']

export const PAIR_PAGE_SIZE = 100

export const DEFAULT_FILTERS: PairFilters = { split: 'all', kept: 'all', q: '', sort: 'created' }

export function useDatasetStats(projectId: string) {
  return useQuery({
    queryKey: qk.datasetStats(projectId),
    queryFn: async () =>
      unwrap(await api.GET('/projects/{project_id}/dataset/stats', { params: { path: { project_id: projectId } } })),
  })
}

export function usePairs(projectId: string, filters: PairFilters) {
  return useInfiniteQuery({
    queryKey: qk.pairs(projectId, filters),
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET('/projects/{project_id}/pairs', {
          params: {
            path: { project_id: projectId },
            query: {
              split: filters.split,
              kept: filters.kept === 'all' ? undefined : filters.kept === 'kept',
              q: filters.q || undefined,
              sort: filters.sort,
              limit: PAIR_PAGE_SIZE,
              cursor: pageParam,
            },
          },
        }),
      ),
    // opaque cursor: pass next_cursor straight back
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
}

type Pages = InfiniteData<PairPage, string | null>

function mapPairs(queryClient: QueryClient, projectId: string, fn: (pair: Pair) => Pair) {
  queryClient.setQueriesData<Pages>({ queryKey: [...qk.datasetAll(projectId), 'pairs'] }, (old) =>
    old ? { ...old, pages: old.pages.map((p) => ({ ...p, items: p.items.map(fn) })) } : old,
  )
}

function refresh(queryClient: QueryClient, projectId: string) {
  void queryClient.invalidateQueries({ queryKey: qk.datasetAll(projectId) })
  void queryClient.invalidateQueries({ queryKey: qk.project(projectId) })
}

/** PATCH one pair. kept/split changes show instantly and roll back if the request fails. */
export function useUpdatePair(projectId: string) {
  const queryClient = useQueryClient()
  const pairsKey = [...qk.datasetAll(projectId), 'pairs']
  return useMutation({
    mutationFn: async ({ id, ...body }: PairPatch & { id: string }) =>
      unwrap(
        await api.PATCH('/projects/{project_id}/pairs/{pair_id}', {
          params: { path: { project_id: projectId, pair_id: id } },
          body,
        }),
      ),
    onMutate: async ({ id, kept, split }) => {
      await queryClient.cancelQueries({ queryKey: pairsKey })
      const snapshot = queryClient.getQueriesData<Pages>({ queryKey: pairsKey })
      mapPairs(queryClient, projectId, (pair) =>
        pair.id === id
          ? {
              ...pair,
              ...(kept !== undefined && kept !== null ? { kept, dropped_reason: kept ? null : (pair.dropped_reason ?? 'user_deleted') } : {}),
              ...(split ? { split } : {}),
            }
          : pair,
      )
      return { snapshot }
    },
    onError: (_err, _vars, ctx) => {
      ctx?.snapshot.forEach(([key, data]) => queryClient.setQueryData(key, data))
    },
    onSuccess: (updated) => {
      mapPairs(queryClient, projectId, (pair) => (pair.id === updated.id ? updated : pair))
    },
    onSettled: () => refresh(queryClient, projectId),
  })
}

export function useCreatePair(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: PairCreate) =>
      unwrap(await api.POST('/projects/{project_id}/pairs', { params: { path: { project_id: projectId } }, body })),
    onSuccess: () => refresh(queryClient, projectId),
  })
}

export function useBulkPairs(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: { ids: string[]; action: BulkAction }) =>
      unwrap(await api.POST('/projects/{project_id}/pairs/bulk', { params: { path: { project_id: projectId } }, body })),
    onSuccess: () => refresh(queryClient, projectId),
  })
}

export type ExportShape = components['schemas']['ExportIn']['shape']

export function useExportDataset(projectId: string) {
  return useMutation({
    mutationFn: async (shape: ExportShape = 'training') =>
      unwrap(await api.POST('/projects/{project_id}/dataset/export', { params: { path: { project_id: projectId } }, body: { shape } })),
  })
}

export function useApproveDataset(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    /** allowSmall: approve a dataset below the recommended size on purpose (e.g. after finishing generation early). */
    mutationFn: async ({ allowSmall = false }: { allowSmall?: boolean } = {}) =>
      unwrap(
        await api.POST('/projects/{project_id}/dataset/approve', {
          params: { path: { project_id: projectId } },
          body: { allow_small: allowSmall },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.project(projectId) })
      void queryClient.invalidateQueries({ queryKey: qk.projects() })
    },
  })
}

export function useRestyle(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      unwrap(await api.POST('/projects/{project_id}/dataset/restyle', { params: { path: { project_id: projectId } } })),
    onSuccess: (project) => {
      queryClient.setQueryData(qk.project(projectId), project)
      void queryClient.invalidateQueries({ queryKey: qk.datasetAll(projectId) })
      void queryClient.invalidateQueries({ queryKey: qk.projects() })
    },
  })
}
