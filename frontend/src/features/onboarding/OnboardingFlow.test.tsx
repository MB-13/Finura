import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { OnboardingFlow } from '@/features/onboarding/OnboardingFlow'
import { Projects } from '@/routes/Projects'
import { jsonResponse, stubApi, type Handler } from '@/test/api'
import { makeProject } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const ME = { id: 'u1', email: 'a@example.com', display_name: null, onboarding_done: false, email_notifications: true }
const me = (over = {}): Handler => (url, req) => (url.pathname === '/me' && req.method === 'GET' ? jsonResponse({ ...ME, ...over }) : undefined)
const patchMe: Handler = (url, req) => (url.pathname === '/me' && req.method === 'PATCH' ? jsonResponse({ ...ME, onboarding_done: true }) : undefined)
const projects: Handler = (url, req) => (url.pathname === '/projects' && req.method === 'GET' ? jsonResponse({ items: [], next_cursor: null }) : undefined)

describe('onboarding', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('redirects /projects to /onboarding when onboarding is not done', async () => {
    stubApi(me(), projects)
    const { router } = renderRoutes(<Projects />, { path: '/projects', routes: [{ path: '/onboarding', element: <div>Onboarding page</div> }] })
    await waitFor(() => expect(router.state.location.pathname).toBe('/onboarding'))
    expect(await screen.findByText('Onboarding page')).toBeInTheDocument()
  })

  it('does not redirect when onboarding is done', async () => {
    stubApi(me({ onboarding_done: true }), projects)
    const { router } = renderRoutes(<Projects />, { path: '/projects', routes: [{ path: '/onboarding', element: <div>Onboarding page</div> }] })
    expect(await screen.findByText('No projects yet')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/projects')
  })

  it('walks the three steps', async () => {
    stubApi(me(), patchMe)
    renderRoutes(<OnboardingFlow />)
    expect(screen.getByText(/Fine-tuning teaches style, not facts/)).toBeInTheDocument()
    expect(screen.getByText(/your own free Google Colab GPU/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByRole('link', { name: /Open settings to add a key/ })).toHaveAttribute('href', '/settings')
    // focus follows the step: the clicked button may unmount, so the new step's heading takes it
    expect(screen.getByRole('heading', { level: 2, name: 'Connect an AI key' })).toHaveFocus()
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByLabelText('Project name')).toBeInTheDocument()
    // "Next" is gone on the last step; focus must not fall back to <body>
    expect(screen.getByRole('heading', { level: 2, name: 'Create your first project' })).toHaveFocus()
  })

  it('skipping marks onboarding done and goes to /projects without bouncing back', async () => {
    const calls = stubApi(me(), patchMe, projects)
    const { router } = renderRoutes(<OnboardingFlow />, { path: '/onboarding', routes: [{ path: '/projects', element: <Projects /> }] })
    await userEvent.click(screen.getByRole('button', { name: 'Skip for now' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/projects'))
    const patch = calls.find((c) => c.method === 'PATCH')!
    expect(await patch.request.json()).toEqual({ onboarding_done: true })
    expect(await screen.findByText('No projects yet')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/projects')
  })

  it('creating the first project saves onboarding_done and opens the project', async () => {
    const calls = stubApi(patchMe, (url, req) => (url.pathname === '/projects' && req.method === 'POST' ? jsonResponse(makeProject({ name: 'Docs' }), 201) : undefined))
    const { router } = renderRoutes(<OnboardingFlow />, { path: '/onboarding', routes: [{ path: '/projects/:id', element: <div>Workspace</div> }] })
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await userEvent.type(screen.getByLabelText('Project name'), 'Docs')
    await userEvent.click(screen.getByRole('button', { name: 'Create project' }))
    expect(await screen.findByText('Workspace')).toBeInTheDocument()
    expect(router.state.location.pathname).toMatch(/^\/projects\/1111/)
    expect(calls.some((c) => c.method === 'PATCH' && c.url.pathname === '/me')).toBe(true)
  })
})
