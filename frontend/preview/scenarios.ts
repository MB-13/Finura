/**
 * Preview scenarios: a route plus API stubs. Add yours at the bottom of `scenarios`.
 * Open with  http://localhost:5174/?scenario=<name>[&theme=dark]   (see README.md)
 */
import type { components } from '@/lib/api/schema'
import {
  CATALOG,
  JOB_ID,
  PRESETS,
  PROJECT_ID,
  PROVIDERS,
  makeDocument,
  makeEvaluation,
  makeJob,
  makeKaggle,
  makeKey,
  makePair,
  makeProject,
  makeRun,
  makeStyle,
  DATASET_FORMATS,
  type ProjectOut,
} from '@/test/fixtures'

import { json, pending, type Handler } from './mock-api'
import { playgroundSettingsScenarios } from './playground-settings'

type ProjectStatus = ProjectOut['status']
const now = Date.now()
const ago = (minutes: number) => new Date(now - minutes * 60_000).toISOString()
const ahead = (minutes: number) => new Date(now + minutes * 60_000).toISOString()

export type Scenario = {
  /** Initial in-app route. */
  route: string
  /** Handlers tried before the defaults (so you can override any endpoint). */
  handlers?: Handler[]
  /** One line shown in the scenario index. */
  note?: string
}

/* ------------------------------------------------------------------ fixtures */

export const NAMES = ['Customer support bot', 'Legal contracts assistant', 'Product handbook Q&A', 'HR policy helper']

export function summary(name: string, status: ProjectStatus, i: number): components['schemas']['ProjectSummary'] {
  return {
    id: `00000000-0000-4000-8000-00000000000${i}`,
    name,
    status,
    status_message: status === 'failed' ? 'We could not read one of your PDFs.' : null,
    base_model_id: i % 2 ? 'unsloth/Qwen3.5-4B' : null,
    created_at: ago(60 * 24 * (i + 1)),
    updated_at: ago(30 * (i + 1)),
  }
}

// A realistic long, markdown-heavy base answer next to a short tuned one (results page layout check).
const previewEvaluation = () =>
  makeEvaluation({
    samples: [
      {
        question: "What happens to my CO if I don't use it within three months?",
        reference: "If you don't use the CO within 3 months, it lapses and is no longer available. Anything else I can help with?",
        base_answer:
          'If you do not use your **Certificate of Insurance (COI)** within three months, the consequence depends on **who issued it** and **what it covers**.\n\nHere is a breakdown of the most common scenarios:\n\n### 1. General Liability or Commercial Auto\nIn most standard cases, a COI **does not expire** simply because it has not been used.\n\n* **Validity:** A COI is a snapshot of your current coverage.\n* **The "three-month" confusion:** some clients request a COI for a **three-month period**.\n* **Result:** you likely will not lose your insurance.\n\n### 2. Contract-specific certificates\nIf your contract states the COI is only valid for three months, the **contractual requirement** may be considered unmet even though the policy is still active.\n\n### 3. What to do next\n1. Check the issue date.\n2. Ask your broker for a refreshed certificate.\n3. Keep a copy with the contract.',
        tuned_answer: 'It expires. Anything else I can help with?',
        base_score: 2,
        tuned_score: 9,
        gain: 7,
      },
      {
        question: "Do we need to get vaccinated as soon as it's available?",
        reference: 'Vaccination is recommended but not mandatory. Anything else I can help with?',
        base_answer: 'It depends on local guidance. Many employers **recommend** it, but rules vary.',
        tuned_answer: "It's recommended, not mandatory. Anything else I can help with?",
        base_score: 3,
        tuned_score: 10,
        gain: 7,
      },
    ],
  })

export const LIST_STATUSES: ProjectStatus[] = ['training', 'in_review', 'ready', 'paused', 'awaiting_style', 'failed']

const style = makeStyle({
  template_key: 'support',
  description: 'A friendly support agent who answers briefly and always points to the right manual section.',
  examples: [
    { input: 'How do I reset the device?', output: 'Hold the power button for five seconds until the light blinks.' },
    { input: 'Does it work offline?', output: 'Yes. Syncing resumes automatically when you are back online.' },
  ],
})
const runDone = makeRun({ state: 'done', total_chunks: 12, done_chunks: 12, pairs_generated: 8, pairs_kept: 8 })
const jobBase = makeJob({ started_at: ago(52), last_heartbeat_at: ago(0.2), current_step: 340, max_steps: 800, last_loss: 0.84 })

