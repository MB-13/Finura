import { CheckCircle2, Clock, ExternalLink, Loader2, OctagonAlert, RefreshCw, Trash2, type LucideIcon } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { toast } from 'sonner'

import { Callout } from '@/components/Callout'
import { ErrorState } from '@/components/ErrorState'
import { KeyValue } from '@/components/KeyValue'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import {
  kaggleStatusLabel,
  useConnectKaggle,
  useDisconnectKaggle,
  useKaggle,
  useRecheckKaggle,
  type KaggleAccount,
  type KaggleStatus,
} from '@/features/compute/api'
import { ApiError } from '@/lib/api/client'
import { qk } from '@/lib/query-keys'
import { useNow } from '@/lib/useNow'
import { cn } from '@/lib/utils'
import { useQueryClient } from '@tanstack/react-query'

const chip: Record<KaggleStatus, { icon: LucideIcon; className: string; spin?: boolean }> = {
  ok: { icon: CheckCircle2, className: 'bg-success-muted text-success-muted-foreground' },
  invalid: { icon: OctagonAlert, className: 'bg-destructive-muted text-destructive-muted-foreground' },
  no_gpu_quota: { icon: Clock, className: 'bg-warning-muted text-warning-muted-foreground' },
  unchecked: { icon: Loader2, className: 'bg-secondary text-secondary-foreground', spin: true },
}

const KAGGLE_URL = 'https://www.kaggle.com'

function formatReset(iso: string): string {
  return new Date(iso).toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function KaggleCard() {
  const kaggle = useKaggle()
  const status = kaggle.data?.status
  const ChipIcon = status ? chip[status].icon : null

  return (
    <div role="region" aria-label="Kaggle training" className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-card-title">Kaggle</h3>
          <Badge>Recommended</Badge>
          {status && ChipIcon && (
            <Badge variant="ghost" className={cn('sm:ml-auto', chip[status].className)}>
              <ChipIcon className={cn(chip[status].spin && 'motion-safe:animate-spin')} aria-hidden />
              <span role="status" aria-live="polite">
                {kaggleStatusLabel(status)}
              </span>
            </Badge>
          )}
        </div>
        <p className="text-sm text-muted-foreground">
          A free T4 GPU in your own Kaggle account, about 30 GPU-hours a week. Training starts automatically. There is no
          notebook to run.
        </p>
      </div>
        {kaggle.isPending ? (
          <Skeleton aria-busy="true" aria-label="Loading Kaggle account" className="h-32" />
        ) : kaggle.isError ? (
          <ErrorState message={kaggle.error.message} onRetry={() => kaggle.refetch()} />
        ) : kaggle.data ? (
          <ConnectedKaggle account={kaggle.data} />
        ) : (
          <ConnectKaggleForm />
        )}
    </div>
  )
}

function ConnectKaggleForm() {
  const connect = useConnectKaggle()
  const usernameId = useId()
  const tokenId = useId()
  const usernameErrorId = useId()
  const tokenErrorId = useId()
  const tokenHintId = useId()
  const [username, setUsername] = useState('')
  const [token, setToken] = useState('')
  const error = connect.error
  const fieldErrors = error instanceof ApiError ? error.fieldErrors : {}
  const generalError = error && Object.keys(fieldErrors).length === 0 ? error.message : undefined

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!username.trim() || !token.trim()) return
    connect.mutate(
      { username: username.trim(), api_token: token.trim() },
      {
        onSuccess: () => {
          setToken('') // never keep the token around once sent
          toast.success('Kaggle details saved. Checking them now.')
        },
      },
    )
  }

  return (
    <>
      <ol role="list" aria-label="How to connect Kaggle" className="flex flex-col gap-3 border-l-2 pl-4 text-sm">
        {[
          <>
            Create an account or sign in at{' '}
            <a href={KAGGLE_URL} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-medium text-primary underline underline-offset-4">
              kaggle.com <ExternalLink className="size-3.5" aria-hidden />
            </a>
            .
          </>,
          <>
            <strong>Verify your phone number</strong> (Kaggle, Settings, Phone verification). Kaggle requires it for GPU and internet.
          </>,
          <>
            In Kaggle, go to Settings, API, and choose <em>Create New Token</em>.
          </>,
          <>Paste your username and the token below.</>,
        ].map((step, i) => (
          <li key={i} className="flex gap-3">
            <span
              aria-hidden
              className="w-4 shrink-0 pt-0.5 font-mono text-xs tabular-nums text-muted-foreground"
            >
              {i + 1}
            </span>
            <span className="min-w-0">{step}</span>
          </li>
        ))}
      </ol>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={usernameId}>Kaggle username</Label>
          <Input
            id={usernameId}
            autoComplete="off"
            spellCheck={false}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            aria-invalid={Boolean(fieldErrors['username'])}
            aria-describedby={fieldErrors['username'] ? usernameErrorId : undefined}
          />
          {fieldErrors['username'] && <p id={usernameErrorId} role="alert" className="text-sm text-destructive-muted-foreground">{fieldErrors['username'][0]}</p>}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={tokenId}>Kaggle API token</Label>
          <Input
            id={tokenId}
            type="password"
            autoComplete="off"
            spellCheck={false}
            placeholder="Paste your token"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            aria-invalid={Boolean(fieldErrors['api_token'])}
            aria-describedby={fieldErrors['api_token'] ? `${tokenHintId} ${tokenErrorId}` : tokenHintId}
          />
          <p id={tokenHintId} className="text-caption text-muted-foreground">Write-only: we store it encrypted and never show it again.</p>
          {fieldErrors['api_token'] && <p id={tokenErrorId} role="alert" className="text-sm text-destructive-muted-foreground">{fieldErrors['api_token'][0]}</p>}
        </div>
        {generalError && (
          <p role="alert" className="text-sm text-destructive-muted-foreground">
            {generalError}
          </p>
        )}
        <Button type="submit" className="self-start" disabled={connect.isPending || !username.trim() || !token.trim()}>
          {connect.isPending ? 'Saving…' : 'Connect Kaggle'}
        </Button>
      </form>
    </>
  )
}

