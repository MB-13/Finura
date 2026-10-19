/** Preview-only fixtures for the Playground and Settings pages (owned by the playground/settings restyle). */
import { useState } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router'

import { PlaygroundPage, type Turn } from '@/features/playground/PlaygroundPage'
import type { components } from '@/lib/api/schema'
import { makeKaggle, makeKey, PROJECT_ID, PROVIDERS } from '@/test/fixtures'

import { installMockApi, json, pending, type Handler } from './mock-api'

type Provider = components['schemas']['ProviderOut']

const status = (over = {}) => ({ available: true, reason: null, state: 'warm', source: 'final', checkpoint_step: null, model: 'Qwen3.5 4B', ...over })
const on = (path: string, body: () => Response | Promise<Response>): Handler => (url, req) => (url.pathname === path && req.method === 'GET' ? body() : undefined)

const statusPath = `/projects/${PROJECT_ID}/playground/status`

/** Scenarios merged into `scenarios` (route-based, rendered through the real router). */
export const playgroundSettingsScenarios: Record<string, { route: string; note?: string; handlers?: Handler[] }> = {
  'playground-warming': { route: `/projects/${PROJECT_ID}/playground`, note: 'Model loading', handlers: [on(statusPath, () => json(status({ state: 'warming' })))] },
  'playground-cold': { route: `/projects/${PROJECT_ID}/playground`, note: 'Model not loaded', handlers: [on(statusPath, () => json(status({ state: 'cold' })))] },
  'playground-loading': { route: `/projects/${PROJECT_ID}/playground`, note: 'Skeleton', handlers: [on(statusPath, pending)] },
  'playground-error': { route: `/projects/${PROJECT_ID}/playground`, note: 'Status failed', handlers: [on(statusPath, () => json({ error: 'boom', message: 'The server took too long to answer.' }, 500))] },
  'playground-unavailable': {
    route: `/projects/${PROJECT_ID}/playground`,
    note: 'Model not trained yet',
    handlers: [on(statusPath, () => json(status({ available: false, reason: 'Your model is still training. The playground opens when it finishes, or when training pauses with a saved checkpoint.', state: 'cold', source: null, model: null })))],
  },
  'settings-loading': { route: '/settings', note: 'Skeletons', handlers: [on('/keys', pending), on('/compute/kaggle', pending)] },
  'settings-kaggle-none': { route: '/settings', note: 'Kaggle not connected', handlers: [on('/compute/kaggle', () => json(null))] },
  'settings-kaggle-invalid': {
    route: '/settings',
    note: 'Kaggle token rejected',
    handlers: [on('/compute/kaggle', () => json(makeKaggle({ status: 'invalid', status_message: 'Kaggle rejected this token. Create a new one in Kaggle, Settings, API.', gpu_hours_used: null, gpu_hours_total: null, quota_refresh_at: null })))],
  },
  'settings-kaggle-noquota': {
    route: '/settings',
    note: 'Kaggle quota used',
    handlers: [on('/compute/kaggle', () => json(makeKaggle({ status: 'no_gpu_quota', status_message: 'No GPU hours left this week.', gpu_hours_used: 30, gpu_hours_total: 30 })))],
  },
  'settings-keys-empty': { route: '/settings', note: 'No keys saved', handlers: [on('/providers', () => json(FULL_PROVIDERS)), on('/keys', () => json([]))] },
  'settings-keys-mixed': {
    route: '/settings',
    note: 'Keys in several states',
    handlers: [
      on('/providers', () => json(FULL_PROVIDERS)),
      on('/keys', () =>
        json([
          makeKey({ provider: 'groq', last4: '9f3a', status: 'quota_exhausted', quota_reset_at: new Date(Date.now() + 3 * 3600_000).toISOString(), priority: 0, default_model: 'llama-3.3-70b' }),
          makeKey({ provider: 'gemini', last4: 'Zq7c', status: 'invalid', priority: 1, terms_acknowledged: true }),
          makeKey({ provider: 'cerebras', last4: 'k2m1', status: 'unverified', priority: 2 }),
        ]),
      ),
    ],
  },
}

const FULL_PROVIDERS: Provider[] = [
  { ...PROVIDERS[0]!, note: 'Fast, generous free tier. Rotates between 3 open models.' },
  { ...PROVIDERS[1]!, note: 'Speeds up generation. Not available in some EU/UK regions.' },
  { provider: 'cerebras', name: 'Cerebras', models: [{ id: 'llama-3.3-70b', license: 'Llama 3.3', rpm: 30, tpd: 1000000 }], requires_terms_ack: false, note: 'Needs a payment method on file. Optional.', key_help_url: 'https://cloud.cerebras.ai' },
]

const turns: Record<string, { turns: Turn[]; compare?: boolean }> = {
  chat: {
    turns: [
      {
        id: 1,
        question: 'How do I reset the device if the light keeps blinking red?',
        tuned: {
          status: 'done',
          content:
            'Hold the **power button** for five seconds until the light blinks white, then release it.\n\nIf the light turns red again:\n\n1. Unplug the charger for 30 seconds.\n2. Plug it back in and wait for the light to turn solid.\n3. Run `reset --soft` from the Settings screen.\n\n```\nSettings > Device > Reset\n```\n\nThis does not delete your files.',
          sources: [
            { chunk_id: 'c1', section_path: 'Troubleshooting > Reset', excerpt: 'To reset the device, hold the power button for five seconds until the indicator blinks white.' },
            { chunk_id: 'c2', section_path: 'Warranty > Hardware faults', excerpt: 'A persistent red light after two resets indicates a hardware fault covered for 24 months.' },
          ],
        },
        base: null,
      },
      { id: 2, question: 'And is that covered by the warranty?', tuned: { status: 'streaming', content: 'Yes. A persistent red light after two resets counts as a hardware defect, which is covered for 24 months from the date of purchase', sources: [] }, base: null },
    ],
  },
  compare: {
    compare: true,
    turns: [
      {
        id: 1,
        question: 'What does the warranty cover?',
        tuned: {
          status: 'done',
          content: 'Hardware defects for **24 months** from purchase. Accidental damage is not covered.',
          sources: [{ chunk_id: 'c1', section_path: 'Warranty > Coverage', excerpt: 'We cover hardware defects for 24 months from the date of purchase. Accidental damage is excluded.' }],
        },
        base: { status: 'done', content: 'Warranties usually cover manufacturing defects for a limited period, often one year. Check your retailer for the exact terms.', sources: [] },
      },
      { id: 2, question: 'Can I export to CSV?', tuned: { status: 'done', content: 'Yes. Open Settings, choose Export and pick CSV.', sources: [] }, base: { status: 'error', content: '', sources: [], error: 'The model was not loaded yet. Send your message again once it says Ready.' } },
    ],
  },
}

/** `?view=playground-demo&variant=chat|compare|empty`: the playground with a canned conversation. */
export function PlaygroundDemo({ variant }: { variant: string }) {
  useState(() => installMockApi([on(statusPath, () => json(status()))]))
  const v = turns[variant]
  const router = createMemoryRouter(
    [{ path: '*', element: <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-8"><PlaygroundPage projectId={PROJECT_ID} initialTurns={v?.turns} initialCompare={v?.compare} /></div> }],
    { initialEntries: ['/'] },
  )
  return <RouterProvider router={router} />
}
