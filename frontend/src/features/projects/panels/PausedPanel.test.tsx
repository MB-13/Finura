import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { PausedPanel } from '@/features/projects/panels/PausedPanel'
import { clearAllTokens } from '@/features/training/token-store'
import { jsonResponse, META, stubApi, type Handler } from '@/test/api'
import { JOB_ID, makeJob, makeProject, PROJECT_ID } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const base: Handler[] = [
  (url) => (url.pathname === '/meta' ? jsonResponse(META) : undefined),
  (url) => (url.pathname.endsWith('/metrics') ? jsonResponse([{ step: 10, loss: 1.5, lr: null, at: '2026-01-01T00:00:00Z' }]) : undefined),
  (url) =>
    url.pathname.endsWith('/playground/status')
      ? jsonResponse({ available: true, reason: null, state: 'cold', source: 'checkpoint', checkpoint_step: 120, model: 'Qwen' })
      : undefined,
]

const paused = (over = {}, jobOver = {}) =>
  makeProject({
    status: 'paused',
    status_reason: 'session_ended',
    status_message: 'Your Colab session ended at 64%. Progress is saved. Open the notebook and run it again to continue.',
    active_job: makeJob({ state: 'paused', current_step: 128, max_steps: 200, checkpoint_step: 120, checkpoint_uploaded_at: new Date(Date.now() - 120_000).toISOString(), ...jobOver }),
    ...over,
  })

describe('PausedPanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    clearAllTokens()
  })

  it('shows the server message, progress saved, checkpoint info and the open-notebook link', async () => {
    stubApi(...base)
    renderRoutes(<PausedPanel project={paused()} />)
    expect(screen.getByText(/Your Colab session ended at 64%/)).toBeInTheDocument()
    expect(screen.getByText('60%')).toBeInTheDocument() // saved = checkpoint step 120 of 200
    expect(screen.getByRole('progressbar', { name: 'Progress saved' })).toBeInTheDocument()
    expect(screen.getByText(/Saved at step 120 · 2 min ago/)).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: /Open the notebook again/ })).toHaveAttribute('href', META.notebook_url)
    expect(screen.getByRole('button', { name: 'Generate a new token' })).toBeInTheDocument()
    expect(await screen.findByRole('img', { name: /Training loss over 1 point/ })).toBeInTheDocument()
  })

  it.each([
    ['session_ended', /session ended/],
    ['idle_timeout', /tab was idle/],
    ['no_gpu', /no free GPU/],
    ['stopped', /Training stopped/],
    ['heartbeat_timeout', /Training stopped/],
    ['user_stopped', /You stopped the notebook/],
  ])('falls back to copy for %s when the server sent no message', (reason, text) => {
    stubApi(...base)
    renderRoutes(<PausedPanel project={paused({ status_reason: reason, status_message: null })} />)
    expect(screen.getByText(text)).toBeInTheDocument()
  })

  it('downloads the latest checkpoint through the signed url', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    const calls = stubApi(...base, (url) =>
      url.pathname === `/projects/${PROJECT_ID}/training/${JOB_ID}/checkpoint/download` ? jsonResponse({ url: 'https://r2.example/ckpt.zip', expires_at: 1 }) : undefined,
    )
    renderRoutes(<PausedPanel project={paused()} />)
    await userEvent.click(screen.getByRole('button', { name: /Download latest checkpoint/ }))
    await waitFor(() => expect(open).toHaveBeenCalledWith('https://r2.example/ckpt.zip', '_blank', 'noopener,noreferrer'))
    expect(calls.some((c) => c.url.pathname.endsWith('/checkpoint/download'))).toBe(true)
    open.mockRestore()
  })

  it('disables the download when no checkpoint exists yet', () => {
    stubApi(...base)
    renderRoutes(<PausedPanel project={paused({}, { checkpoint_step: null, checkpoint_uploaded_at: null })} />)
    expect(screen.getByRole('button', { name: /Download latest checkpoint/ })).toBeDisabled()
  })

  it('links to the playground only when it is available', async () => {
    stubApi(...base)
    const { unmount } = renderRoutes(<PausedPanel project={paused()} />)
    expect(await screen.findByRole('link', { name: /Test this checkpoint in the playground/ })).toHaveAttribute('href', `/projects/${PROJECT_ID}/playground`)
    unmount()
    vi.unstubAllGlobals()
    stubApi(...base.slice(0, 2), (url) => (url.pathname.endsWith('/playground/status') ? jsonResponse({ available: false, reason: 'No checkpoint', state: 'cold' }) : undefined))
    renderRoutes(<PausedPanel project={paused()} />)
    await screen.findByRole('img', { name: /Training loss/ })
    await waitFor(() => expect(screen.queryByRole('link', { name: /Test this checkpoint/ })).not.toBeInTheDocument())
  })

  it('explains the automatic restart for a Kaggle job and hides the Colab and token UI', async () => {
    stubApi(...base)
    renderRoutes(
      <PausedPanel
        project={paused({ status_message: null }, { backend: 'kaggle', external_url: 'https://kaggle.com/code/alice/k', launch_attempts: 2 })}
      />,
    )
    expect(screen.getByText(/restarts automatically on your Kaggle account/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /View on Kaggle/ })).toHaveAttribute('href', 'https://kaggle.com/code/alice/k')
    expect(screen.getByText(/attempt 2 of 3/)).toBeInTheDocument()
    expect(screen.queryByText(/run the notebook again/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Open the notebook again/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Generate a new token' })).not.toBeInTheDocument()
    await screen.findByRole('img', { name: /Training loss/ })
  })

  it('explains the quota reset for a Kaggle job parked for no GPU', () => {
    stubApi(...base)
    renderRoutes(<PausedPanel project={paused({ status_reason: 'no_gpu', status_message: null }, { backend: 'kaggle' })} />)
    expect(screen.getByText(/GPU hours for this week are used up/)).toBeInTheDocument()
  })
})
