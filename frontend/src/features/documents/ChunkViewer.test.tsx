import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ChunkViewer } from '@/features/documents/ChunkViewer'
import { jsonResponse, stubApi } from '@/test/api'
import { PROJECT_ID } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const chunk = {
  id: 'c1',
  document_id: 'd1',
  ordinal: 0,
  section_path: 'Intro > Setup',
  text: 'Install the thing and run it.',
  token_count: 42,
  page_start: 2,
  page_end: 3,
}

describe('ChunkViewer', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists chunks with section, pages and tokens, and expands text', async () => {
    stubApi((url) => (url.pathname.endsWith('/chunks') ? jsonResponse({ items: [chunk], next_cursor: null }) : undefined))
    renderRoutes(<ChunkViewer projectId={PROJECT_ID} />)
    expect(await screen.findByText('Intro > Setup')).toBeInTheDocument()
    expect(screen.getByText('pp. 2-3')).toBeInTheDocument()
    expect(screen.getByText('42 tokens')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Show more' }))
    expect(screen.getByRole('button', { name: 'Show less' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('sends q when searching and shows the empty result', async () => {
    const calls = stubApi((url) => {
      if (!url.pathname.endsWith('/chunks')) return undefined
      return jsonResponse(url.searchParams.get('q') ? { items: [], next_cursor: null } : { items: [chunk], next_cursor: null })
    })
    renderRoutes(<ChunkViewer projectId={PROJECT_ID} />)
    await screen.findByText('Intro > Setup')
    await userEvent.type(screen.getByLabelText('Search sections'), 'zebra')
    expect(await screen.findByText('No sections match your search')).toBeInTheDocument()
    expect(calls.some((c) => c.url.searchParams.get('q') === 'zebra')).toBe(true)
  })

  it('loads the next page using the cursor', async () => {
    const calls = stubApi((url) => {
      if (!url.pathname.endsWith('/chunks')) return undefined
      return url.searchParams.get('cursor')
        ? jsonResponse({ items: [{ ...chunk, id: 'c2', section_path: 'Second' }], next_cursor: null })
        : jsonResponse({ items: [chunk], next_cursor: '20' })
    })
    renderRoutes(<ChunkViewer projectId={PROJECT_ID} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Load more' }))
    expect(await screen.findByText('Second')).toBeInTheDocument()
    await waitFor(() => expect(calls.some((c) => c.url.searchParams.get('cursor') === '20')).toBe(true))
  })

  it('shows an error with retry', async () => {
    stubApi(() => jsonResponse({ error: 'boom', message: 'Chunks unavailable' }, 500))
    renderRoutes(<ChunkViewer projectId={PROJECT_ID} />)
    expect(await screen.findByRole('alert', {}, { timeout: 3000 })).toHaveTextContent('Chunks unavailable')
  })
})
