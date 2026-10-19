import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/lib/api/client'
import { qk } from '@/lib/query-keys'

export function useEstimate(projectId: string, enabled: boolean) {
  return useQuery({
    queryKey: qk.estimate(projectId),
    enabled,
    staleTime: 0,
    queryFn: async () => unwrap(await api.GET('/projects/{project_id}/estimate', { params: { path: { project_id: projectId } } })),
  })
}

export function useStartGeneration(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/projects/{project_id}/generate', {
          params: { path: { project_id: projectId } },
          body: { confirm: true },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.project(projectId) })
      void queryClient.invalidateQueries({ queryKey: qk.projects() })
    },
  })
}

export function useCancelRun(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (runId: string) =>
      unwrap(
        await api.POST('/projects/{project_id}/runs/{run_id}/cancel', {
          params: { path: { project_id: projectId, run_id: runId } },
        }),
      ),
    onSuccess: (project) => {
      queryClient.setQueryData(qk.project(projectId), project)
      void queryClient.invalidateQueries({ queryKey: qk.projects() })
    },
  })
}

/** Stop the run and build the dataset from the pairs judged so far. */
export function useFinishRun(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (runId: string) =>
      unwrap(
        await api.POST('/projects/{project_id}/runs/{run_id}/finish', {
          params: { path: { project_id: projectId, run_id: runId } },
        }),
      ),
    onSuccess: (project) => {
      queryClient.setQueryData(qk.project(projectId), project)
      void queryClient.invalidateQueries({ queryKey: qk.projects() })
    },
  })
}

/** Pick a run that was finished early back up: generate the skipped sections, keeping the pairs so far. */
export function useResumeRun(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (runId: string) =>
      unwrap(
        await api.POST('/projects/{project_id}/runs/{run_id}/resume', {
          params: { path: { project_id: projectId, run_id: runId } },
        }),
      ),
    onSuccess: (project) => {
      queryClient.setQueryData(qk.project(projectId), project)
      void queryClient.invalidateQueries({ queryKey: qk.projects() })
    },
  })
}

/** Another generation pass over the documents, added to the dataset under review (pairs and edits are kept). */
export function useGenerateMore(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      unwrap(await api.POST('/projects/{project_id}/generate/more', { params: { path: { project_id: projectId } } })),
    onSuccess: (project) => {
      queryClient.setQueryData(qk.project(projectId), project)
      void queryClient.invalidateQueries({ queryKey: qk.projects() })
    },
  })
}
