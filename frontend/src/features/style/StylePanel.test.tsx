import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { StylePanel } from '@/features/style/StylePanel'
import { jsonResponse, stubApi, type Handler } from '@/test/api'
import { DATASET_FORMATS, makeKey, makeProject, makeRun, makeStyle, PROVIDERS } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const TEMPLATES = [
  {
    key: 'support',
    name: 'Support agent',
    description: 'Helpful and brief',
    defaults: {
      template_key: 'support',
      description: 'You are a patient support agent who solves problems step by step.',
      tone: 'friendly',
      length: 'short',
      format: 'bullets',
      language: 'en',
      examples: [
        { input: 'It broke', output: 'Sorry! Try this.' },
        { input: 'Where is X?', output: 'In settings.' },
      ],
      system_prompt_in_data: false,
    },
  },
]

const base: Handler[] = [
  (url) => (url.pathname === '/style-templates' ? jsonResponse(TEMPLATES) : undefined),
  (url) => (url.pathname === '/providers' ? jsonResponse(PROVIDERS) : undefined),
  (url) => (url.pathname === '/keys' ? jsonResponse([makeKey()]) : undefined),
  (url) => (url.pathname === '/dataset-formats' ? jsonResponse(DATASET_FORMATS) : undefined),
]

const project = () => makeProject({ status: 'awaiting_style' })

async function fillMinimal() {
  await userEvent.type(screen.getByLabelText('Style description'), 'A friendly support agent who is brief.')
  await userEvent.type(screen.getByLabelText('Example 1 question'), 'How?')
  await userEvent.type(screen.getByLabelText('Example 1 answer'), 'Like this.')
}

