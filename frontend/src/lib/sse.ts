import { fetchEventSource, type EventSourceMessage, type FetchEventSourceInit } from '@microsoft/fetch-event-source'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import type { components } from '@/lib/api/schema'
import { mergeMetric, type Metric } from '@/features/training/api'
import { env } from '@/lib/env'
import { qk } from '@/lib/query-keys'
import { getAccessToken } from '@/lib/supabase'

type ProjectOut = components['schemas']['ProjectOut']

/** Signature of `fetchEventSource`; injectable so tests can replace it. */
export type EventSourceFn = (input: RequestInfo, init: FetchEventSourceInit) => Promise<void>

export type StatusEvent = {
  status: ProjectOut['status']
  reason?: string | null
  message?: string | null
  at?: string
}
export type ProgressEvent = {
  phase: string
  document_id?: string
  state?: string
  chunks?: number
  /** generation phases (`preview` | `generate` | `finalize`) */
  run_id?: string
  done?: number
  total?: number
  pairs?: number
  /** checkpoint phase */
  step?: number
  /** convert phase */
  source?: string
}
export type TrainMetricsEvent = { job_id?: string; step: number; max_steps?: number; loss?: number | null; lr?: number | null; at?: string }
export type NoticeEvent = { level: 'info' | 'warning'; text: string; resume_at?: string | null }
/** Latest warning kept in the query cache for the GenerationPanel. */
export type StoredNotice = NoticeEvent & { receivedAt: number }

const RUN_PHASES = new Set(['preview', 'generate', 'finalize'])

/** Errors that must stop reconnecting (auth / missing project). */
class FatalStreamError extends Error {}

const FATAL_STATUSES = new Set([401, 403, 404])
const BASE_DELAY_MS = 1000
const MAX_DELAY_MS = 30_000

export function backoffDelay(attempt: number): number {
  return Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS)
}

function parseJson<T>(data: string): T | null {
  try {
    return JSON.parse(data) as T
  } catch {
    return null
  }
}

/** Show live counters immediately; the invalidation that follows brings the authoritative project. */
function applyRunProgress(queryClient: QueryClient, projectId: string, p: ProgressEvent) {
  queryClient.setQueryData<ProjectOut>(qk.project(projectId), (old) => {
    if (!old || !p.run_id) return old
    const patch = <R extends NonNullable<ProjectOut['active_run']>>(run: R | null | undefined) =>
      run && run.id === p.run_id
        ? {
            ...run,
            done_chunks: p.done ?? run.done_chunks,
            total_chunks: p.total ?? run.total_chunks,
            pairs_generated: p.pairs ?? run.pairs_generated,
            state: (p.state as R['state'] | undefined) ?? run.state,
          }
        : run
    return { ...old, active_run: patch(old.active_run), latest_preview: patch(old.latest_preview) }
  })
}

/** Append a loss point to the job's curve (de-duplicated by step) and move the live counters on the job. */
function applyTrainMetrics(queryClient: QueryClient, projectId: string, m: TrainMetricsEvent) {
  const job = queryClient.getQueryData<ProjectOut>(qk.project(projectId))?.active_job
  if (!job || typeof m.step !== 'number') return
  if (m.job_id && m.job_id !== job.id) return // a heartbeat from an older job of this project
  const at = m.at ?? new Date().toISOString()
  // only extend a loaded curve: seeding an empty cache would stop the initial history fetch
  if (queryClient.getQueryData(qk.metrics(projectId, job.id)) !== undefined) {
    queryClient.setQueryData<Metric[]>(qk.metrics(projectId, job.id), (old) =>
      mergeMetric(old, { step: m.step, loss: m.loss ?? null, lr: m.lr ?? null, at }),
    )
  }
  queryClient.setQueryData<ProjectOut>(qk.project(projectId), (old) =>
    old?.active_job && m.step >= old.active_job.current_step
      ? {
          ...old,
          active_job: {
            ...old.active_job,
            current_step: m.step,
            max_steps: m.max_steps ?? old.active_job.max_steps,
            last_loss: m.loss ?? old.active_job.last_loss,
            last_heartbeat_at: at,
          },
        }
      : old,
  )
}

