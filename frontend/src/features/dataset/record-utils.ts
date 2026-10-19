import type { components } from '@/lib/api/schema'

/** A whole training example in its dataset format's shape (ADR-0003). */
export type PairRecord = components['schemas']['PairOut']['record']
export type DatasetFormat = components['schemas']['PairOut']['dataset_format']
export type FormatInfo = components['schemas']['FormatInfo']
export type Turn = components['schemas']['Turn']

export const MAX_TURNS = 8

/** Column and field names per format. `question`/`answer` on a pair always hold the first prompt and last reply. */
export const LABELS: Record<DatasetFormat, { input: string; output: string; example: string }> = {
  qa_chat: { input: 'Question', output: 'Answer', example: 'pair' },
  instruction: { input: 'Instruction', output: 'Output', example: 'example' },
  multi_turn: { input: 'Opening question', output: 'Last answer', example: 'conversation' },
}

export function emptyRecord(format: DatasetFormat): PairRecord {
  if (format === 'instruction') return { format, instruction: '', input: '', output: '' }
  if (format === 'multi_turn')
    return {
      format,
      messages: [
        { role: 'user', content: '' },
        { role: 'assistant', content: '' },
      ],
    }
  return { format, question: '', answer: '' }
}

export function trimRecord(record: PairRecord): PairRecord {
  if (record.format === 'instruction')
    return { format: record.format, instruction: record.instruction.trim(), input: (record.input ?? '').trim(), output: record.output.trim() }
  if (record.format === 'multi_turn') return { format: record.format, messages: record.messages.map((m) => ({ role: m.role, content: m.content.trim() })) }
  return { format: record.format, question: record.question.trim(), answer: record.answer.trim() }
}

/** What's missing before the record can be saved (mirrors the server's checks), or null. */
export function recordProblem(record: PairRecord): string | null {
  const r = trimRecord(record)
  if (r.format === 'instruction') return r.instruction && r.output ? null : 'Fill in the instruction and the output.'
  if (r.format === 'multi_turn') return r.messages.every((m) => m.content) ? null : 'Fill in every turn, or remove the empty ones.'
  return r.question && r.answer ? null : 'Fill in both the question and the answer.'
}

export const sameRecord = (a: PairRecord, b: PairRecord) => JSON.stringify(trimRecord(a)) === JSON.stringify(trimRecord(b))
