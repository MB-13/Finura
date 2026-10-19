import type { components } from '@/lib/api/schema'

export type ProjectOut = components['schemas']['ProjectOut']
export type DocumentWithChunks = components['schemas']['DocumentWithChunks']

export const PROJECT_ID = '11111111-1111-4111-8111-111111111111'

export function makeProject(overrides: Partial<ProjectOut> = {}): ProjectOut {
  return {
    id: PROJECT_ID,
    name: 'My project',
    status: 'draft',
    status_reason: null,
    status_message: null,
    status_changed_at: '2026-01-01T00:00:00Z',
    base_model_id: null,
    base_model_license: null,
    gen_provider: null,
    gen_model: null,
    target_pairs: 1000,
    total_bytes: 0,
    counts: { documents: 0, chunks: 0, pairs_kept: 0, pairs_train: 0, pairs_eval: 0 },
    allowed_actions: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

export function makeDocument(overrides: Partial<DocumentWithChunks> = {}): DocumentWithChunks {
  return {
    id: '22222222-2222-4222-8222-222222222222',
    filename: 'notes.pdf',
    content_type: 'application/pdf',
    size_bytes: 1024,
    status: 'uploaded',
    page_count: null,
    ocr_pages: 0,
    error: null,
    created_at: '2026-01-01T00:00:00Z',
    chunk_count: 0,
    ...overrides,
  }
}

export type StyleOut = components['schemas']['StyleOut']
export type RunOut = components['schemas']['RunOut']
export type PairOut = components['schemas']['PairOut']
export type ProviderOut = components['schemas']['ProviderOut']
export type ProviderKeyOut = components['schemas']['ProviderKeyOut']

export const STYLE_ID = '33333333-3333-4333-8333-333333333333'
export const RUN_ID = '44444444-4444-4444-8444-444444444444'

export function makeStyle(overrides: Partial<StyleOut> = {}): StyleOut {
  return {
    id: STYLE_ID,
    template_key: null,
    description: 'A friendly support agent who answers briefly.',
    tone: 'friendly',
    length: 'medium',
    format: 'plain',
    language: 'en',
    examples: [{ input: 'How do I reset?', output: 'Hold the button for 5 seconds.' }],
    system_prompt_in_data: false,
    dataset_format: 'qa_chat',
    created_at: '2026-01-01T00:00:00Z',
    warnings: [],
    ...overrides,
  }
}

export function makeRun(overrides: Partial<RunOut> = {}): RunOut {
  return {
    id: RUN_ID,
    kind: 'preview',
    state: 'done',
    style_id: STYLE_ID,
    pairs_per_chunk: 2,
    target_pairs: 1000,
    total_chunks: 4,
    done_chunks: 4,
    pairs_generated: 8,
    pairs_kept: 8,
    tokens_in: 0,
    tokens_out: 0,
    resume_at: null,
    error: null,
    started_at: null,
    finished_at: null,
    ...overrides,
  }
}

export function makePair(overrides: Partial<PairOut> = {}): PairOut {
  const question = overrides.question ?? 'How do I reset the device?'
  const answer = overrides.answer ?? 'Hold the button for five seconds.'
  return {
    id: 'p1',
    dataset_format: 'qa_chat',
    question,
    answer,
    record: { format: 'qa_chat', question, answer },
    split: 'train',
    origin: 'generated',
    judge_correctness: 5,
    judge_style: 4,
    judge_reason: null,
    kept: true,
    dropped_reason: null,
    edited: false,
    chunk: { id: 'c1', section_path: 'Setup > Reset', excerpt: 'To reset, hold the button.' },
    ...overrides,
  }
}

export const PROVIDERS: ProviderOut[] = [
  {
    provider: 'groq',
    name: 'Groq',
    models: [{ id: 'llama-3.3-70b', license: 'Llama 3.3', rpm: 30, tpd: 100000 }],
    requires_terms_ack: false,
    note: null,
    key_help_url: 'https://console.groq.com/keys',
  },
  {
    provider: 'gemini',
    name: 'Gemini',
    models: [{ id: 'gemini-2.5-flash', license: null, rpm: 10, tpd: null }],
    requires_terms_ack: true,
    note: 'Not available in the EU/UK.',
    key_help_url: 'https://aistudio.google.com/apikey',
  },
]

export function makeKey(overrides: Partial<ProviderKeyOut> = {}): ProviderKeyOut {
  return {
    provider: 'groq',
    last4: '1234',
    status: 'valid',
    priority: 0,
    default_model: null,
    terms_acknowledged: false,
    last_verified_at: null,
    quota_reset_at: null,
    ...overrides,
  }
}

export type TrainingJobOut = components['schemas']['TrainingJobOut']
export type KaggleAccountOut = components['schemas']['KaggleAccountOut']
export type EvaluationOut = components['schemas']['EvaluationOut']
export type BaseModelOut = components['schemas']['BaseModelOut']
export type PresetOut = components['schemas']['PresetOut']

export const JOB_ID = '55555555-5555-4555-8555-555555555555'

export function makeJob(overrides: Partial<TrainingJobOut> = {}): TrainingJobOut {
  return {
    id: JOB_ID,
    state: 'running',
    backend: 'colab',
    external_url: null,
    launch_attempts: 0,
    base_model_id: 'unsloth/Qwen3.5-4B',
    base_model_license: 'Apache 2.0',
    is_llama: false,
    train_mode: 'lora16',
    preset: 'balanced',
    hyperparams: {},
    current_step: 50,
    max_steps: 200,
    last_loss: 1.25,
    last_heartbeat_at: null,
    pause_reason: null,
    runtime_info: { gpu_name: 'Tesla T4', vram_gb: 15 },
    exports: null,
    metrics: null,
    error: null,
    started_at: '2026-01-01T00:00:00Z',
    completed_at: null,
    created_at: '2026-01-01T00:00:00Z',
    token_prefix: 'dtj_ab12',
    token_expires_at: '2026-02-01T00:00:00Z',
    checkpoint_step: null,
    checkpoint_uploaded_at: null,
    est_minutes: 45,
    ...overrides,
  }
}

export function makeEvaluation(overrides: Partial<EvaluationOut> = {}): EvaluationOut {
  return {
    state: 'done',
    n_items: 20,
    base_scores: { correctness: 3, style: 2, overall: 2.5 },
    tuned_scores: { correctness: 4, style: 4.5, overall: 4.2 },
    samples: [
      {
        question: 'How do I reset the device?',
        reference: 'Hold the button for five seconds.',
        base_answer: 'Try turning it off and on.',
        tuned_answer: 'Hold the button for five seconds.',
        base_score: 2,
        tuned_score: 5,
        gain: 3,
      },
    ],
    metrics: null,
    error: null,
    ...overrides,
  }
}

export const CATALOG: BaseModelOut[] = [
  {
    id: 'unsloth/Qwen3.5-4B',
    display_name: 'Qwen3.5 4B',
    params_b: 4,
    license: 'Apache 2.0',
    train_mode: 'lora16',
    fits_t4: 'yes',
    vram_gb: 12,
    recommended: true,
    playground_supported: true,
    note: 'Best quality on a free T4.',
    est_minutes: { quick: 20, balanced: 45, thorough: 90 },
  },
  {
    id: 'unsloth/Qwen3-8B',
    display_name: 'Qwen3 8B',
    params_b: 8,
    license: 'Apache 2.0',
    train_mode: 'qlora4',
    fits_t4: 'unconfirmed',
    vram_gb: 14,
    recommended: false,
    playground_supported: false,
    note: null,
    est_minutes: { quick: 40, balanced: 80, thorough: 160 },
  },
]

const hp = { epochs: 1, lora_r: 16 as const, lora_alpha: 32, learning_rate: 0.0002, batch_size: 2, grad_accum: 4, max_seq_len: 1024 }
export const PRESETS = [
  { key: 'quick', name: 'Quick', description: 'A fast first try.', hyperparams: hp },
  { key: 'balanced', name: 'Balanced', description: 'Good for most projects.', hyperparams: hp },
  { key: 'thorough', name: 'Thorough', description: 'Longest, best quality.', hyperparams: hp },
] as unknown as PresetOut[]

export function makeKaggle(overrides: Partial<KaggleAccountOut> = {}): KaggleAccountOut {
  return {
    username: 'alice',
    token_hint: '…ab12',
    status: 'ok',
    status_message: null,
    gpu_hours_used: 4.5,
    gpu_hours_total: 30,
    quota_refresh_at: '2026-01-05T00:00:00Z',
    checked_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

export const DATASET_FORMATS: components['schemas']['FormatInfo'][] = [
  {
    key: 'qa_chat',
    name: 'Questions & answers',
    description: 'One question and one answer per example.',
    best_for: 'FAQ bots.',
    relative_cost: 1,
    input_label: 'Question',
    output_label: 'Answer',
    sample: { format: 'qa_chat', question: 'How long is the warranty?', answer: 'Two years.' },
  },
  {
    key: 'instruction',
    name: 'Instructions (Alpaca)',
    description: 'A task, an optional passage to work on, and the result.',
    best_for: 'Summarize, extract, rewrite.',
    relative_cost: 1.3,
    input_label: 'Instruction',
    output_label: 'Output',
    sample: { format: 'instruction', instruction: 'List the steps.', input: 'Unplug it, then wait.', output: '1. Unplug.\n2. Wait.' },
  },
  {
    key: 'multi_turn',
    name: 'Conversations',
    description: 'Dialogues of two to four turns with follow-up questions.',
    best_for: 'Chat assistants.',
    relative_cost: 3,
    input_label: 'Conversation',
    output_label: 'Last answer',
    sample: {
      format: 'multi_turn',
      messages: [
        { role: 'user', content: 'How long is the warranty?' },
        { role: 'assistant', content: 'Two years.' },
        { role: 'user', content: 'Does it cover water damage?' },
        { role: 'assistant', content: 'No.' },
      ],
    },
  },
]
