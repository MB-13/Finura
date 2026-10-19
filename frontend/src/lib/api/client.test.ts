import { ApiError, createApi, toApiError, unwrap } from '@/lib/api/client'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('api client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('attaches the Supabase access token as a bearer token', async () => {
    const fetchMock = vi.fn(async (_req: Request) => jsonResponse({ status: 'ok' }))
    vi.stubGlobal('fetch', fetchMock)
    const client = createApi('http://api.test', async () => 'token-123')

    await client.GET('/healthz')

    const req = fetchMock.mock.calls[0]![0]
    expect(req.url).toBe('http://api.test/healthz')
    expect(req.headers.get('Authorization')).toBe('Bearer token-123')
  })

  it('sends no Authorization header when signed out', async () => {
    const fetchMock = vi.fn(async (_req: Request) => jsonResponse({ status: 'ok' }))
    vi.stubGlobal('fetch', fetchMock)
    await createApi('http://api.test', async () => null).GET('/healthz')
    expect(fetchMock.mock.calls[0]![0].headers.has('Authorization')).toBe(false)
  })

  it('unwrap throws ApiError with the API error envelope', async () => {
    vi.stubGlobal('fetch', async () => jsonResponse({ error: 'unauthorized', message: 'Authentication required' }, 401))
    const result = await createApi('http://api.test', async () => null).GET('/me')
    expect(() => unwrap(result)).toThrow(ApiError)
    try {
      unwrap(result)
    } catch (e) {
      expect(e).toMatchObject({ status: 401, code: 'unauthorized', message: 'Authentication required' })
    }
  })
})

describe('toApiError', () => {
  it('exposes 422 field errors', () => {
    const err = toApiError(422, {
      error: 'validation_error',
      message: 'Invalid request',
      details: { fields: { display_name: ['too short'] } },
    })
    expect(err.fieldErrors).toEqual({ display_name: ['too short'] })
  })

  it('falls back for non-envelope bodies', () => {
    const err = toApiError(502, 'Bad gateway')
    expect(err.code).toBe('http_error')
    expect(err.fieldErrors).toEqual({})
  })
})
