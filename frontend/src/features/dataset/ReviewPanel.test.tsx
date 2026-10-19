import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ReviewPanel } from '@/features/dataset/ReviewPanel'
import { jsonResponse, stubApi, type Handler } from '@/test/api'
import { CATALOG, makeProject, PRESETS, PROJECT_ID } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const STATS = {
  kept: 480,
  train: 430,
  eval: 50,
  dropped_by_reason: { low_score: 12, duplicate: 3 },
  avg_correctness: 4.5,
  avg_style: 4.25,
  answer_words: { median: 42 },
  min_pairs: 50,
  small_min_pairs: 20,
  max_pairs: 2000,
  min_eval: 5,
  resume: null,
  more: null,
}
const stats: Handler = (url) => (url.pathname.endsWith('/dataset/stats') ? jsonResponse(STATS) : undefined)
const project = (over = {}) => makeProject({ status: 'in_review', ...over })

describe('ReviewPanel', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows stats and the review actions', async () => {
    stubApi(stats)
    renderRoutes(<ReviewPanel project={project()} />)
    expect(await screen.findByText('480')).toBeInTheDocument()
    expect(screen.getByText('430 / 50')).toBeInTheDocument()
    expect(screen.getByText('4.5')).toBeInTheDocument()
    expect(screen.getByText('4.3')).toBeInTheDocument()
    expect(screen.getByText(/low score/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open review table/ })).toHaveAttribute('href', `/projects/${PROJECT_ID}/dataset`)
    expect(screen.getByRole('button', { name: 'Approve & continue' })).toBeInTheDocument()
  })

  it('lists what is missing and keeps approve disabled until the dataset qualifies', async () => {
    const calls = stubApi((url) => (url.pathname.endsWith('/dataset/stats') ? jsonResponse({ ...STATS, kept: 32, train: 29, eval: 3 }) : undefined))
    renderRoutes(<ReviewPanel project={project()} />)
    const checklist = await screen.findByRole('region', { name: 'Before you can approve' })
    expect(checklist).toHaveTextContent('Not done: At least 50 pairs kept')
    expect(checklist).toHaveTextContent('32 / 50')
    expect(checklist).toHaveTextContent('Not done: At least 5 pairs held out for evaluation')
    const approve = screen.getByRole('button', { name: 'Approve & continue' })
    expect(approve).toBeDisabled()
    expect(approve).toHaveAccessibleDescription(/Before you can approve/)
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
  })

  it('offers to complete an early-finished generation or continue with the pairs so far', async () => {
    const RUN = '11111111-1111-4111-8111-111111111111'
    const small = { ...STATS, kept: 32, train: 29, eval: 3, min_eval: 1, resume: { run_id: RUN, remaining_chunks: 18, total_chunks: 30 } }
    const calls = stubApi(
      (url) => (url.pathname.endsWith('/dataset/stats') ? jsonResponse(small) : undefined),
      (url, req) => (url.pathname.endsWith(`/runs/${RUN}/resume`) && req.method === 'POST' ? jsonResponse(makeProject({ status: 'generating' })) : undefined),
      (url, req) =>
        url.pathname.endsWith('/dataset/approve') && req.method === 'POST'
          ? jsonResponse({ id: 'v1', version: 1, train_count: 29, eval_count: 3, sha256_train: 'a', sha256_eval: 'b', created_at: '2026-01-01T00:00:00Z', chunk_count: 10 })
          : undefined,
    )
    renderRoutes(<ReviewPanel project={project()} />)
    const choice = await screen.findByRole('region', { name: /32 of the recommended 50 pairs/ })
    expect(choice).toHaveTextContent('18 of 30 document sections')
    expect(screen.queryByRole('region', { name: 'Before you can approve' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve & continue' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Approve 32 pairs' }))
    await waitFor(() => expect(calls.some((c) => c.url.pathname.endsWith('/dataset/approve'))).toBe(true))
    const approveCall = calls.find((c) => c.url.pathname.endsWith('/dataset/approve'))
    expect(await approveCall?.request.json()).toEqual({ allow_small: true })

    await userEvent.click(screen.getByRole('button', { name: 'Complete generation' }))
    await waitFor(() => expect(calls.some((c) => c.url.pathname.endsWith(`/runs/${RUN}/resume`))).toBe(true))
  })

  it('offers another generation pass when every section is done but the dataset is still small', async () => {
    const small = { ...STATS, kept: 32, train: 29, eval: 3, min_eval: 1, more: { target_pairs: 500, sections: 7, pairs_to_generate: 56 } }
    const calls = stubApi(
      (url) => (url.pathname.endsWith('/dataset/stats') ? jsonResponse(small) : undefined),
      (url, req) => (url.pathname.endsWith('/generate/more') && req.method === 'POST' ? jsonResponse(makeProject({ status: 'generating' })) : undefined),
    )
    renderRoutes(<ReviewPanel project={project()} />)
    const choice = await screen.findByRole('region', { name: /32 of the recommended 50 pairs/ })
    expect(choice).toHaveTextContent('Another pass over 7 document sections, asking for up to 56 new pairs')
    expect(screen.queryByRole('button', { name: 'Complete generation' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve 32 pairs' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Generate more pairs' }))
    await waitFor(() => expect(calls.some((c) => c.url.pathname.endsWith('/generate/more'))).toBe(true))
  })

  it('keeps a Generate more button next to the review actions once the dataset is big enough', async () => {
    stubApi((url) => (url.pathname.endsWith('/dataset/stats') ? jsonResponse({ ...STATS, more: { target_pairs: 1000, sections: 40, pairs_to_generate: 680 } }) : undefined))
    renderRoutes(<ReviewPanel project={project()} />)
    expect(await screen.findByRole('button', { name: /Generate more pairs/ })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Approve & continue' })).toBeEnabled()
  })

  it('shows the 409 message inline when approving fails', async () => {
    stubApi(stats, (url, req) =>
      url.pathname.endsWith('/dataset/approve') && req.method === 'POST'
        ? jsonResponse({ error: 'dataset_too_small', message: 'Keep at least 50 pairs before approving.' }, 409)
        : undefined,
    )
    renderRoutes(<ReviewPanel project={project()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Approve & continue' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Keep at least 50 pairs before approving.')
  })

  it('shows the approved version and hides the approve button', async () => {
    stubApi(stats)
    const version = { id: 'v1', version: 2, train_count: 430, eval_count: 50, sha256_train: 'a', sha256_eval: 'b', created_at: '2026-01-01T00:00:00Z', chunk_count: 10 }
    renderRoutes(<ReviewPanel project={project({ dataset_version: version })} />)
    expect(await screen.findByText(/Next, set up training/)).toHaveTextContent('Approved v2')
    expect(screen.queryByRole('button', { name: 'Approve & continue' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Set up training/ })).toBeInTheDocument()
  })

  it('opens the training setup dialog from the approved state', async () => {
    stubApi(
      stats,
      (url) => (url.pathname === '/models/catalog' ? jsonResponse(CATALOG) : undefined),
      (url) => (url.pathname === '/training/presets' ? jsonResponse(PRESETS) : undefined),
    )
    const version = { id: 'v1', version: 2, train_count: 430, eval_count: 50, sha256_train: 'a', sha256_eval: 'b', created_at: '2026-01-01T00:00:00Z', chunk_count: 10 }
    renderRoutes(<ReviewPanel project={project({ dataset_version: version })} />)
    await userEvent.click(await screen.findByRole('button', { name: /Set up training/ }))
    expect(await screen.findByRole('dialog', { name: 'Set up training' })).toBeInTheDocument()
    expect(await screen.findByRole('radio', { name: 'Qwen3.5 4B' })).toBeInTheDocument()
  })

  it('exports by opening the signed url', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    stubApi(stats, (url, req) =>
      url.pathname.endsWith('/dataset/export') && req.method === 'POST' ? jsonResponse({ url: 'https://r2.example/x.jsonl', expires_at: 1 }) : undefined,
    )
    renderRoutes(<ReviewPanel project={project()} />)
    await userEvent.click(await screen.findByRole('button', { name: /Export JSONL/ }))
    await waitFor(() => expect(open).toHaveBeenCalledWith('https://r2.example/x.jsonl', '_blank', 'noopener,noreferrer'))
    open.mockRestore()
  })

  it('asks before restyling, then calls restyle', async () => {
    const calls = stubApi(stats, (url, req) =>
      url.pathname.endsWith('/dataset/restyle') && req.method === 'POST' ? jsonResponse(makeProject({ status: 'awaiting_style' })) : undefined,
    )
    renderRoutes(<ReviewPanel project={project()} />)
    await userEvent.click(await screen.findByRole('button', { name: /Change style & regenerate/ }))
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
    await userEvent.click(await screen.findByRole('button', { name: 'Discard and change style' }))
    await waitFor(() => expect(calls.some((c) => c.url.pathname.endsWith('/dataset/restyle'))).toBe(true))
  })

  it('shows an error state when stats fail', async () => {
    stubApi(() => jsonResponse({ error: 'boom', message: 'Stats unavailable' }, 400))
    renderRoutes(<ReviewPanel project={project()} />)
    expect(await screen.findByText('Stats unavailable')).toBeInTheDocument()
  })
})
