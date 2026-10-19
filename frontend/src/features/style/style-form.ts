import type { Example, StyleIn, StyleOut } from '@/features/style/api'

export const MIN_DESCRIPTION = 10
export const MAX_DESCRIPTION = 2000
export const MIN_TARGET = 50
export const MAX_TARGET = 2000

export const TONES: StyleIn['tone'][] = ['neutral', 'friendly', 'formal', 'casual', 'technical', 'enthusiastic']
export const LENGTHS: StyleIn['length'][] = ['short', 'medium', 'long']
export const FORMATS: StyleIn['format'][] = ['plain', 'bullets', 'json', 'markdown']
export const LANGUAGES: Record<string, string> = {
  en: 'English',
  es: 'Spanish',
  fr: 'French',
  de: 'German',
  it: 'Italian',
  pt: 'Portuguese',
  nl: 'Dutch',
  hi: 'Hindi',
  ja: 'Japanese',
  zh: 'Chinese',
}

export const EMPTY_STYLE: StyleIn = {
  template_key: null,
  description: '',
  tone: 'neutral',
  length: 'medium',
  format: 'plain',
  language: 'en',
  examples: [{ input: '', output: '' }],
  system_prompt_in_data: false,
  dataset_format: 'qa_chat',
}

export function toStyleIn(style: StyleIn | StyleOut | null | undefined): StyleIn {
  if (!style) return EMPTY_STYLE
  return {
    template_key: style.template_key ?? null,
    description: style.description,
    tone: style.tone,
    length: style.length,
    format: style.format,
    language: style.language,
    examples: style.examples.length > 0 ? style.examples.map((e) => ({ ...e })) : EMPTY_STYLE.examples,
    system_prompt_in_data: style.system_prompt_in_data,
    dataset_format: style.dataset_format ?? 'qa_chat',
  }
}

export type FieldErrors = Record<string, string[]>

/** Local checks that mirror the API limits so users get instant feedback; the server is the real check. */
export function validateStyle(form: StyleIn): FieldErrors {
  const errors: FieldErrors = {}
  const len = form.description.trim().length
  if (len < MIN_DESCRIPTION) errors['description'] = [`Describe the style in at least ${MIN_DESCRIPTION} characters.`]
  else if (len > MAX_DESCRIPTION) errors['description'] = [`Keep the description under ${MAX_DESCRIPTION} characters.`]
  const examples = form.examples
  if (examples.some((e: Example) => !e.input.trim() !== !e.output.trim())) {
    errors['examples'] = ['Fill in both the question and the answer, or remove the example.']
  } else if (!examples.some((e) => e.input.trim() && e.output.trim())) {
    errors['examples'] = ['Add at least one example.']
  }
  return errors
}

/** Drop fully blank examples and trim text before sending. */
export function cleanStyle(form: StyleIn): StyleIn {
  return {
    ...form,
    description: form.description.trim(),
    examples: form.examples
      .filter((e) => e.input.trim() && e.output.trim())
      .map((e) => ({ input: e.input.trim(), output: e.output.trim() })),
  }
}

/** Errors for a field including nested keys such as `examples.0.input`. */
export function errorsFor(errors: FieldErrors, field: string): string | undefined {
  const hit = Object.entries(errors).find(([k]) => k === field || k.startsWith(`${field}.`) || k.startsWith(`${field}[`))
  return hit?.[1][0]
}
