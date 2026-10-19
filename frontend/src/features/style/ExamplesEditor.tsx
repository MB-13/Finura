import { Plus, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import type { Example } from '@/features/style/api'

export const MIN_EXAMPLES = 1
export const MAX_EXAMPLES = 5

type Props = {
  examples: Example[]
  onChange: (examples: Example[]) => void
  error?: string
  disabled?: boolean
}

/** 1-5 input/output pairs showing the model how to answer. At least one is required. */
export function ExamplesEditor({ examples, onChange, error, disabled }: Props) {
  function update(index: number, change: Partial<Example>) {
    onChange(examples.map((ex, i) => (i === index ? { ...ex, ...change } : ex)))
  }

  return (
    <fieldset className="flex min-w-0 flex-col gap-4" disabled={disabled} aria-describedby={error ? 'examples-error' : undefined}>
      <legend className="mb-3 flex w-full flex-wrap items-baseline justify-between gap-x-3">
        <span className="text-card-title">Examples</span>
        <span className="text-metric text-xs font-normal text-muted-foreground">
          {examples.length} of {MAX_EXAMPLES}
        </span>
      </legend>
      <p className="text-sm text-muted-foreground">
        Write a question and the answer you&apos;d love to see. Two or three examples are enough to teach the style.
      </p>
      <ul className="flex flex-col divide-y">
        {examples.map((ex, i) => (
          <li key={i} className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 text-sm font-medium">
                <span aria-hidden className="text-eyebrow tabular-nums">
                  {String(i + 1).padStart(2, '0')}
                </span>
                Example {i + 1}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`Remove example ${i + 1}`}
                disabled={examples.length <= MIN_EXAMPLES}
                onClick={() => onChange(examples.filter((_, j) => j !== i))}
              >
                <Trash2 aria-hidden />
              </Button>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`example-${i}-input`}>
                  <span aria-hidden>Question</span>
                </Label>
                <Textarea
                  id={`example-${i}-input`}
                  aria-label={`Example ${i + 1} question`}
                  rows={3}
                                    placeholder="What would a user ask?"
                  value={ex.input}
                  maxLength={2000}
                  onChange={(e) => update(i, { input: e.target.value })}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`example-${i}-output`}>
                  <span aria-hidden>Answer</span>
                </Label>
                <Textarea
                  id={`example-${i}-output`}
                  aria-label={`Example ${i + 1} answer`}
                  rows={3}
                                    placeholder="How should the model reply?"
                  value={ex.output}
                  maxLength={4000}
                  onChange={(e) => update(i, { output: e.target.value })}
                />
              </div>
            </div>
          </li>
        ))}
      </ul>
      {error && (
        <p id="examples-error" role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="self-start"
        disabled={examples.length >= MAX_EXAMPLES}
        onClick={() => onChange([...examples, { input: '', output: '' }])}
      >
        <Plus aria-hidden /> Add example
      </Button>
    </fieldset>
  )
}