function ConnectedKaggle({ account }: { account: KaggleAccount }) {
  const queryClient = useQueryClient()
  const recheck = useRecheckKaggle()
  const disconnect = useDisconnectKaggle()
  const now = useNow(5000)
  const [confirm, setConfirm] = useState(false)
  const pollUntil = queryClient.getQueryData<number>(qk.kagglePollUntil())
  const stillChecking = account.status === 'unchecked' && pollUntil !== undefined && now > pollUntil

  return (
    <>
      <KeyValue
        items={[
          { label: 'Username', value: account.username, mono: true },
          { label: 'API token', value: account.token_hint, mono: true },
        ]}
      />

      {account.gpu_hours_total !== null && account.gpu_hours_used !== null && (
        <div className="flex flex-col gap-2 border-t pt-4">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <span className="text-eyebrow">GPU hours this week</span>
            <span className="font-mono text-[0.8125rem] tabular-nums">
              {account.gpu_hours_used} of {account.gpu_hours_total} used
            </span>
          </div>
          <Progress
            aria-label="GPU hours used this week"
            value={account.gpu_hours_total > 0 ? Math.min(100, (account.gpu_hours_used / account.gpu_hours_total) * 100) : 0}
            indicatorClassName={account.gpu_hours_used >= account.gpu_hours_total ? 'bg-warning' : undefined}
          />
          {account.quota_refresh_at && (
            <span className="text-caption text-muted-foreground">Resets {formatReset(account.quota_refresh_at)}</span>
          )}
        </div>
      )}

      <div aria-live="polite" className="flex flex-col gap-3 empty:hidden">
        {account.status === 'unchecked' && !stillChecking && (
          <p className="text-sm text-muted-foreground">Checking your Kaggle account…</p>
        )}
        {stillChecking && (
          <p className="text-sm text-muted-foreground">Still checking. This can take a minute. Use Re-check to try again.</p>
        )}
        {account.status !== 'unchecked' && account.status_message && (
          <Callout tone={account.status === 'ok' ? 'success' : account.status === 'invalid' ? 'destructive' : 'warning'}>
            {account.status_message}
          </Callout>
        )}
      </div>

      <div className="flex flex-wrap gap-2 border-t pt-4">
        <Button
          variant="outline"
          size="sm"
          disabled={recheck.isPending}
          onClick={() => recheck.mutate(undefined, { onError: (err) => toast.error(err.message) })}
        >
          <RefreshCw aria-hidden /> Re-check
        </Button>
        <Button variant="outline" size="sm" onClick={() => setConfirm(true)}>
          <Trash2 aria-hidden /> Disconnect
        </Button>
      </div>

      <AlertDialog open={confirm} onOpenChange={setConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Disconnect Kaggle?</AlertDialogTitle>
            <AlertDialogDescription>
              We delete the saved token. New training jobs can use Google Colab instead. You can connect again at any time.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep connected</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={disconnect.isPending}
              onClick={(e) => {
                e.preventDefault()
                disconnect.mutate(undefined, {
                  onSuccess: () => {
                    setConfirm(false)
                    toast.success('Kaggle disconnected')
                  },
                  onError: (err) => toast.error(err.message),
                })
              }}
            >
              {disconnect.isPending ? 'Disconnecting…' : 'Disconnect'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
