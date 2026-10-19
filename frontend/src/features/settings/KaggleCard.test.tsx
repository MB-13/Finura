import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { KaggleCard } from '@/features/settings/KaggleCard'
import { jsonResponse, stubApi, type Handler } from '@/test/api'
import { makeKaggle, type KaggleAccountOut } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const TOKEN = 'kgl_super_secret_token'

/** A stateful stub of /compute/kaggle. */
function kaggleApi(initial: KaggleAccountOut | null, afterPut?: () => KaggleAccountOut) {
  let account = initial
  const handler: Handler = (url, req) => {
    if (url.pathname === '/compute/kaggle' && req.method === 'GET') return jsonResponse(account)
    if (url.pathname === '/compute/kaggle' && req.method === 'PUT') {
      account = makeKaggle({ status: 'unchecked', gpu_hours_total: null, gpu_hours_used: null, quota_refresh_at: null })
      const res = jsonResponse(account)
      if (afterPut) setTimeout(() => (account = afterPut()), 50)
      return res
    }
    if (url.pathname === '/compute/kaggle/check' && req.method === 'POST') {
      account = makeKaggle({ status: 'unchecked' })
      return jsonResponse(account, 202)
    }
    if (url.pathname === '/compute/kaggle' && req.method === 'DELETE') {
      account = null
      return new Response(null, { status: 204 })
    }
    return undefined
  }
  return handler
}

describe('KaggleCard', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows the explanation, the setup steps and the form when not connected', async () => {
    stubApi(kaggleApi(null))
    renderRoutes(<KaggleCard />)
    expect(await screen.findByLabelText('Kaggle username')).toBeInTheDocument()
    expect(screen.getByText(/about 30 GPU-hours a week/)).toBeInTheDocument()
    const steps = screen.getByRole('list', { name: 'How to connect Kaggle' })
    expect(within(steps).getAllByRole('listitem')).toHaveLength(4)
    expect(within(steps).getByText('Verify your phone number')).toBeInTheDocument()
    expect(screen.getByLabelText('Kaggle API token')).toHaveAttribute('type', 'password')
    expect(screen.getByRole('button', { name: 'Connect Kaggle' })).toBeDisabled()
  })

  it('shows a loading state and an error state', async () => {
    stubApi((url) => (url.pathname === '/compute/kaggle' ? jsonResponse({ error: 'boom', message: 'Kaggle down' }, 500) : undefined))
    renderRoutes(<KaggleCard />)
    expect(screen.getByLabelText('Loading Kaggle account')).toBeInTheDocument()
    expect(await screen.findByText('Kaggle down')).toBeInTheDocument()
  })

  it('announces field errors and links them to their inputs', async () => {
    stubApi((url, req) =>
      url.pathname === '/compute/kaggle' && req.method === 'PUT'
        ? jsonResponse({ error: 'validation', message: 'Invalid', details: { fields: { username: ['Unknown user'], api_token: ['Bad token'] } } }, 422)
        : undefined,
      kaggleApi(null),
    )
    renderRoutes(<KaggleCard />)
    await userEvent.type(await screen.findByLabelText('Kaggle username'), 'alice')
    await userEvent.type(screen.getByLabelText('Kaggle API token'), TOKEN)
    await userEvent.click(screen.getByRole('button', { name: 'Connect Kaggle' }))
    await screen.findByText('Unknown user')
    expect(screen.getByLabelText('Kaggle username')).toHaveAccessibleDescription('Unknown user')
    expect(screen.getByLabelText('Kaggle API token')).toHaveAccessibleDescription(/Bad token/)
    expect(screen.getAllByRole('alert').map((a) => a.textContent)).toEqual(expect.arrayContaining(['Unknown user', 'Bad token']))
  })

  it('submits the form, clears the token, never shows it, and polls until the account is ok', async () => {
    const calls = stubApi(kaggleApi(null, () => makeKaggle({ status: 'ok' })))
    renderRoutes(<KaggleCard />)
    await userEvent.type(await screen.findByLabelText('Kaggle username'), 'alice')
    await userEvent.type(screen.getByLabelText('Kaggle API token'), TOKEN)
    await userEvent.click(screen.getByRole('button', { name: 'Connect Kaggle' }))

    const put = await waitFor(() => {
      const c = calls.find((x) => x.method === 'PUT')
      expect(c).toBeDefined()
      return c!
    })
    expect(await put.request.json()).toEqual({ username: 'alice', api_token: TOKEN })
    expect(await screen.findByText('Checking…')).toBeInTheDocument()
    expect(document.body.innerHTML).not.toContain(TOKEN)
    expect(await screen.findByText('Connected', {}, { timeout: 6000 })).toBeInTheDocument()
    expect(screen.getByText('…ab12')).toBeInTheDocument()
    expect(screen.getByText(/4.5 of 30 used/)).toBeInTheDocument()
    expect(document.body.innerHTML).not.toContain(TOKEN)
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(TOKEN)
  }, 15_000)

  it('shows an invalid token with the server message', async () => {
    stubApi(kaggleApi(makeKaggle({ status: 'invalid', status_message: 'Kaggle rejected this token.', gpu_hours_used: null, gpu_hours_total: null, quota_refresh_at: null })))
    renderRoutes(<KaggleCard />)
    expect(await screen.findByText('Invalid token')).toBeInTheDocument()
    expect(screen.getByText('Kaggle rejected this token.')).toBeInTheDocument()
  })

  it('shows no GPU quota with the reset time', async () => {
    stubApi(kaggleApi(makeKaggle({ status: 'no_gpu_quota', status_message: 'No GPU hours left this week.', gpu_hours_used: 30 })))
    renderRoutes(<KaggleCard />)
    expect(await screen.findByText('No GPU quota')).toBeInTheDocument()
    expect(screen.getByText('No GPU hours left this week.')).toBeInTheDocument()
    expect(screen.getByText(/30 of 30 used/)).toBeInTheDocument()
    expect(screen.getByText(/Resets/)).toBeInTheDocument()
  })

  it('re-checks the account', async () => {
    const calls = stubApi(kaggleApi(makeKaggle()))
    renderRoutes(<KaggleCard />)
    await userEvent.click(await screen.findByRole('button', { name: 'Re-check' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.pathname === '/compute/kaggle/check')).toBe(true))
    expect(await screen.findByText('Checking…')).toBeInTheDocument()
  })

  it('asks before disconnecting, then shows the form again', async () => {
    const calls = stubApi(kaggleApi(makeKaggle()))
    renderRoutes(<KaggleCard />)
    await userEvent.click(await screen.findByRole('button', { name: 'Disconnect' }))
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
    const dialog = await screen.findByRole('alertdialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Disconnect' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
    expect(await screen.findByLabelText('Kaggle username')).toBeInTheDocument()
  })
})
