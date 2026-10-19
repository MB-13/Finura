import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { RunNotebookPanel } from '@/features/training/RunNotebookPanel'
import { clearAllTokens, revealToken } from '@/features/training/token-store'
import { jsonResponse, META, stubApi, type Handler } from '@/test/api'
import { JOB_ID, makeJob, makeKaggle, makeProject, PROJECT_ID } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const meta: Handler = (url) => (url.pathname === '/meta' ? jsonResponse(META) : undefined)
const project = () => makeProject({ status: 'awaiting_run', active_job: makeJob({ state: 'created', current_step: 0 }) })

describe('RunNotebookPanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    clearAllTokens()
  })

  it('shows the four steps, the waiting indicator and the estimate', async () => {
    stubApi(meta)
    revealToken(JOB_ID, { token: 'dtj_first', notebookUrl: 'https://colab.example/create', expiresAt: '2026-02-01T00:00:00Z' })
    renderRoutes(<RunNotebookPanel project={project()} />)
    const steps = screen.getByRole('list', { name: 'Steps to run the notebook' })
    expect(within(steps).getAllByRole('listitem')).toHaveLength(4)
    expect(within(steps).getByText(/T4 GPU/)).toBeInTheDocument()
    expect(screen.getByText(/keep the tab open/)).toBeInTheDocument()
    expect(screen.getByText('Waiting for the notebook to connect…')).toBeInTheDocument()
    expect(screen.getByText(/usually takes about 45 min/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open in Colab/ })).toHaveAttribute('href', 'https://colab.example/create')
  })

  it('shows the token once with a copy button, then only its prefix after "I\'ve copied it"', async () => {
    const user = userEvent.setup()
    stubApi(meta)
    revealToken(JOB_ID, { token: 'dtj_first', notebookUrl: null, expiresAt: null })
    renderRoutes(<RunNotebookPanel project={project()} />)
    expect(screen.getByTestId('job-token')).toHaveTextContent('dtj_first')
    await user.click(screen.getByRole('button', { name: /Copy token/ }))
    expect(await navigator.clipboard.readText()).toBe('dtj_first')
    await user.click(screen.getByRole('button', { name: "I've copied it" }))
    expect(screen.queryByTestId('job-token')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Generate a new token' })).toHaveFocus()
    expect(screen.getByText(/dtj_ab12/)).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('dtj_first')
  })

  it('falls back to /meta for the notebook link and offers a new token when none is in memory', async () => {
    stubApi(meta)
    renderRoutes(<RunNotebookPanel project={project()} />)
    expect(screen.getByText(/dtj_ab12/)).toBeInTheDocument()
    expect(screen.getByText(/expires/)).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: /Open in Colab/ })).toHaveAttribute('href', META.notebook_url)
    expect(screen.getByRole('button', { name: 'Generate a new token' })).toBeInTheDocument()
  })

  it('rotates the token and shows the new one', async () => {
    const calls = stubApi(meta, (url, req) =>
      url.pathname === `/projects/${PROJECT_ID}/training/${JOB_ID}/token` && req.method === 'POST'
        ? jsonResponse({ token: 'dtj_rotated', expires_at: '2026-03-01T00:00:00Z' })
        : undefined,
    )
    renderRoutes(<RunNotebookPanel project={project()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Generate a new token' }))
    expect(await screen.findByTestId('job-token')).toHaveTextContent('dtj_rotated')
    expect(calls.some((c) => c.method === 'POST' && c.url.pathname.endsWith('/token'))).toBe(true)
  })

  it('asks before cancelling, then cancels the job', async () => {
    const calls = stubApi(meta, (url, req) =>
      url.pathname.endsWith(`/training/${JOB_ID}/cancel`) && req.method === 'POST' ? jsonResponse(makeProject({ status: 'in_review' })) : undefined,
    )
    renderRoutes(<RunNotebookPanel project={project()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Cancel training' }))
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
    const dialog = await screen.findByRole('alertdialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel training' }))
    await waitFor(() => expect(calls.some((c) => c.url.pathname.endsWith(`/training/${JOB_ID}/cancel`))).toBe(true))
  })

  it('shows a loading line when the job is not in the project yet', () => {
    stubApi(meta)
    renderRoutes(<RunNotebookPanel project={makeProject({ status: 'awaiting_run' })} />)
    expect(screen.getByText('Run the training notebook')).toBeInTheDocument()
    expect(screen.getByText('Loading your training job…')).toBeInTheDocument()
  })

  describe('Kaggle job', () => {
    const kaggleProject = (over = {}) =>
      makeProject({ status: 'awaiting_run', active_job: makeJob({ state: 'created', backend: 'kaggle', current_step: 0, ...over }) })

    it('shows "Starting on Kaggle" before the kernel exists, with no token or Colab UI', () => {
      stubApi(meta)
      revealToken(JOB_ID, { token: 'dtj_should_not_show', notebookUrl: 'https://colab.example/create', expiresAt: null })
      renderRoutes(<RunNotebookPanel project={kaggleProject()} />)
      expect(screen.getByText('Starting on Kaggle…')).toBeInTheDocument()
      expect(screen.queryByTestId('job-token')).not.toBeInTheDocument()
      expect(screen.queryByRole('list', { name: 'Steps to run the notebook' })).not.toBeInTheDocument()
      expect(screen.queryByRole('link', { name: /Open in Colab/ })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Generate a new token' })).not.toBeInTheDocument()
      expect(screen.queryByRole('link', { name: /View on Kaggle/ })).not.toBeInTheDocument()
      expect(document.body.textContent).not.toContain('dtj_')
    })

    it('shows the Kaggle link, the close-tab note and the restart note once launched', () => {
      stubApi(meta)
      renderRoutes(
        <RunNotebookPanel project={kaggleProject({ external_url: 'https://kaggle.com/code/alice/k', launch_attempts: 2 })} />,
      )
      expect(screen.getByText('Running on your Kaggle account')).toBeInTheDocument()
      expect(screen.getByText(/You can close this tab/)).toBeInTheDocument()
      expect(screen.getByRole('link', { name: /View on Kaggle/ })).toHaveAttribute('href', 'https://kaggle.com/code/alice/k')
      expect(screen.getByText(/Restarted automatically after the Kaggle session ended \(attempt 2 of 3\)/)).toBeInTheDocument()
    })

    it('shows which stage the Kaggle run is in before training starts', () => {
      stubApi(meta)
      const launched = { external_url: 'https://kaggle.com/code/alice/k' }
      const { unmount } = renderRoutes(
        <RunNotebookPanel project={kaggleProject({ ...launched, runtime_info: { kaggle_status: 'QUEUED' } })} />,
      )
      const stages = screen.getByRole('list', { name: 'Kaggle progress' })
      expect(within(stages).getAllByRole('listitem')).toHaveLength(4)
      expect(within(stages).getByText('Waiting for a free GPU').closest('li')).toHaveAttribute('aria-current', 'step')
      expect(screen.getByText(/Kaggle queues runs until a T4 is free/)).toBeInTheDocument()
      unmount()
      renderRoutes(<RunNotebookPanel project={kaggleProject({ ...launched, runtime_info: { kaggle_status: 'RUNNING' } })} />)
      expect(screen.getByText('Setting up').closest('li')).toHaveAttribute('aria-current', 'step')
      expect(screen.getByText(/Installing the training libraries/)).toBeInTheDocument()
    })

    it('does not mention restarts on the first attempt and can be cancelled', async () => {
      const calls = stubApi(meta, (url, req) =>
        url.pathname.endsWith(`/training/${JOB_ID}/cancel`) && req.method === 'POST' ? jsonResponse(makeProject({ status: 'in_review' })) : undefined,
      )
      renderRoutes(<RunNotebookPanel project={kaggleProject({ launch_attempts: 1 })} />)
      expect(screen.queryByText(/Restarted automatically/)).not.toBeInTheDocument()
      await userEvent.click(screen.getByRole('button', { name: 'Cancel training' }))
      await userEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Cancel training' }))
      await waitFor(() => expect(calls.some((c) => c.url.pathname.endsWith('/cancel'))).toBe(true))
    })
  })

  it('switches a waiting Colab job to Kaggle when Kaggle is connected', async () => {
    const user = userEvent.setup()
    const calls = stubApi(meta, (url, req) => {
      if (url.pathname === '/compute/kaggle') return jsonResponse(makeKaggle({ status: 'ok' }))
      if (url.pathname.endsWith(`/training/${JOB_ID}/switch`) && req.method === 'POST')
        return jsonResponse({ job: makeJob({ backend: 'kaggle' }), token: null, notebook_url: null })
      return undefined
    })
    renderRoutes(<RunNotebookPanel project={project()} />)
    await user.click(await screen.findByRole('button', { name: 'Run on Kaggle instead' }))
    await waitFor(() => expect(calls.some((c) => c.url.pathname.endsWith(`/training/${JOB_ID}/switch`))).toBe(true))
    const sent = calls.find((c) => c.url.pathname.endsWith('/switch'))!
    expect(await sent.request.json()).toEqual({ backend: 'kaggle' })
  })

  it('points to Settings when Kaggle is not connected', async () => {
    stubApi(meta, (url) => (url.pathname === '/compute/kaggle' ? jsonResponse(null) : undefined))
    renderRoutes(<RunNotebookPanel project={project()} />)
    expect(await screen.findByRole('link', { name: /Connect Kaggle in Settings/ })).toHaveAttribute('href', '/settings')
    expect(screen.queryByRole('button', { name: 'Run on Kaggle instead' })).not.toBeInTheDocument()
  })
})
