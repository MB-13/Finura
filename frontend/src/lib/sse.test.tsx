import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { FetchEventSourceInit } from '@microsoft/fetch-event-source'
import type { ReactNode } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router'

import { toast } from 'sonner'

import { backoffDelay, useProjectEvents, type EventSourceFn } from '@/lib/sse'
import { qk } from '@/lib/query-keys'
import { JOB_ID, makeJob, makeProject, makeRun, PROJECT_ID } from '@/test/fixtures'

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  let init!: FetchEventSourceInit
  let url = ''
  const connect = vi.fn<EventSourceFn>((input, i) => {
    url = String(input)
    init = i
    return new Promise<void>(() => {})
  })
  const getToken = async () => 'tok'
  let Hook: () => null = () => null
  Hook = () => {
    useProjectEvents(PROJECT_ID, { connect, getToken })
    return null
  }
  const router = createMemoryRouter(
    [
      { path: '/projects/:id', element: <Hook /> },
      { path: '/projects', element: <div>list</div> },
    ],
    { initialEntries: [`/projects/${PROJECT_ID}`] },
  )
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  const utils = renderHook(() => null, { wrapper: ({ children }) => wrapper({ children: <>{children}<RouterProvider router={router} /></> }) })
  return { queryClient, router, connect, utils, get init() { return init }, get url() { return url } }
}

const send = (init: FetchEventSourceInit, event: string, data: unknown) =>
  init.onmessage?.({ id: '', event, data: JSON.stringify(data), retry: undefined })

