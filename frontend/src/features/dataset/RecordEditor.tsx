import { Plus, X } from 'lucide-react'
import { useId } from 'react'

import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { MAX_TURNS, type PairRecord } from '@/features/dataset/record-utils'

type Props = {
  record: PairRecord
  onChange: (record: PairRecord) => void
  /** Appended to every field label so screen readers know which example is being edited, e.g. " for pair 3". */
  labelSuffix?: string
  /** Server field errors, keyed like `record.messages.2.content`. */
  errors?: Record<string, string[]>
}

/** Edits one training example in its format's shape. Controlled: the parent owns the record. */
export function RecordEditor({ record, onChange, labelSuffix = '', errors = {} }: Props) {
  const id = useId()
  const err = (key: string) => errors[`record.${key}`]?.[0] ?? errors[key]?.[0]

  if (record.format === 'multi_turn') {
    const turns = record.messages
    const setTurn = (i: number, content: string) => onChange({ ...record, messages: turns.map((t, j) => (j === i ? { ...t, content } : t)) })
    return (
      <fieldset className="flex flex-col gap-3">
        <legend className="sr-only">Conversation{labelSuffix}</legend>
        {turns.map((t, i) => {
          const label = `${t.role === 'user' ? 'User' : 'Assistant'} turn ${Math.floor(i / 2) + 1}${labelSuffix}`
          return (
            <div key={i} className={t.role === 'assistant' ? 'flex flex-col gap-1.5 border-l-2 border-primary/40 pl-3' : 'flex flex-col gap-1.5'}>
              <Label htmlFor={`${id}-${i}`}>{label}</Label>
              <Textarea id={`${id}-${i}`} value={t.content} onChange={(e) => setTurn(i, e.target.value)} aria-invalid={Boolean(err(`messages.${i}.content`))} />
              <FieldError message={err(`messages.${i}.content`)} />
            </div>
          )
        })}
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={turns.length + 2 > MAX_TURNS}
            onClick={() =>
              onChange({
                ...record,
                messages: [...turns, { role: 'user', content: '' }, { role: 'assistant', content: '' }],
              })
            }
          >
            <Plus aria-hidden /> Add a follow-up
          </Button>
          {turns.length > 2 && (
            <Button type="button" variant="ghost" size="sm" onClick={() => onChange({ ...record, messages: turns.slice(0, -2) })}>
              <X aria-hidden /> Remove the last follow-up
            </Button>
          )}
        </div>
        <FieldError message={err('messages')} />
      </fieldset>
    )
  }

  if (record.format === 'instruction') {
    return (
      <>
        <TextField id={`${id}-i`} label={`Instruction${labelSuffix}`} value={record.instruction} onChange={(v) => onChange({ ...record, instruction: v })} error={err('instruction')} />
        <TextField
          id={`${id}-in`}
          label={`Input${labelSuffix} (optional)`}
          hint="The text the instruction works on. Leave empty when the instruction stands on its own."
          value={record.input ?? ''}
          onChange={(v) => onChange({ ...record, input: v })}
          error={err('input')}
        />
        <TextField id={`${id}-o`} label={`Output${labelSuffix}`} value={record.output} onChange={(v) => onChange({ ...record, output: v })} error={err('output')} />
      </>
    )
  }

  return (
    <>
      <TextField id={`${id}-q`} label={`Question${labelSuffix}`} value={record.question} onChange={(v) => onChange({ ...record, question: v })} error={err('question')} />
      <TextField id={`${id}-a`} label={`Answer${labelSuffix}`} value={record.answer} onChange={(v) => onChange({ ...record, answer: v })} error={err('answer')} />
    </>
  )
}

function TextField({
  id,
  label,
  hint,
  value,
  onChange,
  error,
}: {
  id: string
  label: string
  hint?: string
  value: string
  onChange: (value: string) => void
  error?: string
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Textarea id={id} value={value} onChange={(e) => onChange(e.target.value)} aria-invalid={Boolean(error)} aria-describedby={hint ? `${id}-hint` : undefined} />
      {hint && (
        <p id={`${id}-hint`} className="text-caption text-muted-foreground">
          {hint}
        </p>
      )}
      <FieldError message={error} />
    </div>
  )
}

function FieldError({ message }: { message: string | undefined }) {
  return message ? <p className="text-sm text-destructive">{message}</p> : null
}
