import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { revealToken } from '@/features/training/token-store'
import { api, unwrap } from '@/lib/api/client'
import type { components } from '@/lib/api/schema'
import { qk } from '@/lib/query-keys'

export type BaseModel = components['schemas']['BaseModelOut']
export type ModelCheck = components['schemas']['ModelCheck']
export type Preset = components['schemas']['PresetOut']
export type PresetKey = components['schemas']['TrainingCreate']['preset']
export type Advanced = components['schemas']['Advanced']
export type TrainingJob = components['schemas']['TrainingJobOut']
export type TrainingCreate = components['schemas']['TrainingCreate']
export type Metric = components['schemas']['MetricOut']
export type Artifact = components['schemas']['ArtifactOut']
export type Evaluation = components['schemas']['EvaluationOut']

export function useModelCatalog(projectId: string, enabled = true) {
  return useQuery({
    queryKey: qk.modelCatalog(projectId),
    enabled,
    staleTime: 5 * 60_000,
    queryFn: async () => unwrap(await api.GET('/models/catalog', { params: { query: { project_id: projectId } } })),
  })
}

export function usePresets(enabled = true) {
  return useQuery({
    queryKey: qk.presets(),
    enabled,
    staleTime: 10 * 60_000,
    queryFn: async () => unwrap(await api.GET('/training/presets')),
  })
}

export function useCheckModel() {
  return useMutation({
    mutationFn: async (hfId: string) => unwrap(await api.POST('/models/check', { body: { hf_id: hfId } })),
  })
}

/**
 * Create the job. The one-time token goes straight into the in-memory token store and is stripped from the
 * result, so it never lands in the query or mutation cache.
 */
export function useCreateTraining(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: TrainingCreate) => {
      const created = unwrap(
        await api.POST('/projects/{project_id}/training', { params: { path: { project_id: projectId } }, body }),
      )
      // Kaggle jobs have no user-visible token (the server manages it)
      if (created.token) {
        revealToken(created.job.id, {
          token: created.token,
          notebookUrl: created.notebook_url ?? null,
          expiresAt: created.job.token_expires_at ?? null,
        })
      }
      return created.job
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.project(projectId) })
      void queryClient.invalidateQueries({ queryKey: qk.projects() })
    },
  })
}

/** Move a Colab job nobody has connected to yet onto the user's Kaggle account (same model and settings). */
export function useSwitchToKaggle(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (jobId: string) =>
      unwrap(
        await api.POST('/projects/{project_id}/training/{job_id}/switch', {
          params: { path: { project_id: projectId, job_id: jobId } },
          body: { backend: 'kaggle' },
        }),
      ).job,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.project(projectId) })
      void queryClient.invalidateQueries({ queryKey: qk.projects() })
    },
  })
}

/** Rotate the job token; the new token is shown once (in-memory only) and the old one stops working. */
export function useRotateToken(projectId: string, jobId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (notebookUrl: string | null) => {
      const out = unwrap(
        await api.POST('/projects/{project_id}/training/{job_id}/token', {
          params: { path: { project_id: projectId, job_id: jobId } },
        }),
      )
      revealToken(jobId, { token: out.token, notebookUrl, expiresAt: out.expires_at })
      return { expires_at: out.expires_at }
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.project(projectId) }),
  })
}

export function useCancelTraining(projectId: string, jobId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/projects/{project_id}/training/{job_id}/cancel', {
          params: { path: { project_id: projectId, job_id: jobId } },
        }),
      ),
    onSuccess: (project) => {
      queryClient.setQueryData(qk.project(projectId), project)
      void queryClient.invalidateQueries({ queryKey: qk.projects() })
    },
  })
}

export function useMetrics(projectId: string, jobId: string | undefined) {
  return useQuery({
    queryKey: qk.metrics(projectId, jobId ?? ''),
    enabled: Boolean(jobId),
    queryFn: async () =>
      unwrap(
        await api.GET('/projects/{project_id}/training/{job_id}/metrics', {
          params: { path: { project_id: projectId, job_id: jobId! } },
        }),
      ),
  })
}

export function useCheckpointDownload(projectId: string, jobId: string) {
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.GET('/projects/{project_id}/training/{job_id}/checkpoint/download', {
          params: { path: { project_id: projectId, job_id: jobId } },
        }),
      ),
  })
}

export function useArtifacts(projectId: string, enabled = true) {
  return useQuery({
    queryKey: qk.artifacts(projectId),
    enabled,
    queryFn: async () => unwrap(await api.GET('/projects/{project_id}/artifacts', { params: { path: { project_id: projectId } } })),
  })
}

export function useArtifactDownload(projectId: string) {
  return useMutation({
    mutationFn: async (artifactId: string) =>
      unwrap(
        await api.GET('/projects/{project_id}/artifacts/{artifact_id}/download', {
          params: { path: { project_id: projectId, artifact_id: artifactId } },
        }),
      ),
  })
}

export function useEvaluation(projectId: string, enabled = true) {
  return useQuery({
    queryKey: qk.evaluation(projectId),
    enabled,
    queryFn: async () => unwrap(await api.GET('/projects/{project_id}/evaluation', { params: { path: { project_id: projectId } } })),
  })
}

/** Merge a metric into a loss curve: one point per step, sorted by step. */
export function mergeMetric(points: Metric[] | undefined, point: Metric): Metric[] {
  const list = points ?? []
  const idx = list.findIndex((p) => p.step === point.step)
  if (idx >= 0) {
    const next = list.slice()
    next[idx] = point
    return next
  }
  return [...list, point].sort((a, b) => a.step - b.step)
}
