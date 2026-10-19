import type { Evaluation } from '@/features/training/api'

export type Sample = {
  question: string
  /** Earlier turns of a conversation (conversation datasets only), as "User: …" / "Assistant: …" lines. */
  context: string | null
  reference: string | null
  base_answer: string | null
  tuned_answer: string | null
  base_score: number | null
  tuned_score: number | null
  gain: number | null
}

const str = (v: unknown): string | null => (typeof v === 'string' ? v : null)
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/** Samples arrive as loose JSON; keep only well-formed entries. */
export function parseSamples(raw: Evaluation['samples']): Sample[] {
  return (raw ?? []).flatMap((s) => {
    const question = str(s['question'])
    if (!question) return []
    return [
      {
        question,
        context: str(s['context']),
        reference: str(s['reference']),
        base_answer: str(s['base_answer']),
        tuned_answer: str(s['tuned_answer']),
        base_score: num(s['base_score']),
        tuned_score: num(s['tuned_score']),
        gain: num(s['gain']),
      },
    ]
  })
}

export const SCORE_LABELS: [key: string, label: string][] = [
  ['correctness', 'Accuracy'],
  ['style', 'Style'],
  ['overall', 'Overall'],
]

/** Judge scores are 1-5; if every value is within 0-1 treat the scale as 0-1. */
export function scoreScale(...groups: (Record<string, number> | null)[]): number {
  const values = groups.flatMap((g) => (g ? Object.values(g) : []))
  return values.length > 0 && values.every((v) => v <= 1) ? 1 : 5
}

export function metricNumber(metrics: Record<string, unknown> | null | undefined, key: string): number | null {
  const v = metrics?.[key]
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}
