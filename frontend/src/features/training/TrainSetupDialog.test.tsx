import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { TrainSetupDialog } from '@/features/training/TrainSetupDialog'
import { clearAllTokens, useRevealedToken } from '@/features/training/token-store'
import { jsonResponse, stubApi, type Handler } from '@/test/api'
import { CATALOG, JOB_ID, makeJob, makeKaggle, PRESETS, PROJECT_ID } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const SECRET = 'dtj_secret_value_123'

const lookups: Handler = (url, req) => {
  if (url.pathname === '/models/catalog') return jsonResponse(CATALOG)
  if (url.pathname === '/training/presets') return jsonResponse(PRESETS)
  if (url.pathname === '/models/check' && req.method === 'POST') return undefined
  return undefined
}

function check(body: Record<string, unknown>): Handler {
  return (url, req) =>
    url.pathname === '/models/check' && req.method === 'POST'
      ? jsonResponse({
          hf_id: 'acme/model',
          ok: true,
          architecture: 'llama',
          params_b: 3,
          license: 'mit',
          license_ok: true,
          gated: false,
          is_llama: false,
          train_mode: 'lora16',
          fits_t4: 'yes',
          warnings: [],
          blocking: [],
          ...body,
        })
      : undefined
}

function Probe() {
  const revealed = useRevealedToken(JOB_ID)
  return <div data-testid="probe">{revealed?.token ?? 'no token'}</div>
}

function setup(...handlers: Handler[]) {
  const calls = stubApi(...handlers, lookups)
  const onOpenChange = vi.fn()
  const utils = renderRoutes(
    <>
      <TrainSetupDialog projectId={PROJECT_ID} open onOpenChange={onOpenChange} />
      <Probe />
    </>,
  )
  return { calls, onOpenChange, ...utils }
}

const submit = () => screen.getByRole('button', { name: 'Create training job' })

