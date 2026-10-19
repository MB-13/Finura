import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/lib/api/client'
import type { components } from '@/lib/api/schema'
import { qk } from '@/lib/query-keys'

export type StyleIn = components['schemas']['StyleIn']
export type StyleOut = components['schemas']['StyleOut']
export type StyleTemplate = components['schemas']['StyleTemplate']
export type Example = components['schemas']['Example']
export type Run = components['schemas']['RunOut']
export type Pair = components['schemas']['PairOut']
export type PreviewIn = components['schemas']['PreviewIn']
export type ProjectPatch = components['schemas']['ProjectPatch']

export function useStyleTemplates() {
  return useQuery({
    queryKey: qk.styleTemplates(),
    staleTime: 10 * 60_000,
    queryFn: async () => unwrap(await api.GET('/style-templates')),
  })
}

export function useDatasetFormats() {
  return useQuery({
    queryKey: qk.datasetFormats(),
    staleTime: Infinity,
    queryFn: async () => unwrap(await api.GET('/dataset-formats')),
  })
}

function useRefreshProject(projectId: string) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: qk.project(projectId) })
    void queryClient.invalidateQueries({ queryKey: qk.projects() })
  }
}

export function useSaveStyle(projectId: string) {
  const refresh = useRefreshProject(projectId)
  return useMutation({
    mutationFn: async (body: StyleIn) =>
      unwrap(await api.PUT('/projects/{project_id}/style', { params: { path: { project_id: projectId } }, body })),
    onSuccess: refresh,
  })
}

/** target_pairs / gen_provider / gen_model. */
export function usePatchProject(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: ProjectPatch) =>
      unwrap(await api.PATCH('/projects/{project_id}', { params: { path: { project_id: projectId } }, body })),
    onSuccess: (project) => {
      queryClient.setQueryData(qk.project(projectId), project)
    },
  })
}

export function useStartPreview(projectId: string) {
  const refresh = useRefreshProject(projectId)
  return useMutation({
    mutationFn: async (body: Partial<PreviewIn> = {}) =>
      unwrap(
        await api.POST('/projects/{project_id}/preview', {
          params: { path: { project_id: projectId } },
          body: { n_chunks: 4, pairs_per_chunk: 2, ...body },
        }),
      ),
    onSuccess: refresh,
  })
}

export function useRunPairs(projectId: string, runId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: qk.runPairs(projectId, runId ?? ''),
    enabled: Boolean(runId) && enabled,
    queryFn: async () =>
      unwrap(
        await api.GET('/projects/{project_id}/runs/{run_id}/pairs', {
          params: { path: { project_id: projectId, run_id: runId! } },
        }),
      ),
  })
}
