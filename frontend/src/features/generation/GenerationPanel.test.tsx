import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { FINISH_EARLY_MIN_PAIRS, GenerationPanel } from '@/features/generation/GenerationPanel'
import { qk } from '@/lib/query-keys'
import { jsonResponse, stubApi } from '@/test/api'
import { makeProject, makeRun } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const gen = (over = {}) => makeProject({ status: 'generating', allowed_actions: ['finish_generation', 'cancel_generation', 'rename', 'delete'], active_run: makeRun({ kind: 'full', state: 'running', total_chunks: 200, done_chunks: 50, pairs_generated: 120, ...over }) })

describe('GenerationPanel', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows chunk progress, pairs generated and the run state', () => {
    renderRoutes(<GenerationPanel project={gen()} />)
    expect(screen.getByText('50 of 200 sections')).toBeInTheDocument()
    expect(screen.getByText('25%')).toBeInTheDocument()
    expect(screen.getByText('120 pairs generated')).toBeInTheDocument()
    expect(screen.getByText('Generating')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Generation progress' })).toBeInTheDocument()
    expect(screen.queryByText(/Paused until/)).not.toBeInTheDocument()
  })

  it('shows the waiting_quota card with the resume time, the latest warning and a tip', () => {
    const resume = '2026-03-04T09:30:00Z'
    renderRoutes(<GenerationPanel project={gen({ state: 'waiting_quota', resume_at: resume })} />)
    expect(screen.getByText(/Paused until your free quota resets/)).toBeInTheDocument()
    const expected = new Date(resume).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })
    expect(screen.getByText(`It will continue automatically at ${expected}.`)).toBeInTheDocument()
    expect(screen.getByText(/connect a Gemini key to finish faster/)).toBeInTheDocument()
  })

  it('renders the latest warning notice from the cache', async () => {
    const { queryClient } = renderRoutes(<GenerationPanel project={gen()} />)
    expect(screen.queryByText('Groq rate limit hit, switched model.')).not.toBeInTheDocument()
    queryClient.setQueryData(qk.notice(gen().id), { level: 'warning', text: 'Groq rate limit hit, switched model.', receivedAt: 1 })
    expect(await screen.findByText('Groq rate limit hit, switched model.')).toBeInTheDocument()
  })

  it('asks for confirmation before cancelling', async () => {
    const calls = stubApi((url, req) =>
      url.pathname.endsWith('/cancel') && req.method === 'POST' ? jsonResponse(makeProject({ status: 'awaiting_style' })) : undefined,
    )
    renderRoutes(<GenerationPanel project={gen()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Cancel generation' }))
    expect(calls).toHaveLength(0)
    const dialog = await screen.findByRole('alertdialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel generation' }))
    await waitFor(() => expect(calls.some((c) => c.url.pathname.endsWith(`/runs/${gen().active_run!.id}/cancel`))).toBe(true))
  })

  it('shows a starting state before the run exists', () => {
    renderRoutes(<GenerationPanel project={makeProject({ status: 'generating', active_run: null })} />)
    expect(screen.getByText('Starting up…')).toBeInTheDocument()
  })

  it('offers to finish early with the pairs so far, after confirmation', async () => {
    const calls = stubApi((url, req) =>
      url.pathname.endsWith('/finish') && req.method === 'POST' ? jsonResponse(makeProject({ status: 'generating' })) : undefined,
    )
    renderRoutes(<GenerationPanel project={gen({ state: 'waiting_quota' })} />)
    await userEvent.click(screen.getByRole('button', { name: 'Use pairs so far' }))
    expect(calls).toHaveLength(0)
    const dialog = await screen.findByRole('alertdialog')
    expect(within(dialog).getByText(/remaining 150 sections are skipped/)).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Use pairs so far' }))
    await waitFor(() => expect(calls.some((c) => c.url.pathname.endsWith(`/runs/${gen().active_run!.id}/finish`))).toBe(true))
  })

  it('hides finishing early until enough pairs exist', () => {
    renderRoutes(<GenerationPanel project={gen({ pairs_generated: FINISH_EARLY_MIN_PAIRS - 1 })} />)
    expect(screen.queryByRole('button', { name: 'Use pairs so far' })).not.toBeInTheDocument()
  })
})
