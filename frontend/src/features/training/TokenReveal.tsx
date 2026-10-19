import { Check, Copy, KeyRound, RefreshCw, ShieldCheck } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { useRotateToken, type TrainingJob } from '@/features/training/api'
import { forgetToken, useRevealedToken } from '@/features/training/token-store'

function formatExpiry(iso: string | null | undefined): string | null {
  return iso ? new Date(iso).toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' }) : null
}

/**
 * Shows the job token once. Without a token in memory (reload, another device) only the prefix and expiry
 * are shown, with a button to rotate it.
 */
export function TokenReveal({ projectId, job, notebookUrl }: { projectId: string; job: TrainingJob; notebookUrl: string | null }) {
  const revealed = useRevealedToken(job.id)
  const rotate = useRotateToken(projectId, job.id)
  const [copied, setCopied] = useState(false)
  const rotateButton = useRef<HTMLButtonElement>(null)
  const refocusAfterHide = useRef(false)
  const expiry = formatExpiry(revealed?.expiresAt ?? job.token_expires_at)

  // "I've copied it" unmounts the focused button; move focus to the next control in the same section
  useEffect(() => {
    if (!revealed && refocusAfterHide.current) {
      refocusAfterHide.current = false
      rotateButton.current?.focus()
    }
  }, [revealed])

  async function copy(token: string) {
    try {
      await navigator.clipboard.writeText(token)
      setCopied(true)
      toast.success('Token copied')
    } catch {
      toast.error('Could not copy. Select the token and copy it by hand.')
    }
  }

  function regenerate() {
    rotate.mutate(revealed?.notebookUrl ?? notebookUrl, {
      onSuccess: () => {
        setCopied(false)
        toast.success('New token created. The old one no longer works.')
      },
      onError: (err) => toast.error(err.message),
    })
  }

  if (revealed) {
    return (
      <div className="flex flex-col gap-3 border-l-2 border-primary pl-4" aria-label="Job token" role="group">
        <p className="text-sm text-foreground/85">
          This is your job token. It is shown only once, so copy it now. You will paste it into the notebook.
        </p>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
          <code
            data-testid="job-token"
            className="min-w-0 flex-1 rounded-md border bg-background px-3.5 py-2.5 font-mono text-[0.9375rem] font-medium break-all select-all"
          >
            {revealed.token}
          </code>
          <Button type="button" size="lg" className="sm:h-auto" onClick={() => void copy(revealed.token)}>
            {copied ? <Check aria-hidden /> : <Copy aria-hidden />} {copied ? 'Copied' : 'Copy token'}
          </Button>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          {expiry ? (
            <p className="flex items-center gap-1.5 text-caption text-muted-foreground">
              <ShieldCheck className="size-3.5 shrink-0" aria-hidden /> Works for this job only and expires on {expiry}.
            </p>
          ) : (
            <span />
          )}
          <Button type="button" variant="ghost" size="sm" onClick={() => {
              refocusAfterHide.current = true
              forgetToken(job.id)
            }}>
            I&apos;ve copied it
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3 border-l-2 pl-4" aria-label="Job token" role="group">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <KeyRound className="size-4 text-muted-foreground" aria-hidden />
        <span>
          Token <code className="font-mono font-medium text-[0.8125rem]">{job.token_prefix ?? 'dtj_…'}…</code>
          {expiry && <span className="text-muted-foreground"> · expires {expiry}</span>}
        </span>
      </div>
      <p className="text-caption text-muted-foreground">
        For your safety the full token is only shown once. Lost it? Make a new one. The old one stops working.
      </p>
      {rotate.isError && (
        <p role="alert" className="text-sm text-destructive-muted-foreground">
          {rotate.error.message}
        </p>
      )}
      <Button ref={rotateButton} type="button" variant="outline" size="sm" className="self-start" disabled={rotate.isPending} onClick={regenerate}>
        <RefreshCw aria-hidden /> {rotate.isPending ? 'Creating…' : 'Generate a new token'}
      </Button>
    </div>
  )
}
