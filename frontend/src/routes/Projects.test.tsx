import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { Projects } from '@/routes/Projects'
import { jsonResponse, stubApi } from '@/test/api'
import { makeProject, PROJECT_ID } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const summary = (overrides = {}) => {
  const { id, name, status, status_message, base_model_id, created_at, updated_at } = makeProject()
  return { id, name, status, status_message, base_model_id, created_at, updated_at, ...overrides }
}

function renderPage() {
  return renderRoutes(<Projects />, {
    path: '/projects',
    routes: [{ path: '/projects/:id', element: <div>Workspace opened</div> }],
  })
}

describe('Projects page', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists projects with a status badge and link', async () => {
    stubApi((url, req) =>
      url.pathname === '/projects' && req.method === 'GET'
        ? jsonResponse({
            items: [summary({ name: 'Alpha', status: 'parsing' }), summary({ id: 'x2', name: 'Beta', status: 'ready' })],
            next_cursor: null,
          })
        : undefined,
    )
    renderPage()
    expect(await screen.findByRole('link', { name: 'Alpha' })).toHaveAttribute('href', `/projects/${PROJECT_ID}`)
    expect(screen.getByText('Reading documents')).toBeInTheDocument()
    expect(screen.getByText('Ready')).toBeInTheDocument()
    expect(screen.queryByText(/Signed in as/)).not.toBeInTheDocument()
  })

  it('shows the empty state', async () => {
    stubApi((url) => (url.pathname === '/projects' ? jsonResponse({ items: [], next_cursor: null }) : undefined))
    renderPage()
    expect(await screen.findByText('No projects yet')).toBeInTheDocument()
  })

  it('shows an error with retry when the API fails', async () => {
    stubApi(() => jsonResponse({ error: 'unauthorized', message: 'Session expired' }, 401))
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('Session expired')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('creates a project and opens it', async () => {
    const calls = stubApi((url, req) => {
      if (url.pathname !== '/projects') return undefined
      if (req.method === 'POST') return jsonResponse(makeProject({ name: 'Fresh' }), 201)
      return jsonResponse({ items: [], next_cursor: null })
    })
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /New project/ }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText('Project name'), 'Fresh')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create project' }))
    expect(await screen.findByText('Workspace opened')).toBeInTheDocument()
    const post = calls.find((c) => c.method === 'POST')!
    expect(await post.request.json()).toEqual({ name: 'Fresh' })
  })

  it('creates a project from the empty-state "Create your first project" button', async () => {
    const calls = stubApi((url, req) => {
      if (url.pathname !== '/projects') return undefined
      if (req.method === 'POST') return jsonResponse(makeProject({ name: 'First' }), 201)
      return jsonResponse({ items: [], next_cursor: null })
    })
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /Create your first project/ }))
    const dialog = await screen.findByRole('dialog', { name: 'New project' })
    await userEvent.type(within(dialog).getByLabelText('Project name'), 'First')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create project' }))
    expect(await screen.findByText('Workspace opened')).toBeInTheDocument()
    expect(await calls.find((c) => c.method === 'POST')!.request.json()).toEqual({ name: 'First' })
  })

  it('creates a project from the header button while projects exist', async () => {
    const calls = stubApi((url, req) => {
      if (url.pathname !== '/projects') return undefined
      if (req.method === 'POST') return jsonResponse(makeProject({ name: 'Second' }), 201)
      return jsonResponse({ items: [summary({ name: 'Alpha' })], next_cursor: null })
    })
    renderPage()
    await screen.findByRole('link', { name: 'Alpha' })
    await userEvent.click(screen.getByRole('button', { name: /New project/ }))
    const dialog = await screen.findByRole('dialog', { name: 'New project' })
    await userEvent.type(within(dialog).getByLabelText('Project name'), 'Second')
    await userEvent.keyboard('{Enter}')
    expect(await screen.findByText('Workspace opened')).toBeInTheDocument()
    expect(await calls.find((c) => c.method === 'POST')!.request.json()).toEqual({ name: 'Second' })
  })

  it('validates an empty name without calling the API', async () => {
    const calls = stubApi((url) => (url.pathname === '/projects' ? jsonResponse({ items: [], next_cursor: null }) : undefined))
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /New project/ }))
    await userEvent.click(await screen.findByRole('button', { name: 'Create project' }))
    expect(await screen.findByText('Give your project a name.')).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
  })

  it('confirms before deleting', async () => {
    const calls = stubApi((url, req) => {
      if (url.pathname === `/projects/${PROJECT_ID}` && req.method === 'DELETE') return new Response(null, { status: 202 })
      if (url.pathname === '/projects') return jsonResponse({ items: [summary({ name: 'Alpha' })], next_cursor: null })
      return undefined
    })
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Actions for Alpha' }))
    await userEvent.click(await screen.findByRole('menuitem', { name: /Delete/ }))
    const dialog = await screen.findByRole('alertdialog')
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete project' }))
    await screen.findByText('Project deleted').catch(() => undefined)
    expect(calls.some((c) => c.method === 'DELETE')).toBe(true)
  })
})
