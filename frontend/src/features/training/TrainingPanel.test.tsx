import { act, screen, waitFor } from '@testing-library/react'

import { TrainingPanel } from '@/features/training/TrainingPanel'
import { handleProjectEvent } from '@/lib/sse'
import { qk } from '@/lib/query-keys'
import { jsonResponse, stubApi, type Handler } from '@/test/api'
import { JOB_ID, makeJob, makeProject, PROJECT_ID } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const at = (sec: number) => new Date(Date.UTC(2026, 0, 1, 0, 0, sec)).toISOString()
const METRICS = [
  { step: 10, loss: 2.0, lr: 0.0002, at: at(0) },
  { step: 20, loss: 1.6, lr: 0.0002, at: at(20) },
  { step: 30, loss: 1.4, lr: 0.0002, at: at(40) },
]
const metrics: Handler = (url) => (url.pathname === `/projects/${PROJECT_ID}/training/${JOB_ID}/metrics` ? jsonResponse(METRICS) : undefined)

function training(over = {}) {
  return makeProject({
    status: 'training',
    active_job: makeJob({
      current_step: 50,
      max_steps: 200,
      last_heartbeat_at: new Date(Date.now() - 12_000).toISOString(),
      checkpoint_step: 40,
      checkpoint_uploaded_at: new Date(Date.now() - 4 * 60_000).toISOString(),
      ...over,
    }),
  })
}

describe('TrainingPanel', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows progress %, GPU, heartbeat age, checkpoint info and the tip', async () => {
    stubApi(metrics)
    renderRoutes(<TrainingPanel project={training()} />)
    expect(screen.getByText('Step 50 of 200')).toBeInTheDocument()
    expect(screen.getByText('25%')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Training progress' })).toBeInTheDocument()
    expect(screen.getByText(/Tesla T4 · 15 GB/)).toBeInTheDocument()
    expect(screen.getByText(/Updated 12 s ago/)).toBeInTheDocument()
    expect(screen.getByText(/Saved at step 40 · 4 min ago/)).toBeInTheDocument()
    expect(screen.getByText(/Keep the Colab tab open/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel training' })).toBeInTheDocument()
  })

  it('computes an ETA from the metric timestamps and draws the loss chart', async () => {
    stubApi(metrics)
    renderRoutes(<TrainingPanel project={training({ current_step: 30 })} />)
    // 20 steps in 40 s -> 0.5 steps/s, 170 steps left -> 340 s
    expect(await screen.findByText('About 6 min left')).toBeInTheDocument()
    const chart = await screen.findByRole('img', { name: /Training loss over 3 points: latest 1.400 at step 30/ })
    expect(chart.querySelector('polyline')?.getAttribute('points')?.split(' ')).toHaveLength(3)
  })

  it('shows an empty chart message when there are no metrics yet', async () => {
    stubApi((url) => (url.pathname.endsWith('/metrics') ? jsonResponse([]) : undefined))
    renderRoutes(<TrainingPanel project={training()} />)
    expect(await screen.findByText(/loss curve appears once training reports/)).toBeInTheDocument()
    expect(screen.getByText('Working out the time left…')).toBeInTheDocument()
  })

  it('shows an error state when metrics fail', async () => {
    stubApi((url) => (url.pathname.endsWith('/metrics') ? jsonResponse({ error: 'boom', message: 'Metrics unavailable' }, 400) : undefined))
    renderRoutes(<TrainingPanel project={training()} />)
    expect(await screen.findByText('Metrics unavailable')).toBeInTheDocument()
  })

  it('extends the chart and progress from train_metrics events, de-duplicating by step', async () => {
    stubApi(metrics)
    const { queryClient } = renderRoutes(<TrainingPanel project={training({ current_step: 30 })} />)
    queryClient.setQueryData(qk.project(PROJECT_ID), training({ current_step: 30 }))
    await screen.findByRole('img', { name: /over 3 points/ })
    const send = (data: unknown) =>
      act(() => {
        handleProjectEvent(queryClient, PROJECT_ID, { id: '', event: 'train_metrics', data: JSON.stringify(data), retry: undefined })
      })
    send({ step: 40, max_steps: 200, loss: 1.1, lr: 0.0002, at: at(60) })
    send({ step: 40, max_steps: 200, loss: 1.1, lr: 0.0002, at: at(60) })
    expect(await screen.findByRole('img', { name: /over 4 points: latest 1.100 at step 40/ })).toBeInTheDocument()
    await waitFor(() => expect(queryClient.getQueryData<ReturnType<typeof makeProject>>(qk.project(PROJECT_ID))?.active_job).toMatchObject({ current_step: 40, last_loss: 1.1 }))
  })

  it('shows a loading line when the job is missing', () => {
    stubApi(metrics)
    renderRoutes(<TrainingPanel project={makeProject({ status: 'training' })} />)
    expect(screen.getByText('Training your model')).toBeInTheDocument()
    expect(screen.getByText('Loading your training job…')).toBeInTheDocument()
  })

  it('hides Colab copy and links to Kaggle for a Kaggle job', async () => {
    stubApi(metrics)
    renderRoutes(<TrainingPanel project={training({ backend: 'kaggle', external_url: 'https://kaggle.com/code/alice/k', launch_attempts: 2 })} />)
    expect(screen.queryByText(/Colab/)).not.toBeInTheDocument()
    expect(screen.getByText(/You can close this tab/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /View on Kaggle/ })).toHaveAttribute('href', 'https://kaggle.com/code/alice/k')
    expect(screen.getByText(/attempt 2 of 3/)).toBeInTheDocument()
    expect(screen.getByText('Step 50 of 200')).toBeInTheDocument()
  })
})
