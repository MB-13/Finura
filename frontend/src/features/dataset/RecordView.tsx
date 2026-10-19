import type { ReactNode } from 'react'

import type { PairRecord } from '@/features/dataset/record-utils'
import { cn } from '@/lib/utils'

const fieldLabel = 'text-caption font-medium text-muted-foreground'

/** A whole training example, laid out for its format. The reply the model learns is marked with a primary rule. */
export function RecordView({ record, className }: { record: PairRecord; className?: string }) {
  if (record.format === 'multi_turn') {
    return (
      <ol className={cn('flex flex-col gap-3', className)} aria-label="Conversation">
        {record.messages.map((m, i) => (
          <li key={i} className={cn('flex flex-col gap-1', m.role === 'assistant' && 'border-l-2 border-primary/40 pl-3')}>
            <span className={fieldLabel}>{m.role === 'user' ? 'User' : 'Assistant'}</span>
            <p className={cn('text-body whitespace-pre-wrap', m.role === 'user' && 'font-medium')}>{m.content}</p>
          </li>
        ))}
      </ol>
    )
  }
  if (record.format === 'instruction') {
    return (
      <div className={cn('flex flex-col gap-4', className)}>
        <Field label="Instruction">
          <p className="text-body font-medium whitespace-pre-wrap">{record.instruction}</p>
        </Field>
        {record.input ? (
          <Field label="Input">
            <blockquote className="rounded-lg bg-muted/60 px-3 py-2 text-sm whitespace-pre-wrap">{record.input}</blockquote>
          </Field>
        ) : null}
        <Field label="Output" reply>
          <p className="text-body whitespace-pre-wrap">{record.output}</p>
        </Field>
      </div>
    )
  }
  return (
    <div className={cn('flex flex-col gap-4', className)}>
      <Field label="Question">
        <p className="text-body font-medium whitespace-pre-wrap">{record.question}</p>
      </Field>
      <Field label="Answer" reply>
        <p className="text-body whitespace-pre-wrap">{record.answer}</p>
      </Field>
    </div>
  )
}

function Field({ label, reply = false, children }: { label: string; reply?: boolean; children: ReactNode }) {
  return (
    <div className={cn('flex flex-col gap-1', reply && 'border-l-2 border-primary/40 pl-3')}>
      <span className={fieldLabel}>{label}</span>
      {children}
    </div>
  )
}