describe('useProjectEvents', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('connects to the events endpoint and sends the bearer token on every connect', async () => {
    const s = setup()
    await waitFor(() => expect(s.connect).toHaveBeenCalledTimes(1))
    expect(s.url).toMatch(new RegExp(`/projects/${PROJECT_ID}/events$`))
    const fetchSpy = vi.fn(async () => new Response(null))
    vi.stubGlobal('fetch', fetchSpy)
    await s.init.fetch!('http://x/events', { headers: { Accept: 'text/event-stream' } })
    const headers = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1].headers as Headers
    expect(headers.get('Authorization')).toBe('Bearer tok')
  })

  it('writes the snapshot into the project cache', async () => {
    const s = setup()
    await waitFor(() => expect(s.connect).toHaveBeenCalled())
    send(s.init, 'snapshot', makeProject({ name: 'From stream', status: 'parsing' }))
    expect(s.queryClient.getQueryData<ReturnType<typeof makeProject>>(qk.project(PROJECT_ID))?.name).toBe('From stream')
  })

  it('merges a status event into the cached project and invalidates it', async () => {
    const s = setup()
    await waitFor(() => expect(s.connect).toHaveBeenCalled())
    s.queryClient.setQueryData(qk.project(PROJECT_ID), makeProject({ status: 'parsing' }))
    const invalidate = vi.spyOn(s.queryClient, 'invalidateQueries')
    send(s.init, 'status', { status: 'failed', reason: 'parse_error', message: 'Bad PDF', at: '2026-02-02T00:00:00Z' })
    const project = s.queryClient.getQueryData<ReturnType<typeof makeProject>>(qk.project(PROJECT_ID))!
    expect(project).toMatchObject({ status: 'failed', status_reason: 'parse_error', status_message: 'Bad PDF', name: 'My project' })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: qk.project(PROJECT_ID) })
  })

  it('invalidates documents on progress and chunks when a document is parsed', async () => {
    const s = setup()
    await waitFor(() => expect(s.connect).toHaveBeenCalled())
    const invalidate = vi.spyOn(s.queryClient, 'invalidateQueries')
    send(s.init, 'progress', { phase: 'parse', document_id: 'd', state: 'parsing' })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: qk.documents(PROJECT_ID) })
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: qk.chunksAll(PROJECT_ID) })
    send(s.init, 'progress', { phase: 'parse', document_id: 'd', state: 'parsed', chunks: 3 })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: qk.chunksAll(PROJECT_ID) })
  })

  it('patches and invalidates the project and run pairs on generation progress', async () => {
    const s = setup()
    await waitFor(() => expect(s.connect).toHaveBeenCalled())
    const run = makeRun({ kind: 'full', state: 'running', total_chunks: 10, done_chunks: 1, pairs_generated: 2 })
    s.queryClient.setQueryData(qk.project(PROJECT_ID), makeProject({ status: 'generating', active_run: run }))
    const invalidate = vi.spyOn(s.queryClient, 'invalidateQueries')
    send(s.init, 'progress', { phase: 'generate', run_id: run.id, done: 4, total: 10, pairs: 9, state: 'waiting_quota' })
    const project = s.queryClient.getQueryData<ReturnType<typeof makeProject>>(qk.project(PROJECT_ID))!
    expect(project.active_run).toMatchObject({ done_chunks: 4, total_chunks: 10, pairs_generated: 9, state: 'waiting_quota' })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: qk.project(PROJECT_ID) })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: qk.runPairs(PROJECT_ID, run.id) })
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: qk.documents(PROJECT_ID) })
  })

  it.each(['preview', 'finalize'])('invalidates the project on %s progress', async (phase) => {
    const s = setup()
    await waitFor(() => expect(s.connect).toHaveBeenCalled())
    const invalidate = vi.spyOn(s.queryClient, 'invalidateQueries')
    send(s.init, 'progress', { phase, run_id: 'r1', done: 1, total: 2, pairs: 3, state: 'running' })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: qk.project(PROJECT_ID) })
  })

  it('toasts info notices and keeps the latest warning in the cache', async () => {
    const s = setup()
    await waitFor(() => expect(s.connect).toHaveBeenCalled())
    const info = vi.spyOn(toast, 'info').mockReturnValue(1)
    send(s.init, 'notice', { level: 'info', text: 'Switched to Gemini.' })
    expect(info).toHaveBeenCalledWith('Switched to Gemini.')
    expect(s.queryClient.getQueryData(qk.notice(PROJECT_ID))).toBeUndefined()
    send(s.init, 'notice', { level: 'warning', text: 'Quota used up.', resume_at: '2026-01-02T00:00:00Z' })
    send(s.init, 'notice', { level: 'warning', text: 'Still waiting.' })
    expect(info).toHaveBeenCalledTimes(1)
    expect(s.queryClient.getQueryData(qk.notice(PROJECT_ID))).toMatchObject({ level: 'warning', text: 'Still waiting.' })
    info.mockRestore()
  })

  it('ignores malformed notices', async () => {
    const s = setup()
    await waitFor(() => expect(s.connect).toHaveBeenCalled())
    s.init.onmessage?.({ id: '', event: 'notice', data: 'not json', retry: undefined })
    send(s.init, 'notice', { level: 'warning' })
    expect(s.queryClient.getQueryData(qk.notice(PROJECT_ID))).toBeUndefined()
  })

  it('navigates to /projects on deleted', async () => {
    const s = setup()
    await waitFor(() => expect(s.connect).toHaveBeenCalled())
    send(s.init, 'deleted', {})
    await waitFor(() => expect(s.router.state.location.pathname).toBe('/projects'))
  })

  it('stops on 401/403/404 and retries other failures with backoff', async () => {
    const s = setup()
    await waitFor(() => expect(s.connect).toHaveBeenCalled())
    await expect(s.init.onopen!(new Response(null, { status: 404 }))).rejects.toThrow()
    await expect(s.init.onopen!(new Response(null, { status: 401 }))).rejects.toThrow()
    await expect(s.init.onopen!(new Response(null, { status: 502 }))).rejects.toThrow()
    await expect(s.init.onopen!(new Response(null, { status: 200 }))).resolves.toBeUndefined()
    // fatal error is rethrown from onerror (stops fetch-event-source), others return a delay
    let fatal: unknown
    try {
      await s.init.onopen!(new Response(null, { status: 403 }))
    } catch (e) {
      fatal = e
    }
    expect(() => s.init.onerror!(fatal)).toThrow()
    expect(s.init.onerror!(new Error('net'))).toBe(1000)
    expect(s.init.onerror!(new Error('net'))).toBe(2000)
  })

  it('aborts the stream on unmount', async () => {
    const s = setup()
    await waitFor(() => expect(s.connect).toHaveBeenCalled())
    const signal = s.init.signal!
    expect(signal.aborted).toBe(false)
    s.utils.unmount()
    expect(signal.aborted).toBe(true)
  })
})