/** One project per status, with the nested objects each panel expects. Override via `projectFor(status, {...})`. */
export function projectFor(status: ProjectStatus, overrides: Partial<ProjectOut> = {}): ProjectOut {
  const base = makeProject({
    id: PROJECT_ID,
    name: 'Customer support bot',
    status,
    status_changed_at: ago(12),
    counts: { documents: 3, chunks: 128, pairs_kept: 0, pairs_train: 0, pairs_eval: 0 },
    total_bytes: 6_400_000,
    allowed_actions: ['rename', 'delete'],
  })
  const withStyle = { style, latest_preview: runDone, gen_provider: 'groq', gen_model: 'llama-3.3-70b' }
  const withDataset = {
    ...withStyle,
    base_model_id: 'unsloth/Qwen3.5-4B',
    base_model_license: 'Apache 2.0',
    counts: { documents: 3, chunks: 128, pairs_kept: 940, pairs_train: 846, pairs_eval: 94 },
    dataset_version: { id: 'dv1', version: 1, train_count: 846, eval_count: 94, sha256_train: 'ab', sha256_eval: 'cd', dataset_format: 'qa_chat' as const, approved_at: ago(70) },
  }
  const byStatus: Partial<Record<ProjectStatus, Partial<ProjectOut>>> = {
    draft: { counts: { documents: 0, chunks: 0, pairs_kept: 0, pairs_train: 0, pairs_eval: 0 }, total_bytes: 0 },
    uploaded: { allowed_actions: ['rename', 'delete', 'process'] },
    parsing: {},
    awaiting_style: { allowed_actions: ['rename', 'delete', 'preview'], latest_preview: null },
    previewing: { style, latest_preview: makeRun({ state: 'running', done_chunks: 2, total_chunks: 4, pairs_generated: 3 }), active_run: makeRun({ state: 'running', done_chunks: 2, total_chunks: 4, pairs_generated: 3 }) },
    generating: { ...withStyle, active_run: makeRun({ kind: 'full', state: 'running', total_chunks: 128, done_chunks: 47, pairs_generated: 312, pairs_kept: 290, tokens_in: 180_000, tokens_out: 60_000 }), allowed_actions: ['rename', 'cancel_generation'] },
    in_review: { ...withDataset, allowed_actions: ['rename', 'delete', 'approve', 'restyle', 'export'] },
    awaiting_run: { ...withDataset, active_job: makeJob({ state: 'created', current_step: 0, last_loss: null, started_at: null, last_heartbeat_at: null }), allowed_actions: ['rename', 'cancel_training'] },
    training: { ...withDataset, active_job: jobBase, allowed_actions: ['rename', 'cancel_training'] },
    paused: { ...withDataset, status_reason: 'idle_timeout', active_job: makeJob({ state: 'paused', pause_reason: 'idle_timeout', current_step: 340, max_steps: 800, last_loss: 0.84, checkpoint_step: 300, checkpoint_uploaded_at: ago(14), last_heartbeat_at: ago(20) }), allowed_actions: ['rename', 'cancel_training'] },
    evaluating: { ...withDataset, active_job: makeJob({ state: 'evaluating', current_step: 800, max_steps: 800, last_loss: 0.61 }) },
    ready: { ...withDataset, active_job: makeJob({ state: 'completed', current_step: 800, max_steps: 800, last_loss: 0.61, completed_at: ago(5), exports: { adapter: true, gguf: true, drive_path: '/content/drive/MyDrive/doctune/support-answers-2026-10-09/qwen3_5-4b-lora-merged-q4_k_m', hf_repo: 'engineering-department-of-acme/doctune-support-answers-qwen3-5-4b' } as never }), evaluation: previewEvaluation(), allowed_actions: ['rename', 'delete', 'playground'] },
    failed: { ...withStyle, status_message: 'We could not read one of your PDFs (scan.pdf looks password-protected).', allowed_actions: ['rename', 'delete', 'retry'] },
  }
  return { ...base, ...byStatus[status], ...overrides } as ProjectOut
}

