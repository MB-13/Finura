import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { DeleteAccountCard } from '@/features/settings/DeleteAccountCard'
import { NotificationsCard } from '@/features/settings/NotificationsCard'
import { jsonResponse, stubApi } from '@/test/api'
import { renderRoutes } from '@/test/render'

const ME = { id: 'u1', email: 'a@example.com', display_name: null, onboarding_done: true, email_notifications: true }

describe('DeleteAccountCard', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('requires typing DELETE, then deletes, signs out and goes to the landing page', async () => {
    const calls = stubApi((url, req) => (url.pathname === '/me' && req.method === 'DELETE' ? jsonResponse({}, 202) : undefined))
    const signOut = vi.fn(async () => {})
    const { router } = renderRoutes(<DeleteAccountCard />, { path: '/settings', auth: { signOut }, routes: [{ path: '/', element: <div>Landing</div> }] })
    await userEvent.click(screen.getByRole('button', { name: 'Delete account' }))
    const confirm = await screen.findByRole('button', { name: 'Delete everything' })
    expect(confirm).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/to confirm/), 'delete')
    expect(confirm).toBeDisabled()
    await userEvent.clear(screen.getByLabelText(/to confirm/))
    await userEvent.type(screen.getByLabelText(/to confirm/), 'DELETE')
    expect(confirm).toBeEnabled()
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
    await userEvent.click(confirm)
    await waitFor(() => expect(signOut).toHaveBeenCalled())
    await waitFor(() => expect(router.state.location.pathname).toBe('/'))
    expect(calls.some((c) => c.method === 'DELETE' && c.url.pathname === '/me')).toBe(true)
  })

  it('shows the error and stays signed in when deleting fails', async () => {
    stubApi((url, req) => (url.pathname === '/me' && req.method === 'DELETE' ? jsonResponse({ error: 'boom', message: 'Try later' }, 500) : undefined))
    const signOut = vi.fn(async () => {})
    renderRoutes(<DeleteAccountCard />, { auth: { signOut } })
    await userEvent.click(screen.getByRole('button', { name: 'Delete account' }))
    await userEvent.type(await screen.findByLabelText(/to confirm/), 'DELETE')
    await userEvent.click(screen.getByRole('button', { name: 'Delete everything' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Try later')
    expect(signOut).not.toHaveBeenCalled()
  })
})

describe('NotificationsCard', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('toggles email notifications with PATCH /me', async () => {
    const calls = stubApi((url, req) => (url.pathname === '/me' && req.method === 'PATCH' ? jsonResponse({ ...ME, email_notifications: false }) : undefined))
    renderRoutes(<NotificationsCard me={ME} />)
    const box = screen.getByRole('checkbox', { name: /Email me when training pauses/ })
    expect(box).toBeChecked()
    await userEvent.click(box)
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true))
    expect(await calls.find((c) => c.method === 'PATCH')!.request.json()).toEqual({ email_notifications: false })
  })
})