describe('training events', () => {
  it('invalidates the project on checkpoint progress', async () => {
    const s = setup()
    await waitFor(() => expect(s.connect).toHaveBeenCalled())
    const invalidate = vi.spyOn(s.queryClient, 'invalidateQueries')
    send(s.init, 'progress', { phase: 'checkpoint', step: 340 })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: qk.project(PROJECT_ID) })
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: qk.documents(PROJECT_ID) })
  })

  it('invalidates the project and evaluation on eval progress', async () => {
    const s = setup()
    await waitFor(() => expect(s.connect).toHaveBeenCalled())
    const invalidate = vi.spyOn(s.queryClient, 'invalidateQueries')
    send(s.init, 'progress', { phase: 'eval', state: 'scoring' })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: qk.project(PROJECT_ID) })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: qk.evaluation(PROJECT_ID) })
  })

  it('invalidates playground status and artifacts on convert progress', async () => {
    const s = setup()
    await waitFor(() => expect(s.connect).toHaveBeenCalled())
    const invalidate = vi.spyOn(s.queryClient, 'invalidateQueries')
    send(s.init, 'progress', { phase: 'convert', source: 'final', state: 'done' })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: qk.playgroundStatus(PROJECT_ID) })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: qk.artifacts(PROJECT_ID) })
  })

  it('appends train_metrics to a loaded curve without duplicates and ignores them with no active job', async () => {
    const s = setup()
    await waitFor(() => expect(s.connect).toHaveBeenCalled())
    send(s.init, 'train_metrics', { step: 1, max_steps: 10, loss: 2, lr: 0.1, at: '2026-01-01T00:00:00Z' })
    s.queryClient.setQueryData(qk.project(PROJECT_ID), makeProject({ status: 'training', active_job: makeJob({ current_step: 0, max_steps: 10 }) }))
    // curve not loaded yet: nothing is seeded, so the initial history fetch is not suppressed
    send(s.init, 'train_metrics', { step: 1, max_steps: 10, loss: 2, lr: 0.1, at: '2026-01-01T00:00:00Z' })
    expect(s.queryClient.getQueryData(qk.metrics(PROJECT_ID, JOB_ID))).toBeUndefined()
    s.queryClient.setQueryData(qk.metrics(PROJECT_ID, JOB_ID), [])
    send(s.init, 'train_metrics', { step: 2, max_steps: 10, loss: 1.5, lr: 0.1, at: '2026-01-01T00:00:10Z' })
    send(s.init, 'train_metrics', { step: 2, max_steps: 10, loss: 1.5, lr: 0.1, at: '2026-01-01T00:00:10Z' })
    send(s.init, 'train_metrics', { step: 1, max_steps: 10, loss: 2, lr: 0.1, at: '2026-01-01T00:00:00Z' })
    const points = s.queryClient.getQueryData<{ step: number }[]>(qk.metrics(PROJECT_ID, JOB_ID))!
    expect(points.map((p) => p.step)).toEqual([1, 2])
    expect(s.queryClient.getQueryData<ReturnType<typeof makeProject>>(qk.project(PROJECT_ID))?.active_job).toMatchObject({ current_step: 2, last_loss: 1.5 })
  })
})

describe('backoffDelay', () => {
  it('doubles and caps at 30 s', () => {
    expect([0, 1, 2, 10].map(backoffDelay)).toEqual([1000, 2000, 4000, 30000])
  })
})