/** Apply one SSE message to the query cache. Returns true when the stream should end. */
export function handleProjectEvent(queryClient: QueryClient, projectId: string, ev: EventSourceMessage): boolean {
  switch (ev.event) {
    case 'snapshot': {
      const project = parseJson<ProjectOut>(ev.data)
      if (project) queryClient.setQueryData(qk.project(projectId), project)
      return false
    }
    case 'status': {
      const s = parseJson<StatusEvent>(ev.data)
      if (!s) return false
      queryClient.setQueryData<ProjectOut>(qk.project(projectId), (old) =>
        old
          ? {
              ...old,
              status: s.status,
              status_reason: s.reason ?? null,
              status_message: s.message ?? null,
              status_changed_at: s.at ?? old.status_changed_at,
            }
          : old,
      )
      // allowed_actions and counts are computed server-side: refetch rather than guess
      void queryClient.invalidateQueries({ queryKey: qk.project(projectId) })
      // generated pairs change with the status (e.g. restyle discards them)
      void queryClient.invalidateQueries({ queryKey: qk.datasetAll(projectId) })
      return false
    }
    case 'notice': {
      const n = parseJson<NoticeEvent>(ev.data)
      if (!n?.text) return false
      if (n.level === 'warning') queryClient.setQueryData<StoredNotice>(qk.notice(projectId), { ...n, receivedAt: Date.now() })
      else toast.info(n.text)
      return false
    }
    case 'train_metrics': {
      const m = parseJson<TrainMetricsEvent>(ev.data)
      if (m) applyTrainMetrics(queryClient, projectId, m)
      return false
    }
    case 'progress': {
      const p = parseJson<ProgressEvent>(ev.data)
      if (p?.phase === 'checkpoint') {
        void queryClient.invalidateQueries({ queryKey: qk.project(projectId) })
        return false
      }
      if (p?.phase === 'eval') {
        void queryClient.invalidateQueries({ queryKey: qk.project(projectId) })
        void queryClient.invalidateQueries({ queryKey: qk.evaluation(projectId) })
        return false
      }
      if (p?.phase === 'convert') {
        void queryClient.invalidateQueries({ queryKey: qk.playgroundStatus(projectId) })
        void queryClient.invalidateQueries({ queryKey: qk.artifacts(projectId) })
        return false
      }
      if (p && RUN_PHASES.has(p.phase)) {
        applyRunProgress(queryClient, projectId, p)
        void queryClient.invalidateQueries({ queryKey: qk.project(projectId) })
        if (p.run_id) void queryClient.invalidateQueries({ queryKey: qk.runPairs(projectId, p.run_id) })
        return false
      }
      void queryClient.invalidateQueries({ queryKey: qk.documents(projectId) })
      if (p?.state === 'parsed') {
        void queryClient.invalidateQueries({ queryKey: qk.chunksAll(projectId) })
        void queryClient.invalidateQueries({ queryKey: qk.project(projectId) })
      }
      return false
    }
    case 'deleted':
      return true
    default:
      return false
  }
}

type Options = {
  /** Replace the SSE implementation (tests). */
  connect?: EventSourceFn
  getToken?: () => Promise<string | null>
}

/**
 * Subscribe to `/projects/{id}/events` and keep the project caches fresh.
 * Reconnects with exponential backoff, stops on 401/403/404, closes on unmount.
 */
export function useProjectEvents(projectId: string | undefined, { connect = fetchEventSource, getToken = getAccessToken }: Options = {}) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  useEffect(() => {
    if (!projectId) return
    const controller = new AbortController()
    let attempt = 0

    void connect(`${env.apiUrl}/projects/${projectId}/events`, {
      signal: controller.signal,
      openWhenHidden: true,
      headers: { Accept: 'text/event-stream' },
      // resolve the token on every (re)connect so a refreshed session is used
      fetch: async (input, init) => {
        const token = await getToken()
        const headers = new Headers(init?.headers)
        if (token) headers.set('Authorization', `Bearer ${token}`)
        return globalThis.fetch(input, { ...init, headers })
      },
      async onopen(response) {
        if (FATAL_STATUSES.has(response.status)) throw new FatalStreamError(`Stream rejected (${response.status})`)
        if (!response.ok) throw new Error(`Stream failed (${response.status})`)
        attempt = 0
      },
      onmessage(ev) {
        attempt = 0
        if (handleProjectEvent(queryClient, projectId, ev)) {
          controller.abort()
          void queryClient.invalidateQueries({ queryKey: qk.projects() })
          void navigate('/projects')
        }
      },
      onerror(err) {
        if (err instanceof FatalStreamError || controller.signal.aborted) throw err
        return backoffDelay(attempt++)
      },
    }).catch(() => {
      // fatal error or abort: stop quietly, the query itself surfaces auth/404 errors
    })

    return () => controller.abort()
  }, [projectId, connect, getToken, queryClient, navigate])
}