const pairs = Array.from({ length: 40 }, (_, i) =>
  makePair({
    id: `p${i}`,
    question: ['How do I reset the device?', 'What does the warranty cover?', 'Can I export my data as CSV?', 'Why is my sync paused?'][i % 4]!,
    answer: ['Hold the power button for five seconds until the light blinks, then release.', 'Hardware defects for 24 months from purchase. Accidental damage is not covered.', 'Yes. Open Settings, choose Export and pick CSV. Large exports are emailed.', 'Sync pauses when you are offline or on battery saver. It resumes automatically.'][i % 4]!,
    split: i % 10 === 0 ? 'eval' : 'train',
    judge_correctness: 3 + (i % 3),
    judge_style: 3 + ((i + 1) % 3),
    kept: i % 9 !== 0,
    dropped_reason: i % 9 === 0 ? 'low_score' : null,
    edited: i % 7 === 0,
  }),
)

const conversations = Array.from({ length: 12 }, (_, i) => {
  const turns = [
    ['How do I reset the device?', 'Hold the power button for five seconds until the light blinks, then release.'],
    ['Will that delete my settings?', 'No. A reset restarts the device; your settings and data stay as they are.'],
    ['And if it still freezes?', 'Do a factory reset from Settings > System. That one does erase your data, so export it first.'],
  ].slice(0, 2 + (i % 2))
  const messages = turns.flatMap(([q, a]) => [
    { role: 'user' as const, content: q! },
    { role: 'assistant' as const, content: a! },
  ])
  return makePair({
    id: `c${i}`,
    dataset_format: 'multi_turn',
    question: messages[0]!.content,
    answer: messages[messages.length - 1]!.content,
    record: { format: 'multi_turn', messages },
    split: i % 10 === 0 ? 'eval' : 'train',
    judge_correctness: 4 + (i % 2),
    judge_style: 5,
  })
})

const metrics = Array.from({ length: 34 }, (_, i) => ({
  step: (i + 1) * 10,
  loss: 2.4 * Math.exp(-i / 11) + 0.55 + Math.sin(i) * 0.04,
  lr: 0.0002,
  at: ago(52 - i),
}))

/* ------------------------------------------------------------------ default API */

export function defaultHandlers(project: () => ProjectOut): Handler[] {
  const get = (path: string | RegExp, body: unknown | (() => unknown), method = 'GET'): Handler => (url, req) => {
    const hit = typeof path === 'string' ? url.pathname === path : path.test(url.pathname)
    return hit && req.method === method ? json(typeof body === 'function' ? (body as () => unknown)() : body) : undefined
  }
  const docs = [
    makeDocument({ id: 'd1', filename: 'user-manual.pdf', size_bytes: 3_200_000, status: 'parsed', page_count: 48, chunk_count: 74 }),
    makeDocument({ id: 'd2', filename: 'warranty-terms.pdf', size_bytes: 1_100_000, status: 'parsed', page_count: 12, chunk_count: 21 }),
    makeDocument({ id: 'd3', filename: 'faq.md', size_bytes: 42_000, status: 'parsed', page_count: null, chunk_count: 33 }),
  ]
  return [
    get('/meta', { version: '1', notebook_url: 'https://colab.research.google.com/github/x/y', notebook_version: '1', limits: { file_mb: 20, project_mb: 50, max_pairs: 2000 }, providers: ['groq', 'gemini'] }),
    get('/me', { id: 'u1', email: 'alice@example.com', display_name: 'Alice', onboarding_done: true, email_notifications: true }),
    get('/projects', () => ({ items: LIST_STATUSES.map((s, i) => summary(NAMES[i % NAMES.length]!, s, i + 1)), next_cursor: null })),
    get(`/projects/${PROJECT_ID}`, () => project()),
    get(`/projects/${PROJECT_ID}/documents`, docs),
    get(`/projects/${PROJECT_ID}/chunks`, { items: [], next_cursor: null }),
    get(`/projects/${PROJECT_ID}/estimate`, { chunks: 128, pairs_per_chunk: 8, supported_pairs: 1024, target_pairs: 1000, est_requests: 130, est_tokens: 420_000, est_minutes: 55, est_days: 0, providers: ['groq'], fits_daily_quota: true }),
    get(`/projects/${PROJECT_ID}/dataset/stats`, { kept: 940, train: 846, eval: 94, dropped_by_reason: { low_score: 41, duplicate: 12 }, avg_correctness: 4.3, avg_style: 4.1, answer_words: {}, min_pairs: 50, small_min_pairs: 20, max_pairs: 2000, min_eval: 5, resume: null, more: null }),
    get(/\/projects\/[^/]+\/pairs$/, { items: pairs, next_cursor: null }),
    get(/\/runs\/[^/]+\/pairs$/, pairs.slice(0, 4)),
    get(`/projects/${PROJECT_ID}/evaluation`, previewEvaluation()),
    get(`/projects/${PROJECT_ID}/training/${JOB_ID}/metrics`, metrics),
    get(`/projects/${PROJECT_ID}/playground/status`, { available: true, state: 'warm', source: 'final', model: 'Qwen3.5 4B' }),
    get(`/projects/${PROJECT_ID}/artifacts`, [
      { id: 'a1', kind: 'adapter_safetensors', size_bytes: 84_000_000, meta: null, expires_at: ahead(60 * 24 * 13) },
      { id: 'a2', kind: 'adapter_gguf', size_bytes: 61_000_000, meta: null, expires_at: ahead(60 * 24 * 13) },
    ]),
    get('/providers', PROVIDERS),
    get('/keys', [makeKey({ provider: 'groq', last4: '9f3a' })]),
    get('/style-templates', [
      { key: 'support', name: 'Support agent', description: 'Helpful, concise answers for customers.', defaults: {} },
      { key: 'tutor', name: 'Friendly tutor', description: 'Explains step by step in simple words.', defaults: {} },
      { key: 'legal', name: 'Formal advisor', description: 'Precise and cautious wording.', defaults: {} },
    ]),
    get('/dataset-formats', DATASET_FORMATS),
    get('/models/catalog', CATALOG),
    get('/training/presets', PRESETS),
    get('/compute/kaggle', makeKaggle()),
  ]
}