describe('StylePanel', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('prefills the form from a template', async () => {
    stubApi(...base)
    renderRoutes(<StylePanel project={project()} />)
    await userEvent.click(await screen.findByRole('button', { name: /Support agent/ }))
    expect(screen.getByLabelText('Style description')).toHaveValue(TEMPLATES[0]!.defaults.description)
    expect(screen.getByLabelText('Tone')).toHaveValue('friendly')
    expect(screen.getByLabelText('Format')).toHaveValue('bullets')
    expect(screen.getByLabelText('Example 2 question')).toHaveValue('Where is X?')
    expect(screen.getByRole('button', { name: /Support agent/ })).toHaveAttribute('aria-pressed', 'true')
  })

  it('adds and removes examples within 1 to 5', async () => {
    stubApi(...base)
    renderRoutes(<StylePanel project={project()} />)
    const add = await screen.findByRole('button', { name: 'Add example' })
    expect(screen.getByRole('button', { name: 'Remove example 1' })).toBeDisabled()
    for (let i = 0; i < 4; i++) await userEvent.click(add)
    expect(screen.getByLabelText('Example 5 question')).toBeInTheDocument()
    expect(add).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Remove example 5' }))
    expect(screen.queryByLabelText('Example 5 question')).not.toBeInTheDocument()
    expect(add).toBeEnabled()
  })

  it('blocks saving without an example and says why', async () => {
    const calls = stubApi(...base)
    renderRoutes(<StylePanel project={project()} />)
    await userEvent.type(await screen.findByLabelText('Style description'), 'A friendly support agent who is brief.')
    await userEvent.click(screen.getByRole('button', { name: 'Save & generate preview' }))
    expect(await screen.findByText('Add at least one example.')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'PUT')).toBe(false)
  })

  it('shows 422 field errors from the server', async () => {
    stubApi(
      (url, req) =>
        url.pathname.endsWith('/style') && req.method === 'PUT'
          ? jsonResponse({ error: 'validation_error', message: 'Invalid', details: { fields: { description: ['Too vague, name the audience.'] } } }, 422)
          : undefined,
      ...base,
    )
    renderRoutes(<StylePanel project={project()} />)
    await screen.findByLabelText('Style description')
    await fillMinimal()
    await userEvent.click(screen.getByRole('button', { name: 'Save & generate preview' }))
    expect(await screen.findByText('Too vague, name the audience.')).toBeInTheDocument()
    expect(screen.getByText('Please fix the highlighted fields.')).toBeInTheDocument()
  })

  it('saves the style (PUT) and then starts the preview (POST)', async () => {
    const calls = stubApi(
      (url, req) => (url.pathname.endsWith('/style') && req.method === 'PUT' ? jsonResponse(makeStyle({ warnings: [{ code: 'single_example', message: 'Add a second example.' }] })) : undefined),
      (url, req) => (url.pathname.endsWith('/preview') && req.method === 'POST' ? jsonResponse(makeRun({ state: 'queued' })) : undefined),
      ...base,
    )
    renderRoutes(<StylePanel project={project()} />)
    await screen.findByLabelText('Style description')
    await fillMinimal()
    await userEvent.click(screen.getByRole('button', { name: 'Save & generate preview' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.pathname.endsWith('/preview'))).toBe(true))
    const writes = calls.filter((c) => c.method !== 'GET').map((c) => `${c.method} ${c.url.pathname.split('/').pop()}`)
    expect(writes).toEqual(['PUT style', 'POST preview'])
    const put = calls.find((c) => c.method === 'PUT')!
    expect(await put.request.json()).toMatchObject({ description: 'A friendly support agent who is brief.', examples: [{ input: 'How?', output: 'Like this.' }] })
    expect(await screen.findByText('Add a second example.')).toBeInTheDocument()
  })

  it('picks the dataset format, shows a sample of it, and keeps it when a template is applied', async () => {
    const calls = stubApi(
      (url, req) => (url.pathname.endsWith('/style') && req.method === 'PUT' ? jsonResponse(makeStyle({ dataset_format: 'multi_turn' })) : undefined),
      (url, req) => (url.pathname.endsWith('/preview') && req.method === 'POST' ? jsonResponse(makeRun({ state: 'queued' })) : undefined),
      ...base,
    )
    renderRoutes(<StylePanel project={project()} />)
    const formats = await screen.findByRole('group', { name: 'Dataset format' })
    expect(screen.getByRole('radio', { name: /Questions & answers/ })).toBeChecked()
    const conversations = screen.getByRole('radio', { name: /Conversations/ })
    expect(formats).toHaveTextContent('~3× quota')
    await userEvent.click(conversations)
    expect(conversations).toBeChecked()
    expect(screen.getByRole('list', { name: 'Conversation' })).toHaveTextContent('Does it cover water damage?')

    await userEvent.click(screen.getByRole('button', { name: /Support agent/ }))
    expect(conversations).toBeChecked()
    await userEvent.click(screen.getByRole('button', { name: 'Save & generate preview' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    expect(await calls.find((c) => c.method === 'PUT')!.request.json()).toMatchObject({ dataset_format: 'multi_turn', template_key: 'support' })
  })

  it('patches dataset size and provider/model before saving', async () => {
    const calls = stubApi(
      (_url, req) => (req.method === 'PATCH' ? jsonResponse(makeProject({ status: 'awaiting_style', target_pairs: 300 })) : undefined),
      (url, req) => (url.pathname.endsWith('/style') && req.method === 'PUT' ? jsonResponse(makeStyle()) : undefined),
      (url, req) => (url.pathname.endsWith('/preview') && req.method === 'POST' ? jsonResponse(makeRun()) : undefined),
      ...base,
    )
    renderRoutes(<StylePanel project={project()} />)
    await screen.findByLabelText('Style description')
    await fillMinimal()
    await userEvent.click(screen.getByRole('button', { name: 'Advanced' }))
    const size = screen.getByLabelText('Dataset size (pairs)')
    await userEvent.clear(size)
    await userEvent.type(size, '300')
    await userEvent.selectOptions(await screen.findByLabelText('Provider'), 'groq')
    await userEvent.selectOptions(screen.getByLabelText('Model'), 'llama-3.3-70b')
    await userEvent.click(screen.getByRole('button', { name: 'Save & generate preview' }))
    await waitFor(() => expect(calls.some((c) => c.url.pathname.endsWith('/preview'))).toBe(true))
    const patch = calls.find((c) => c.method === 'PATCH')!
    expect(await patch.request.json()).toEqual({ target_pairs: 300, gen_provider: 'groq', gen_model: 'llama-3.3-70b' })
  })

  it('rejects a dataset size outside 50-2000 locally', async () => {
    const calls = stubApi(...base)
    renderRoutes(<StylePanel project={project()} />)
    await screen.findByLabelText('Style description')
    await fillMinimal()
    await userEvent.click(screen.getByRole('button', { name: 'Advanced' }))
    const size = screen.getByLabelText('Dataset size (pairs)')
    await userEvent.clear(size)
    await userEvent.type(size, '10')
    await userEvent.click(screen.getByRole('button', { name: 'Save & generate preview' }))
    expect(await screen.findByText('Choose between 50 and 2000 pairs.')).toBeInTheDocument()
    expect(calls.some((c) => c.method !== 'GET')).toBe(false)
  })

  it('points to Settings and disables the preview when no key is usable', async () => {
    stubApi(
      (url) => (url.pathname === '/keys' ? jsonResponse([makeKey({ status: 'invalid' })]) : undefined),
      ...base,
    )
    renderRoutes(<StylePanel project={project()} />, { routes: [{ path: '/settings', element: <div>settings page</div> }] })
    const link = await screen.findByRole('link', { name: 'Add a key in Settings' })
    expect(link).toHaveAttribute('href', '/settings')
    expect(screen.getByRole('button', { name: 'Save & generate preview' })).toBeDisabled()
  })

  it('shows an inline error when the preview cannot start', async () => {
    stubApi(
      (url, req) => (url.pathname.endsWith('/style') && req.method === 'PUT' ? jsonResponse(makeStyle()) : undefined),
      (url, req) => (url.pathname.endsWith('/preview') && req.method === 'POST' ? jsonResponse({ error: 'key_required', message: 'Connect a key first.' }, 409) : undefined),
      ...base,
    )
    renderRoutes(<StylePanel project={project()} />)
    await screen.findByLabelText('Style description')
    await fillMinimal()
    await userEvent.click(screen.getByRole('button', { name: 'Save & generate preview' }))
    expect(await screen.findByText('Connect a key first.')).toBeInTheDocument()
  })
})
