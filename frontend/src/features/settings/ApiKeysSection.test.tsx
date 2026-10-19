import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ApiKeysSection } from '@/features/settings/ApiKeysSection'
import { jsonResponse, stubApi, type Handler } from '@/test/api'
import { makeKey, PROVIDERS } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const providers: Handler = (url) => (url.pathname === '/providers' ? jsonResponse(PROVIDERS) : undefined)

describe('ApiKeysSection', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows a card per provider with the recommended badge, note and help link', async () => {
    stubApi(providers, (url) => (url.pathname === '/keys' ? jsonResponse([]) : undefined))
    renderRoutes(<ApiKeysSection />)
    const groq = await screen.findByLabelText('Groq key')
    expect(within(groq).getByText('Recommended')).toBeInTheDocument()
    expect(within(groq).getByRole('link', { name: /Get a free key/ })).toHaveAttribute('href', 'https://console.groq.com/keys')
    expect(screen.getByText('Not available in the EU/UK.')).toBeInTheDocument()
  })

  it('shows only the masked key, and never re-displays what was typed after saving', async () => {
    const calls = stubApi(
      providers,
      (url, req) => (url.pathname === '/keys/groq' && req.method === 'PUT' ? jsonResponse(makeKey({ status: 'unverified' })) : undefined),
      (url) => (url.pathname === '/keys' ? jsonResponse([makeKey({ provider: 'groq', status: 'valid' })]) : undefined),
    )
    renderRoutes(<ApiKeysSection />)
    const groq = await screen.findByLabelText('Groq key')
    expect(within(groq).getByText('…1234')).toBeInTheDocument()
    const input = within(groq).getByLabelText('Replace Groq key')
    expect(input).toHaveAttribute('type', 'password')
    expect(input).toHaveValue('')
    await userEvent.type(input, 'gsk_secret_abcd9999')
    await userEvent.click(within(groq).getByRole('button', { name: 'Replace key' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    const put = calls.find((c) => c.method === 'PUT')!
    expect(await put.request.json()).toMatchObject({ api_key: 'gsk_secret_abcd9999' })
    await waitFor(() => expect(input).toHaveValue(''))
    expect(document.body.textContent).not.toContain('gsk_secret_abcd9999')
  })

  it('links a rejected key to its input as an announced error', async () => {
    stubApi(
      providers,
      (url, req) =>
        url.pathname === '/keys/groq' && req.method === 'PUT'
          ? jsonResponse({ error: 'validation', message: 'Invalid', details: { fields: { api_key: ['That key was rejected'] } } }, 422)
          : undefined,
      (url) => (url.pathname === '/keys' ? jsonResponse([]) : undefined),
    )
    renderRoutes(<ApiKeysSection />)
    const groq = await screen.findByLabelText('Groq key')
    const input = within(groq).getByLabelText('Groq API key')
    await userEvent.type(input, 'gsk_bad')
    await userEvent.click(within(groq).getByRole('button', { name: 'Save key' }))
    expect(await within(groq).findByRole('alert')).toHaveTextContent('That key was rejected')
    expect(input).toHaveAccessibleDescription('That key was rejected')
  })

  it('requires the terms checkbox before a Gemini key can be saved', async () => {
    const calls = stubApi(
      providers,
      (url, req) => (url.pathname === '/keys/gemini' && req.method === 'PUT' ? jsonResponse(makeKey({ provider: 'gemini', terms_acknowledged: true })) : undefined),
      (url) => (url.pathname === '/keys' ? jsonResponse([]) : undefined),
    )
    renderRoutes(<ApiKeysSection />)
    const gemini = await screen.findByLabelText('Gemini key')
    await userEvent.type(within(gemini).getByLabelText('Gemini API key'), 'AIza-key')
    const save = within(gemini).getByRole('button', { name: 'Save key' })
    expect(save).toBeDisabled()
    await userEvent.click(within(gemini).getByRole('checkbox'))
    expect(save).toBeEnabled()
    await userEvent.click(save)
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    expect(await calls.find((c) => c.method === 'PUT')!.request.json()).toMatchObject({ terms_acknowledged: true })
  })

  it('shows status chips for invalid, quota and checking keys', async () => {
    stubApi(
      providers,
      (url) =>
        url.pathname === '/keys'
          ? jsonResponse([
              makeKey({ provider: 'groq', status: 'invalid' }),
              makeKey({ provider: 'gemini', status: 'unverified', priority: 1 }),
            ])
          : undefined,
    )
    renderRoutes(<ApiKeysSection />)
    expect(await within(await screen.findByLabelText('Groq key')).findByText('Invalid key')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Gemini key')).getByText('Checking…')).toBeInTheDocument()
  })

  it('shows the quota reset time for exhausted keys', async () => {
    stubApi(providers, (url) =>
      url.pathname === '/keys' ? jsonResponse([makeKey({ status: 'quota_exhausted', quota_reset_at: '2026-01-01T12:30:00Z' })]) : undefined,
    )
    renderRoutes(<ApiKeysSection />)
    expect(await screen.findByText(/Quota used until/)).toBeInTheDocument()
  })

  it('confirms before removing a key', async () => {
    const calls = stubApi(
      providers,
      (url, req) => (url.pathname === '/keys/groq' && req.method === 'DELETE' ? new Response(null, { status: 204 }) : undefined),
      (url) => (url.pathname === '/keys' ? jsonResponse([makeKey()]) : undefined),
    )
    renderRoutes(<ApiKeysSection />)
    const groq = await screen.findByLabelText('Groq key')
    await userEvent.click(within(groq).getByRole('button', { name: /Remove/ }))
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
    await userEvent.click(await screen.findByRole('button', { name: 'Remove key' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
  })

  it('swaps priorities when moving a key up', async () => {
    const calls = stubApi(
      providers,
      (_url, req) => (req.method === 'PATCH' ? jsonResponse(makeKey()) : undefined),
      (url) =>
        url.pathname === '/keys'
          ? jsonResponse([makeKey({ provider: 'groq', priority: 0 }), makeKey({ provider: 'gemini', priority: 1 })])
          : undefined,
    )
    renderRoutes(<ApiKeysSection />)
    await userEvent.click(within(await screen.findByLabelText('Gemini key')).getByRole('button', { name: 'Move Gemini up' }))
    await waitFor(() => expect(calls.filter((c) => c.method === 'PATCH')).toHaveLength(2))
    const bodies = await Promise.all(calls.filter((c) => c.method === 'PATCH').map(async (c) => [c.url.pathname, await c.request.json()]))
    expect(Object.fromEntries(bodies)).toEqual({ '/keys/gemini': { priority: 0 }, '/keys/groq': { priority: 1 } })
  })

  it('shows an error state with retry', async () => {
    stubApi(() => jsonResponse({ error: 'boom', message: 'Keys unavailable' }, 500))
    renderRoutes(<ApiKeysSection />)
    expect(await screen.findByRole('alert', {}, { timeout: 3000 })).toHaveTextContent(/unavailable/)
  })
})
