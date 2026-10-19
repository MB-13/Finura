import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { PreviewResults } from '@/features/style/PreviewResults'
import { jsonResponse, stubApi, type Handler } from '@/test/api'
import { makePair, makeProject, makeRun, makeStyle } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const ESTIMATE = {
  chunks: 120,
  pairs_per_chunk: 2,
  supported_pairs: 240,
  target_pairs: 1000,
  est_requests: 500,
  est_tokens: 750000,
  est_minutes: 90,
  est_days: 0,
  providers: ['groq'],
  fits_daily_quota: true,
}

const pairsHandler: Handler = (url) =>
  url.pathname.endsWith('/pairs') ? jsonResponse([makePair(), makePair({ id: 'p2', question: 'Second question?' })]) : undefined

const withPreview = (over = {}) =>
  makeProject({ status: 'awaiting_style', style: makeStyle(), latest_preview: makeRun(), ...over })

describe('PreviewResults', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists preview pairs with scores and an expandable source', async () => {
    stubApi(pairsHandler)
    renderRoutes(<PreviewResults project={withPreview()} onTweak={() => {}} />)
    expect(await screen.findByText('How do I reset the device?')).toBeInTheDocument()
    expect(screen.getAllByLabelText('Accuracy score 5')).toHaveLength(2)
    const [source] = screen.getAllByRole('button', { name: /Source: Setup > Reset/ })
    expect(screen.queryByText('To reset, hold the button.')).not.toBeInTheDocument()
    await userEvent.click(source!)
    expect(screen.getByText('To reset, hold the button.')).toBeInTheDocument()
  })

  it('enables Generate when the preview is done and matches the current style', async () => {
    stubApi(pairsHandler)
    renderRoutes(<PreviewResults project={withPreview()} onTweak={() => {}} />)
    await screen.findByText('How do I reset the device?')
    expect(screen.getByRole('button', { name: 'Generate full dataset' })).toBeEnabled()
    expect(screen.queryByText('Out of date')).not.toBeInTheDocument()
  })

  it('marks the preview stale and disables Generate when the style changed', async () => {
    stubApi(pairsHandler)
    const project = withPreview({ style: makeStyle({ id: 'another-style-id' }) })
    renderRoutes(<PreviewResults project={project} onTweak={() => {}} />)
    expect(await screen.findByText('Out of date')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Generate full dataset' })).toBeDisabled()
  })

  it('shows the failure reason and keeps Generate disabled', async () => {
    const calls = stubApi(pairsHandler)
    const project = withPreview({
      status_message: 'Your Groq key ran out of quota.',
      latest_preview: makeRun({ state: 'failed', error: 'rate_limited' }),
    })
    renderRoutes(<PreviewResults project={project} onTweak={() => {}} />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Your Groq key ran out of quota.')
    expect(alert).toHaveTextContent('rate_limited')
    expect(screen.getByRole('button', { name: 'Generate full dataset' })).toBeDisabled()
    expect(calls).toHaveLength(0)
  })

  it('calls onTweak', async () => {
    stubApi(pairsHandler)
    const onTweak = vi.fn()
    renderRoutes(<PreviewResults project={withPreview()} onTweak={onTweak} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Tweak style' }))
    expect(onTweak).toHaveBeenCalled()
  })

  it('shows an error state when pairs cannot load', async () => {
    stubApi(() => jsonResponse({ error: 'boom', message: 'Pairs unavailable' }, 400))
    renderRoutes(<PreviewResults project={withPreview()} onTweak={() => {}} />)
    expect(await screen.findByText('Pairs unavailable')).toBeInTheDocument()
  })

  it('shows the estimate in minutes and starts generation after confirming', async () => {
    const calls = stubApi(
      pairsHandler,
      (url) => (url.pathname.endsWith('/estimate') ? jsonResponse(ESTIMATE) : undefined),
      (url, req) => (url.pathname.endsWith('/generate') && req.method === 'POST' ? jsonResponse(makeRun({ kind: 'full', state: 'queued' })) : undefined),
    )
    renderRoutes(<PreviewResults project={withPreview()} onTweak={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Generate full dataset' }))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText('about 1 h 30 min')).toBeInTheDocument()
    expect(within(dialog).getByText('120')).toBeInTheDocument()
    expect(within(dialog).getByText('500')).toBeInTheDocument()
    expect(within(dialog).getByText('750,000')).toBeInTheDocument()
    expect(within(dialog).getByText(/Fits within your free daily quota/)).toBeInTheDocument()
    expect(within(dialog).queryByText(/Gemini/)).not.toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Start generating' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.pathname.endsWith('/generate'))).toBe(true))
    expect(await calls.find((c) => c.url.pathname.endsWith('/generate'))!.request.json()).toEqual({ confirm: true })
  })

  it('shows days and the Gemini tip when the run takes more than a day', async () => {
    stubApi(pairsHandler, (url) =>
      url.pathname.endsWith('/estimate') ? jsonResponse({ ...ESTIMATE, est_minutes: 5000, est_days: 3.2, fits_daily_quota: false }) : undefined,
    )
    renderRoutes(<PreviewResults project={withPreview()} onTweak={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Generate full dataset' }))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText('about 4 days')).toBeInTheDocument()
    expect(within(dialog).getByText(/connect a Gemini key to finish faster/)).toBeInTheDocument()
    expect(within(dialog).getByText(/more than your free daily quota/)).toBeInTheDocument()
  })

  it('shows the API message when generation is refused', async () => {
    stubApi(
      pairsHandler,
      (url) => (url.pathname.endsWith('/estimate') ? jsonResponse(ESTIMATE) : undefined),
      (url, req) => (url.pathname.endsWith('/generate') && req.method === 'POST' ? jsonResponse({ error: 'generation_busy', message: 'busy' }, 409) : undefined),
    )
    renderRoutes(<PreviewResults project={withPreview()} onTweak={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Generate full dataset' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Start generating' }))
    expect(await screen.findByText('A generation run is already in progress.')).toBeInTheDocument()
  })
})
