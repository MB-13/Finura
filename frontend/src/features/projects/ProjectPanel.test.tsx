import { screen } from '@testing-library/react'

import { ProjectPanel } from '@/features/projects/ProjectPanel'
import type { ProjectStatus } from '@/features/projects/api'
import { jsonResponse, META, stubApi } from '@/test/api'
import { makeProject } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const expected: Record<ProjectStatus, string> = {
  draft: 'Upload your documents',
  uploaded: 'Upload your documents',
  parsing: 'Reading your documents',
  awaiting_style: 'Describe how your model should answer',
  previewing: 'Generating a preview',
  generating: 'Generating your dataset',
  in_review: 'Review your dataset',
  awaiting_run: 'Run the training notebook',
  training: 'Training your model',
  paused: 'Training is paused',
  evaluating: 'Evaluating your model',
  ready: 'Your model is ready',
  failed: 'Something went wrong',
}

describe('ProjectPanel', () => {
  beforeEach(() => {
    stubApi(
      (url) => (url.pathname === '/meta' ? jsonResponse(META) : undefined),
      (url) => (url.pathname.endsWith('/documents') ? jsonResponse([]) : undefined),
      (url) => (url.pathname === '/keys' ? jsonResponse([]) : undefined),
      (url) => (url.pathname === '/providers' ? jsonResponse([]) : undefined),
      (url) => (url.pathname === '/style-templates' ? jsonResponse([]) : undefined),
      (url) => (url.pathname.endsWith('/dataset/stats') ? jsonResponse({ kept: 0, train: 0, eval: 0, dropped_by_reason: {}, avg_correctness: null, avg_style: null, answer_words: {} }) : undefined),
      (url) => (url.pathname.endsWith('/chunks') ? jsonResponse({ items: [], next_cursor: null }) : undefined),
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  it.each(Object.entries(expected) as [ProjectStatus, string][])('renders the right panel for %s', async (status, title) => {
    renderRoutes(<ProjectPanel project={makeProject({ status })} />)
    expect(await screen.findByText(title)).toBeInTheDocument()
  })

  it('shows the pause reason and how to continue', async () => {
    renderRoutes(<ProjectPanel project={makeProject({ status: 'paused', status_reason: 'colab_idle' })} />)
    expect(await screen.findByText(/colab idle/)).toBeInTheDocument()
    expect(screen.getByText(/run the notebook again/)).toBeInTheDocument()
  })

  it('shows the failure message and Retry only when allowed', async () => {
    const failed = makeProject({ status: 'failed', status_message: 'Parser crashed' })
    const { unmount } = renderRoutes(<ProjectPanel project={failed} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Parser crashed')
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
    unmount()
    renderRoutes(<ProjectPanel project={{ ...failed, allowed_actions: ['retry'] }} />)
    expect(await screen.findByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})
