import { Check, Copy } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

// The notebook writes the GGUF, a Modelfile (with the right chat template) and a README into one export folder.
const COMMANDS = 'cd path/to/your/export-folder\nollama create my-doctune-model -f Modelfile\nollama run my-doctune-model'

/** Terminal-style block: window dots + title, mono lines, `$` prompt for shell commands (not selectable, not copied). */
function Snippet({ label, code, prompt = false }: { label: string; code: string; prompt?: boolean }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="overflow-hidden rounded-lg border bg-muted/40">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-1">
        <span className="flex items-center gap-2">
          <span aria-hidden className="flex gap-1">
            <span className="size-2 rounded-full bg-border" />
            <span className="size-2 rounded-full bg-border" />
            <span className="size-2 rounded-full bg-border" />
          </span>
          <span className="text-eyebrow">{label}</span>
        </span>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          aria-label={`Copy ${label}`}
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(code)
              setCopied(true)
            } catch {
              setCopied(false)
            }
          }}
        >
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />} {copied ? 'Copied' : 'Copy'}
        </Button>
      </div>
      <pre className="overflow-x-auto px-3.5 py-3 font-mono text-[0.8125rem] leading-6">
        <code className="flex flex-col">
          {code.split('\n').map((line, i) => (
            <span key={i} className={cn('whitespace-pre', prompt && "before:mr-2 before:text-muted-foreground before:select-none before:content-['$']")}>
              {line}
            </span>
          ))}
        </code>
      </pre>
    </div>
  )
}

export function OllamaInstructions({ kaggle = false, baseModel }: { kaggle?: boolean; baseModel?: string }) {
  const intro = (
    <>
      Run your model on your own computer with{' '}
      <a className="font-medium text-primary underline underline-offset-4" href="https://ollama.com" target="_blank" rel="noopener noreferrer">
        Ollama
      </a>
      .
    </>
  )
  if (kaggle) {
    // Kaggle runs upload only the adapter; Ollama layers it on the original model with an ADAPTER line.
    const modelfile = `FROM <a GGUF of ${baseModel ?? 'the original model'}>\nADAPTER ./adapter.gguf`
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">
          {intro} Download <span className="font-medium text-foreground">Adapter for llama.cpp (GGUF)</span> above, then
          put this <code className="rounded bg-muted px-1 py-0.5 text-[0.8125rem]">Modelfile</code> next to it:
        </p>
        <Snippet label="Modelfile" code={modelfile} />
        <Snippet label="Commands" code={'ollama create my-doctune-model -f Modelfile\nollama run my-doctune-model'} prompt />
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted-foreground">
        {intro} Download the export folder the notebook saved to your Google Drive (or Hugging Face). It already contains the
        GGUF file and a ready-made <code className="rounded bg-muted px-1 py-0.5 text-[0.8125rem]">Modelfile</code> with the right chat template, so you only run:
      </p>
      <Snippet label="Commands" code={COMMANDS} prompt />
    </div>
  )
}