describe('TrainSetupDialog', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    clearAllTokens()
  })

  it('shows catalog model cards with size, license, T4 badge, mode and per-preset minutes', async () => {
    const { calls } = setup()
    const qwen = await screen.findByRole('radio', { name: 'Qwen3.5 4B' })
    expect(calls.some((c) => c.url.pathname === '/models/catalog' && c.url.searchParams.get('project_id') === PROJECT_ID)).toBe(true)
    expect(qwen).toBeChecked() // recommended is the default
    const card = qwen.closest('label')!
    expect(within(card).getByText('Recommended')).toBeInTheDocument()
    expect(within(card).getByText('Fits free T4')).toBeInTheDocument()
    expect(within(card).getByText(/4 B parameters · Apache 2.0 · Standard \(16-bit\)/)).toBeInTheDocument()
    expect(within(card).getByText('Best quality on a free T4.')).toBeInTheDocument()
    expect(within(card).getByText(/Quick ~20 min · Balanced ~45 min · Thorough ~90 min/)).toBeInTheDocument()
    const big = screen.getByRole('radio', { name: 'Qwen3 8B' }).closest('label')!
    expect(within(big).getByText(/Memory-saving \(4-bit\)/)).toBeInTheDocument()
    expect(within(big).queryByText('Fits free T4')).not.toBeInTheDocument()
  })

  it('says which models open in the playground and warns before training one that does not', async () => {
    setup()
    const qwen = await screen.findByRole('radio', { name: 'Qwen3.5 4B' })
    expect(within(qwen.closest('label')!).getByText('Chat here')).toBeInTheDocument()
    const big = screen.getByRole('radio', { name: 'Qwen3 8B' })
    expect(within(big.closest('label')!).getByText('No chat here')).toBeInTheDocument()
    expect(screen.queryByText(/won't open in the playground/)).not.toBeInTheDocument()

    await userEvent.click(big)
    expect(screen.getByText(/Qwen3 8B won't open in the playground/)).toHaveTextContent('Use Qwen3.5 4B if you want to chat here.')
    expect(submit()).toBeEnabled()
  })

  it('model source tabs are real tabs: arrow keys move between them and each controls a panel', async () => {
    setup()
    const catalogTab = await screen.findByRole('tab', { name: 'Recommended models' })
    expect(catalogTab).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel', { name: 'Recommended models' })).toBeInTheDocument()
    catalogTab.focus()
    await userEvent.keyboard('{ArrowRight}')
    const customTab = screen.getByRole('tab', { name: 'Custom model' })
    expect(customTab).toHaveAttribute('aria-selected', 'true')
    expect(customTab).toHaveFocus()
    expect(screen.getByRole('tabpanel', { name: 'Custom model' })).toBeInTheDocument()
  })

  it('shows an error state when the catalog fails', async () => {
    stubApi((url) => (url.pathname === '/models/catalog' ? jsonResponse({ error: 'boom', message: 'Catalog down' }, 500) : undefined), lookups)
    renderRoutes(<TrainSetupDialog projectId={PROJECT_ID} open onOpenChange={() => {}} />)
    expect(await screen.findByText('Catalog down')).toBeInTheDocument()
  })

  it('blocks a custom model with a blocking reason in plain language', async () => {
    setup(check({ ok: false, blocking: ['too_large'], params_b: 70 }))
    await userEvent.click(await screen.findByRole('tab', { name: 'Custom model' }))
    await userEvent.type(screen.getByLabelText('Hugging Face model id'), 'acme/model')
    await userEvent.click(screen.getByRole('button', { name: 'Check model' }))
    expect(await screen.findByText(/too big for a free Colab GPU/)).toBeInTheDocument()
    expect(submit()).toBeDisabled()
  })

  it('shows warnings, the gated notice and Built with Llama', async () => {
    setup(check({ gated: true, is_llama: true, warnings: ['gated_requires_token', 'may_not_fit'], fits_t4: 'maybe' }))
    await userEvent.click(await screen.findByRole('tab', { name: 'Custom model' }))
    await userEvent.type(screen.getByLabelText('Hugging Face model id'), 'acme/model')
    await userEvent.click(screen.getByRole('button', { name: 'Check model' }))
    expect(await screen.findByText(/you'll need your own Hugging Face token in the notebook/)).toBeInTheDocument()
    expect(screen.getByText(/may not fit on the free T4/)).toBeInTheDocument()
    expect(screen.getByText('Built with Llama')).toBeInTheDocument()
    expect(submit()).toBeEnabled()
  })

  it('requires the license acknowledgement when the license is not ok, and sends it', async () => {
    const { calls } = setup(
      check({ license: 'custom', license_ok: false, warnings: ['license_review'] }),
      (url, req) =>
        url.pathname === `/projects/${PROJECT_ID}/training` && req.method === 'POST'
          ? jsonResponse({ job: makeJob(), token: SECRET, notebook_url: 'https://colab.example/nb' }, 201)
          : undefined,
    )
    await userEvent.click(await screen.findByRole('tab', { name: 'Custom model' }))
    await userEvent.type(screen.getByLabelText('Hugging Face model id'), 'acme/model')
    await userEvent.click(screen.getByRole('button', { name: 'Check model' }))
    const ack = await screen.findByRole('checkbox')
    expect(submit()).toBeDisabled()
    await userEvent.click(ack)
    expect(submit()).toBeEnabled()
    await userEvent.click(submit())
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.pathname.endsWith('/training'))).toBe(true))
    const post = calls.find((c) => c.url.pathname.endsWith('/training') && c.method === 'POST')!
    expect(await post.request.json()).toMatchObject({ base_model_id: 'acme/model', backend: 'colab', preset: 'balanced', license_ack: true })
  })

  it('resets the check result when the model id is edited', async () => {
    setup(check({ ok: false, blocking: ['not_found'] }))
    await userEvent.click(await screen.findByRole('tab', { name: 'Custom model' }))
    const input = screen.getByLabelText('Hugging Face model id')
    await userEvent.type(input, 'acme/model')
    await userEvent.click(screen.getByRole('button', { name: 'Check model' }))
    expect(await screen.findByText(/couldn't find that model/)).toBeInTheDocument()
    await userEvent.type(input, '2')
    expect(screen.queryByText(/couldn't find that model/)).not.toBeInTheDocument()
  })

  it('creates the job with preset and advanced values, shows the token once, and keeps it out of the query cache', async () => {
    const { calls, onOpenChange, queryClient } = setup((url, req) =>
      url.pathname === `/projects/${PROJECT_ID}/training` && req.method === 'POST'
        ? jsonResponse({ job: makeJob(), token: SECRET, notebook_url: 'https://colab.example/nb' }, 201)
        : undefined,
    )
    await screen.findByRole('radio', { name: 'Qwen3.5 4B' })
    await userEvent.click(await screen.findByRole('radio', { name: 'Thorough' }))
    await userEvent.click(screen.getByText('Advanced'))
    await userEvent.type(screen.getByLabelText('Epochs'), '3')
    await userEvent.selectOptions(screen.getByLabelText('LoRA rank'), '32')
    expect(screen.getByLabelText('Learning rate')).toBeInTheDocument()
    await userEvent.click(submit())

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    const post = calls.find((c) => c.url.pathname.endsWith('/training') && c.method === 'POST')!
    expect(await post.request.json()).toEqual({
      base_model_id: 'unsloth/Qwen3.5-4B',
      backend: 'colab',
      preset: 'thorough',
      advanced: { epochs: 3, lora_r: 32 },
      license_ack: false,
    })
    // the token is held in memory for the reveal and nowhere else
    expect(screen.getByTestId('probe')).toHaveTextContent(SECRET)
    expect(JSON.stringify(queryClient.getQueryCache().getAll().map((q) => q.state.data))).not.toContain(SECRET)
    expect(JSON.stringify(queryClient.getMutationCache().getAll().map((m) => m.state.data))).not.toContain(SECRET)
    expect(JSON.stringify({ ...localStorage })).not.toContain(SECRET)
    expect(JSON.stringify({ ...sessionStorage })).not.toContain(SECRET)
  })

  it('shows the server message when creating fails', async () => {
    setup((url, req) =>
      url.pathname.endsWith('/training') && req.method === 'POST'
        ? jsonResponse({ error: 'dataset_not_approved', message: 'nope' }, 409)
        : undefined,
    )
    await screen.findByRole('radio', { name: 'Qwen3.5 4B' })
    await userEvent.click(submit())
    expect(await screen.findByRole('alert')).toHaveTextContent('Approve your dataset first.')
  })

  describe('where to train', () => {
    const kaggleGet = (account: ReturnType<typeof makeKaggle> | null): Handler => (url, req) =>
      url.pathname === '/compute/kaggle' && req.method === 'GET' ? jsonResponse(account) : undefined
    const createOk: Handler = (url, req) =>
      url.pathname === `/projects/${PROJECT_ID}/training` && req.method === 'POST'
        ? jsonResponse({ job: makeJob({ backend: 'kaggle' }), token: null, notebook_url: null }, 201)
        : undefined
    const createFails = (error: string): Handler => (url, req) =>
      url.pathname === `/projects/${PROJECT_ID}/training` && req.method === 'POST' ? jsonResponse({ error, message: 'server text' }, 409) : undefined

    it('defaults to Kaggle when connected, shows GPU hours left and sends backend kaggle', async () => {
      const { calls } = setup(kaggleGet(makeKaggle()), createOk)
      const kaggle = await screen.findByRole('radio', { name: /Automatically on Kaggle \(recommended\)/ })
      await waitFor(() => expect(kaggle).toBeEnabled())
      expect(kaggle).toBeChecked()
      expect(screen.getByText(/25.5 GPU hours left this week/)).toBeInTheDocument()
      await screen.findByRole('radio', { name: 'Qwen3.5 4B' })
      await userEvent.click(submit())
      await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.pathname.endsWith('/training'))).toBe(true))
      const post = calls.find((c) => c.method === 'POST' && c.url.pathname.endsWith('/training'))!
      expect(await post.request.json()).toMatchObject({ backend: 'kaggle' })
    })

    it('lets the user pick Colab instead', async () => {
      const { calls } = setup(kaggleGet(makeKaggle()), createOk)
      const colab = await screen.findByRole('radio', { name: /Manually in Google Colab/ })
      await waitFor(() => expect(screen.getByRole('radio', { name: /Automatically on Kaggle/ })).toBeChecked())
      await userEvent.click(colab)
      await screen.findByRole('radio', { name: 'Qwen3.5 4B' })
      await userEvent.click(submit())
      await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.pathname.endsWith('/training'))).toBe(true))
      const post = calls.find((c) => c.method === 'POST' && c.url.pathname.endsWith('/training'))!
      expect(await post.request.json()).toMatchObject({ backend: 'colab' })
    })

    it('disables Kaggle with a Settings link when not connected, and selects Colab', async () => {
      setup(kaggleGet(null))
      const link = await screen.findByRole('link', { name: 'Connect Kaggle to train automatically' })
      expect(link).toHaveAttribute('href', '/settings')
      expect(screen.getByRole('radio', { name: /Automatically on Kaggle/ })).toBeDisabled()
      expect(screen.getByRole('radio', { name: /Manually in Google Colab/ })).toBeChecked()
    })

    it.each([
      ['invalid', /token is not valid/],
      ['no_gpu_quota', /No Kaggle GPU hours left/],
      ['unchecked', /Still checking/],
    ] as const)('disables Kaggle when the account status is %s', async (status, text) => {
      setup(kaggleGet(makeKaggle({ status })))
      expect(await screen.findByText(text)).toBeInTheDocument()
      expect(screen.getByRole('radio', { name: /Automatically on Kaggle/ })).toBeDisabled()
      expect(screen.getByRole('radio', { name: /Manually in Google Colab/ })).toBeChecked()
    })

    it('explains kaggle_not_connected', async () => {
      setup(kaggleGet(makeKaggle()), createFails('kaggle_not_connected'))
      await screen.findByRole('radio', { name: 'Qwen3.5 4B' })
      await waitFor(() => expect(screen.getByRole('radio', { name: /Automatically on Kaggle/ })).toBeEnabled())
      await userEvent.click(submit())
      expect(await screen.findByRole('alert')).toHaveTextContent('Kaggle is not connected. Connect it in Settings, or choose Google Colab.')
    })

    it('explains kaggle_gated_model', async () => {
      setup(kaggleGet(makeKaggle()), createFails('kaggle_gated_model'))
      await screen.findByRole('radio', { name: 'Qwen3.5 4B' })
      await waitFor(() => expect(screen.getByRole('radio', { name: /Automatically on Kaggle/ })).toBeEnabled())
      await userEvent.click(submit())
      expect(await screen.findByRole('alert')).toHaveTextContent('This model needs a Hugging Face token. Use Google Colab for it instead.')
    })
  })
})
