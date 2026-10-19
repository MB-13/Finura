import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ResultsPanel } from '@/features/results/ResultsPanel'
import { jsonResponse, stubApi, type Handler } from '@/test/api'
import { makeEvaluation, makeJob, makeProject, PROJECT_ID } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const ARTIFACTS = [
  { id: 'a1', kind: 'adapter_safetensors', size_bytes: 52_428_800, meta: null, expires_at: '2999-01-01T00:00:00Z' },
  { id: 'a2', kind: 'adapter_gguf', size_bytes: 20_971_520, meta: null, expires_at: '2999-01-01T00:00:00Z' },
  { id: 'a3', kind: 'eval_generations', size_bytes: 10, meta: null, expires_at: null },
]
const artifacts: Handler = (url) => (url.pathname === `/projects/${PROJECT_ID}/artifacts` ? jsonResponse(ARTIFACTS) : undefined)
const evaluation = (e: unknown): Handler => (url) => (url.pathname === `/projects/${PROJECT_ID}/evaluation` ? jsonResponse(e) : undefined)
const ready = (over = {}, jobOver = {}) =>
  makeProject({ status: 'ready', active_job: makeJob({ state: 'completed', ...jobOver }), evaluation: makeEvaluation(), ...over })

describe('ResultsPanel', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows base vs tuned bars, samples, ROUGE-L and where the exports went', async () => {
    stubApi(artifacts, evaluation(makeEvaluation()))
    renderRoutes(
      <ResultsPanel
        project={ready({}, { metrics: { rouge_l_base: 0.21, rouge_l_tuned: 0.48 }, exports: { drive_path: '/MyDrive/DocTune/p/gguf', hf_repo: 'me/model' } })}
      />,
    )
    const scores = await screen.findByRole('region', { name: 'Original vs tuned' })
    const meters = within(scores).getAllByRole('meter')
    expect(meters).toHaveLength(6)
    expect(within(scores).getAllByRole('meter', { name: 'Tuned' })[0]).toHaveAttribute('aria-valuenow', '4')
    expect(within(scores).getAllByRole('meter', { name: 'Original' })[2]).toHaveAttribute('aria-valuenow', '2.5')
    expect(within(scores).getByText(/original 0.210 → tuned 0.480/)).toBeInTheDocument()

    const samples = await screen.findByRole('list', { name: 'Sample answers' })
    expect(within(samples).getByText('How do I reset the device?')).toBeInTheDocument()
    expect(within(samples).getByText('Try turning it off and on.')).toBeInTheDocument()
    expect(within(samples).getAllByText('Hold the button for five seconds.').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('/MyDrive/DocTune/p/gguf')).toBeInTheDocument()
    expect(screen.getByText('me/model')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open playground/ })).toHaveAttribute('href', `/projects/${PROJECT_ID}/playground`)
  })

  it('shows Scoring… while the evaluation is pending and no samples', async () => {
    stubApi(artifacts, evaluation(makeEvaluation({ state: 'scoring', base_scores: null, tuned_scores: null, samples: null })))
    renderRoutes(<ResultsPanel project={ready({ evaluation: makeEvaluation({ state: 'pending', base_scores: null, tuned_scores: null, samples: null }) })} />)
    expect(await screen.findByText(/Scoring…/)).toBeInTheDocument()
    expect(screen.queryByRole('meter')).not.toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Sample answers' })).not.toBeInTheDocument()
  })

  it('shows the evaluation error text when scoring failed', async () => {
    stubApi(artifacts, evaluation(makeEvaluation({ state: 'failed', error: 'Judge key invalid', base_scores: null, tuned_scores: null, samples: null })))
    renderRoutes(<ResultsPanel project={ready()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Evaluation failed: Judge key invalid')
  })

  it('lists downloads with sizes and downloads through the signed url', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    const calls = stubApi(
      artifacts,
      evaluation(makeEvaluation()),
      (url) => (url.pathname === `/projects/${PROJECT_ID}/artifacts/a2/download` ? jsonResponse({ url: 'https://r2.example/adapter.gguf', expires_at: 1 }) : undefined),
    )
    renderRoutes(<ResultsPanel project={ready()} />)
    const list = await screen.findByRole('list', { name: 'Downloads' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(2) // eval_generations is not offered
    expect(within(list).getByText(/50\.0 MB/)).toBeInTheDocument()
    expect(within(list).getByText(/20\.0 MB/)).toBeInTheDocument()
    await userEvent.click(within(list).getByRole('button', { name: 'Download Adapter for llama.cpp (GGUF)' }))
    await waitFor(() => expect(open).toHaveBeenCalledWith('https://r2.example/adapter.gguf', '_blank', 'noopener,noreferrer'))
    expect(calls.some((c) => c.url.pathname.endsWith('/artifacts/a2/download'))).toBe(true)
    open.mockRestore()
  })

  it('shows an empty and an error state for downloads', async () => {
    stubApi((url) => (url.pathname.endsWith('/artifacts') ? jsonResponse([]) : undefined), evaluation(makeEvaluation()))
    const { unmount } = renderRoutes(<ResultsPanel project={ready()} />)
    expect(await screen.findByText(/No files to download yet/)).toBeInTheDocument()
    unmount()
    vi.unstubAllGlobals()
    stubApi((url) => (url.pathname.endsWith('/artifacts') ? jsonResponse({ error: 'boom', message: 'Files unavailable' }, 400) : undefined), evaluation(makeEvaluation()))
    renderRoutes(<ResultsPanel project={ready()} />)
    expect(await screen.findByText('Files unavailable')).toBeInTheDocument()
  })

  it('shows the Ollama snippet, license note, Built with Llama and a disabled Train again', async () => {
    stubApi(artifacts, evaluation(makeEvaluation()))
    renderRoutes(<ResultsPanel project={ready({}, { is_llama: true, base_model_id: 'meta/llama-3b', base_model_license: 'Llama 3.2' })} />)
    expect(screen.getByText(/ollama create my-doctune-model -f Modelfile/)).toBeInTheDocument()
    expect(screen.getByText(/ollama run my-doctune-model/)).toBeInTheDocument()
    expect(screen.getByText(/ready-made/)).toBeInTheDocument()
    expect(screen.getByText('Built with Llama.')).toBeInTheDocument()
    expect(screen.getByText(/Llama 3.2/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Train again (coming soon)' })).toBeDisabled()
  })

  it('gives Kaggle runs adapter-based Ollama steps and no Google Drive wording', async () => {
    stubApi(artifacts, evaluation(makeEvaluation()))
    renderRoutes(<ResultsPanel project={ready({}, { backend: 'kaggle', base_model_id: 'unsloth/Qwen3.5-4B' })} />)
    expect(screen.getByText(/ADAPTER \.\/adapter\.gguf/)).toBeInTheDocument()
    expect(screen.getByText(/FROM <a GGUF of unsloth\/Qwen3\.5-4B>/)).toBeInTheDocument()
    expect(screen.queryByText(/Google Drive/)).not.toBeInTheDocument()
    expect(screen.queryByText(/ready-made/)).not.toBeInTheDocument()
  })
})