/* ------------------------------------------------------------------ scenarios */

const workspace = (status: ProjectStatus, overrides: Partial<ProjectOut> = {}): Scenario => ({
  route: `/projects/${PROJECT_ID}`,
  note: `Project workspace, status = ${status}`,
  handlers: [(url, req) => (url.pathname === `/projects/${PROJECT_ID}` && req.method === 'GET' ? json(projectFor(status, overrides)) : undefined)],
})

const ALL_STATUSES: ProjectStatus[] = ['draft', 'uploaded', 'parsing', 'awaiting_style', 'previewing', 'generating', 'in_review', 'awaiting_run', 'training', 'paused', 'evaluating', 'ready', 'failed']

export const scenarios: Record<string, Scenario> = {
  projects: { route: '/projects', note: 'Projects list with several statuses' },
  'projects-empty': { route: '/projects', note: 'No projects', handlers: [(u) => (u.pathname === '/projects' ? json({ items: [], next_cursor: null }) : undefined)] },
  'projects-loading': { route: '/projects', note: 'Skeleton state', handlers: [(u) => (u.pathname === '/projects' ? pending() : undefined)] },
  'projects-error': { route: '/projects', note: 'Error state', handlers: [(u) => (u.pathname === '/projects' ? json({ error: 'boom', message: 'The server took too long to answer.' }, 500) : undefined)] },
  ...Object.fromEntries(ALL_STATUSES.map((s) => [`workspace-${s}`, workspace(s)])),
  'workspace-loading': { route: `/projects/${PROJECT_ID}`, note: 'Skeleton state', handlers: [(u) => (u.pathname === `/projects/${PROJECT_ID}` ? pending() : undefined)] },
  'workspace-not-found': { route: `/projects/${PROJECT_ID}`, note: '404', handlers: [(u) => (u.pathname === `/projects/${PROJECT_ID}` ? json({ error: 'not_found', message: 'Project not found' }, 404) : undefined)] },
  'workspace-upload': workspace('draft', { allowed_actions: ['rename', 'delete', 'upload', 'process', 'remove_document'], counts: { documents: 3, chunks: 0, pairs_kept: 0, pairs_train: 0, pairs_eval: 0 } }),
  'workspace-style-preview': workspace('awaiting_style', { style, latest_preview: runDone, allowed_actions: ['rename', 'delete', 'preview'] }),
  'workspace-generating-waiting': workspace('generating', { active_run: makeRun({ kind: 'full', state: 'waiting_quota', total_chunks: 128, done_chunks: 47, pairs_generated: 312, resume_at: ahead(60 * 7) }), allowed_actions: ['rename', 'cancel_generation', 'finish_generation'] }),
  'workspace-awaiting_run-kaggle-queued': workspace('awaiting_run', { active_job: makeJob({ state: 'created', backend: 'kaggle', external_url: 'https://www.kaggle.com/code/alice/doctune-job', current_step: 0, last_loss: null, started_at: null, last_heartbeat_at: null, est_minutes: 55, runtime_info: { kaggle_status: 'QUEUED' } }) }),
  'workspace-awaiting_run-kaggle-running': workspace('awaiting_run', { active_job: makeJob({ state: 'created', backend: 'kaggle', external_url: 'https://www.kaggle.com/code/alice/doctune-job', current_step: 0, last_loss: null, started_at: null, last_heartbeat_at: null, est_minutes: 55, runtime_info: { kaggle_status: 'RUNNING' } }) }),
  'workspace-training-kaggle': workspace('training', { active_job: makeJob({ backend: 'kaggle', external_url: 'https://www.kaggle.com/code/alice/doctune-job', started_at: ago(52), last_heartbeat_at: ago(0.2), current_step: 340, max_steps: 800, last_loss: 0.84, checkpoint_step: 300, checkpoint_uploaded_at: ago(4) }) }),
  'workspace-paused-kaggle': workspace('paused', { status_reason: 'session_ended', active_job: makeJob({ state: 'paused', backend: 'kaggle', external_url: 'https://www.kaggle.com/code/alice/doctune-job', pause_reason: 'session_ended', current_step: 340, max_steps: 800, last_loss: 0.84, checkpoint_step: 300, checkpoint_uploaded_at: ago(14), last_heartbeat_at: ago(20) }) }),
  'dataset-empty': { route: `/projects/${PROJECT_ID}/dataset`, note: 'Review table with no pairs', handlers: [(u) => (u.pathname === `/projects/${PROJECT_ID}` ? json(projectFor('in_review')) : /\/pairs$/.test(u.pathname) ? json({ items: [], next_cursor: null }) : undefined)] },
  'review-small': {
    route: `/projects/${PROJECT_ID}`,
    note: 'Review, dataset below the approval minimums',
    handlers: [
      (u) => (u.pathname === `/projects/${PROJECT_ID}` ? json({ ...projectFor('in_review'), dataset_version: null }) : undefined),
      (u) => (u.pathname === `/projects/${PROJECT_ID}/dataset/stats` ? json({ kept: 32, train: 29, eval: 3, dropped_by_reason: { judge_low: 14, judge_failed: 10 }, avg_correctness: 5, avg_style: 4.5, answer_words: { '25-75': 14, '<25': 18 }, min_pairs: 50, small_min_pairs: 20, max_pairs: 2000, min_eval: 1, resume: null, more: { target_pairs: 500, sections: 7, pairs_to_generate: 56 } }) : undefined),
    ],
  },
  'dataset-readonly': { route: `/projects/${PROJECT_ID}/dataset`, note: 'Review table, read-only (ready)', handlers: [(u) => (u.pathname === `/projects/${PROJECT_ID}` ? json(projectFor('ready')) : undefined)] },
  'dataset-conversations': {
    route: `/projects/${PROJECT_ID}/dataset`,
    note: 'Review table, conversation dataset',
    handlers: [
      (u) => (u.pathname === `/projects/${PROJECT_ID}` ? json(projectFor('in_review', { style: { ...style, dataset_format: 'multi_turn' } })) : undefined),
      (u) => (/\/pairs$/.test(u.pathname) ? json({ items: conversations, next_cursor: null }) : undefined),
    ],
  },
  'workspace-style-formats': workspace('awaiting_style', { latest_preview: null, allowed_actions: ['rename', 'delete', 'preview'] }),
  dataset: { route: `/projects/${PROJECT_ID}/dataset`, note: 'Full-screen review table', handlers: [(u) => (u.pathname === `/projects/${PROJECT_ID}` ? json(projectFor('in_review')) : undefined)] },
  playground: { route: `/projects/${PROJECT_ID}/playground`, note: 'Chat playground', handlers: [(u) => (u.pathname === `/projects/${PROJECT_ID}` ? json(projectFor('ready')) : undefined)] },
  settings: { route: '/settings', note: 'Settings: API keys + account' },
  ...playgroundSettingsScenarios,
  onboarding: { route: '/onboarding', handlers: [(u) => (u.pathname === '/me' ? json({ id: 'u1', email: 'alice@example.com', display_name: 'Alice', onboarding_done: false, email_notifications: true }) : undefined)] },
  landing: { route: '/', note: 'Marketing landing' },
  'sign-in': { route: '/sign-in' },
  docs: { route: '/docs' },
  privacy: { route: '/privacy' },
  terms: { route: '/terms' },
  'not-found': { route: '/nope' },
}
