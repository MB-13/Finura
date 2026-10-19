import { ArrowDown, ArrowUp, ExternalLink, KeyRound, RefreshCw, Trash2 } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { toast } from 'sonner'

import { NativeSelect } from '@/components/NativeSelect'
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
import {
  useDeleteKey,
  usePatchKey,
  useSaveKey,
  useVerifyKey,
  type ProviderInfo,
  type ProviderKey,
} from '@/features/settings/api'
import { keyStatusChip, keyStatusLabel } from '@/features/settings/key-status'
import { ApiError } from '@/lib/api/client'
import { cn } from '@/lib/utils'

const FALLBACK_NOTES: Record<string, string> = {
  gemini: 'Speeds up generation. Not available in some EU/UK regions.',
  cerebras: 'Needs a payment method on file. Optional.',
}

type Props = {
  info: ProviderInfo
  keyInfo: ProviderKey | undefined
  /** Position among connected keys (for the up/down buttons). */
  index: number
  total: number
  onMove: (direction: -1 | 1) => void
}

export function ProviderKeyCard({ info, keyInfo, index, total, onMove }: Props) {
  const save = useSaveKey()
  const patch = usePatchKey()
  const remove = useDeleteKey()
  const verify = useVerifyKey()
  const keyId = useId()
  const modelId = useId()
  const termsId = useId()
  const keyErrorId = useId()
  const [apiKey, setApiKey] = useState('')
  const [terms, setTerms] = useState(keyInfo?.terms_acknowledged ?? false)
  const [draftModel, setDraftModel] = useState('')
  const [confirmRemove, setConfirmRemove] = useState(false)

  const model = keyInfo ? (keyInfo.default_model ?? '') : draftModel
  const error = save.error instanceof ApiError ? save.error : null
  const keyError = error?.fieldErrors['api_key']?.[0] ?? (error && !error.fieldErrors['api_key'] ? error.message : undefined)
  const needsTerms = info.requires_terms_ack && !terms

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!apiKey.trim() || needsTerms) return
    save.mutate(
      {
        provider: info.provider,
        body: { api_key: apiKey.trim(), default_model: model || null, terms_acknowledged: terms },
      },
      {
        onSuccess: () => {
          setApiKey('') // never keep the key around once sent
          toast.success(`${info.name} key saved. Checking it now.`)
        },
      },
    )
  }

  function changeModel(value: string) {
    if (!keyInfo) return setDraftModel(value)
    patch.mutate(
      { provider: info.provider, body: { default_model: value || null } },
      { onError: (err) => toast.error(err.message) },
    )
  }

  const chip = keyInfo ? keyStatusChip[keyInfo.status] : null
  const ChipIcon = chip?.icon

  return (
    <div role="region" aria-label={`${info.name} key`} className="flex flex-col gap-5 py-6 first:pt-0 last:pb-0">
      <div className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-card-title">{info.name}</h3>
          {info.provider === 'groq' && <Badge>Recommended</Badge>}
          {info.provider === 'gemini' && <Badge variant="info">Speeds up generation</Badge>}
          {info.provider === 'cerebras' && <Badge variant="secondary">Optional</Badge>}
          {keyInfo && chip && ChipIcon && (
            <Badge variant="ghost" className={cn('sm:ml-auto', chip.className)}>
              <ChipIcon className={cn(chip.spin && 'motion-safe:animate-spin')} aria-hidden />
              {keyStatusLabel(keyInfo)}
            </Badge>
          )}
        </div>
        <p className="text-sm text-muted-foreground">{info.note ?? FALLBACK_NOTES[info.provider]}</p>
      </div>
        {keyInfo && (
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-y py-3 text-sm">
            <div className="flex items-center gap-2">
              <KeyRound className="size-4 text-muted-foreground" aria-hidden />
              <span className="text-eyebrow">Saved key</span>
              <code className="font-mono text-[0.8125rem]">…{keyInfo.last4}</code>
            </div>
            <div className="flex items-center gap-1">
              <span className="mr-1 font-mono text-[0.8125rem] text-muted-foreground tabular-nums">{index >= 0 ? `Priority ${index + 1} of ${total}` : 'Priority'}</span>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Move ${info.name} up`}
                disabled={index <= 0}
                onClick={() => onMove(-1)}
              >
                <ArrowUp aria-hidden />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Move ${info.name} down`}
                disabled={index < 0 || index >= total - 1}
                onClick={() => onMove(1)}
              >
                <ArrowDown aria-hidden />
              </Button>
            </div>
            <div className="flex items-center gap-2 sm:ml-auto">
              <Button
                variant="outline"
                size="sm"
                disabled={verify.isPending}
                onClick={() => verify.mutate(info.provider, { onError: (err) => toast.error(err.message) })}
              >
                <RefreshCw aria-hidden /> Re-verify
              </Button>
              <Button variant="outline" size="sm" onClick={() => setConfirmRemove(true)}>
                <Trash2 aria-hidden /> Remove
              </Button>
            </div>
          </div>
        )}

        <div className="flex flex-col gap-1.5">
          <Label htmlFor={modelId}>Default model</Label>
          <NativeSelect id={modelId} value={model} onChange={(e) => changeModel(e.target.value)} disabled={patch.isPending}>
            <option value="">Automatic (rotate between models)</option>
            {info.models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.id}
                {m.license ? ` (${m.license})` : ''}
              </option>
            ))}
          </NativeSelect>
        </div>

        <form onSubmit={submit} className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={keyId}>{keyInfo ? `Replace ${info.name} key` : `${info.name} API key`}</Label>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                id={keyId}
                type="password"
                autoComplete="off"
                spellCheck={false}
                className="sm:flex-1"
                placeholder={keyInfo ? 'Paste a new key to replace the saved one' : 'Paste your key'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                aria-invalid={Boolean(keyError)}
                aria-describedby={keyError ? keyErrorId : undefined}
              />
              <Button type="submit" disabled={save.isPending || !apiKey.trim() || needsTerms}>
                {save.isPending ? 'Saving…' : keyInfo ? 'Replace key' : 'Save key'}
              </Button>
            </div>
            <p className="text-caption text-muted-foreground">
              Write-only: we store it encrypted and never show it again.
            </p>
            {keyError && (
              <p id={keyErrorId} role="alert" className="text-sm text-destructive-muted-foreground">
                {keyError}
              </p>
            )}
          </div>
          {info.requires_terms_ack && (
            <div className="flex items-start gap-2.5 border-l-2 border-warning py-0.5 pl-3">
              <input
                id={termsId}
                type="checkbox"
                className="mt-0.5 size-4 shrink-0 accent-primary"
                checked={terms}
                onChange={(e) => setTerms(e.target.checked)}
              />
              <Label htmlFor={termsId} className="text-sm leading-snug font-normal">
                I understand Google&apos;s terms restrict using Gemini outputs to build competing models.
              </Label>
            </div>
          )}
          <a
            href={info.key_help_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex w-fit items-center gap-1 rounded-sm text-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            Get a free key <ExternalLink className="size-3.5" aria-hidden />
          </a>
        </form>

      <AlertDialog open={confirmRemove} onOpenChange={setConfirmRemove}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove your {info.name} key?</AlertDialogTitle>
            <AlertDialogDescription>
              Dataset generation will no longer use {info.name}. You can add a key again at any time.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={remove.isPending}
              onClick={(e) => {
                e.preventDefault()
                remove.mutate(info.provider, {
                  onSuccess: () => {
                    setConfirmRemove(false)
                    toast.success(`${info.name} key removed`)
                  },
                  onError: (err) => toast.error(err.message),
                })
              }}
            >
              {remove.isPending ? 'Removing…' : 'Remove key'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
