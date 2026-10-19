import { Check, ChevronDown, NotebookPen, Zap, type LucideIcon } from 'lucide-react'
import { useId, useState, type FormEvent, type ReactNode } from 'react'
import { Tabs } from 'radix-ui'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Callout } from '@/components/Callout'
import { ErrorState } from '@/components/ErrorState'
import { NativeSelect } from '@/components/NativeSelect'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
  useCheckModel,
  useCreateTraining,
  useModelCatalog,
  usePresets,
  type Advanced,
  type PresetKey,
  type TrainingCreate,
} from '@/features/training/api'
import { gpuHoursLeft, useKaggle } from '@/features/compute/api'
import { ModelCard } from '@/features/training/ModelCard'
import { ModelCheckResult } from '@/features/training/ModelCheckResult'
import { CREATE_ERRORS } from '@/features/training/model-copy'
import { PresetPicker } from '@/features/training/PresetPicker'
import { ApiError } from '@/lib/api/client'
import { cn } from '@/lib/utils'

type Tab = 'catalog' | 'custom'
type Backend = TrainingCreate['backend']
const RANKS = [8, 16, 32, 64] as const

type AdvancedForm = { epochs: string; loraR: string; learningRate: string; maxSeqLen: string }
const EMPTY_ADVANCED: AdvancedForm = { epochs: '', loraR: '', learningRate: '', maxSeqLen: '' }

/** Only fields the user filled in are sent; the server fills the rest from the preset. */
function toAdvanced(f: AdvancedForm): Advanced | undefined {
  const out: Advanced = {}
  if (f.epochs.trim()) out.epochs = Number(f.epochs)
  if (f.loraR) out.lora_r = Number(f.loraR) as (typeof RANKS)[number]
  if (f.learningRate.trim()) out.learning_rate = Number(f.learningRate)
  if (f.maxSeqLen.trim()) out.max_seq_len = Number(f.maxSeqLen)
  return Object.keys(out).length > 0 ? out : undefined
}

type Props = { projectId: string; open: boolean; onOpenChange: (open: boolean) => void }

export function TrainSetupDialog({ projectId, open, onOpenChange }: Props) {
  const catalog = useModelCatalog(projectId, open)
  const presets = usePresets(open)
  const kaggle = useKaggle(open)
  const check = useCheckModel()
  const create = useCreateTraining(projectId)
  const hfInputId = useId()
  const advancedId = useId()

  const [tab, setTab] = useState<Tab>('catalog')
  const [modelId, setModelId] = useState<string | null>(null)
  const [hfId, setHfId] = useState('')
  const [licenseAck, setLicenseAck] = useState(false)
  const [preset, setPreset] = useState<PresetKey>('balanced')
  const [advanced, setAdvanced] = useState<AdvancedForm>(EMPTY_ADVANCED)
  const [chosenBackend, setChosenBackend] = useState<Backend | null>(null)

  const account = kaggle.data ?? null
  const kaggleReady = account?.status === 'ok'
  const backend: Backend = kaggleReady ? (chosenBackend ?? 'kaggle') : 'colab'
  const hoursLeft = account ? gpuHoursLeft(account) : null

  const models = catalog.data ?? []
  const selected = models.find((m) => m.id === modelId) ?? models.find((m) => m.recommended) ?? models[0]
  const checked = check.data && check.data.hf_id === hfId.trim() ? check.data : null
  const customBlocked = checked ? checked.blocking.length > 0 || !checked.ok : false

  const baseModelId = tab === 'catalog' ? selected?.id : checked?.hf_id
  const needsAck = tab === 'custom' && checked !== null && !checked.license_ok
  const canSubmit =
    Boolean(baseModelId) && (tab === 'catalog' || (checked !== null && !customBlocked)) && (!needsAck || licenseAck) && !create.isPending
  const minutes = tab === 'catalog' ? selected?.est_minutes : null
  const chatModel = models.find((m) => m.recommended && m.playground_supported) ?? models.find((m) => m.playground_supported)
  const noChat = tab === 'catalog' && selected !== undefined && !selected.playground_supported

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!baseModelId || !canSubmit) return
    create.mutate(
      { base_model_id: baseModelId, backend, preset, advanced: toAdvanced(advanced), license_ack: needsAck ? licenseAck : false },
      {
        onSuccess: () => {
          onOpenChange(false)
          toast.success('Training job created')
        },
      },
    )
  }

  const createError = create.error
  const createMessage = createError instanceof ApiError ? (CREATE_ERRORS[createError.code] ?? createError.message) : createError?.message
  const fieldErrors = createError instanceof ApiError ? Object.entries(createError.fieldErrors) : []

  function runCheck() {
    if (hfId.trim()) check.mutate(hfId.trim())
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Set up training</DialogTitle>
          <DialogDescription>
            {backend === 'kaggle'
              ? 'Pick the model to start from and how long to train. Training starts by itself on your Kaggle account.'
              : 'Pick the model to start from and how long to train. You will run it on a free Google Colab GPU in the next step.'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="flex flex-col gap-6">
          <fieldset className="flex flex-col gap-2" aria-busy={kaggle.isPending}>
            <legend className="mb-1 text-card-title">Where to train</legend>
            <div className="grid gap-3 sm:grid-cols-2">
            <BackendOption
              value="kaggle"
              checked={backend === 'kaggle'}
              disabled={!kaggleReady}
              onSelect={() => setChosenBackend('kaggle')}
              title={kaggleReady ? 'Automatically on Kaggle (recommended)' : 'Automatically on Kaggle'}
              hint={kaggleHint(account?.status, hoursLeft, kaggle.isPending)}
              icon={Zap}
              badge="Automatic"
            >
              {!kaggleReady && !kaggle.isPending && (
                <Link to="/settings" className="text-sm font-medium text-primary underline underline-offset-4" onClick={() => onOpenChange(false)}>
                  {account ? 'Open Kaggle settings' : 'Connect Kaggle to train automatically'}
                </Link>
              )}
            </BackendOption>
            <BackendOption
              value="colab"
              checked={backend === 'colab'}
              onSelect={() => setChosenBackend('colab')}
              title="Manually in Google Colab"
              hint="You run a notebook yourself and keep the tab open."
              icon={NotebookPen}
              badge="Manual"
            />
            </div>
          </fieldset>

          <Tabs.Root value={tab} onValueChange={(v) => setTab(v as Tab)} className="flex flex-col gap-4">
          <Tabs.List aria-label="Model source" className="flex gap-1 rounded-xl bg-muted p-1 text-sm">
            {(
              [
                ['catalog', 'Recommended models'],
                ['custom', 'Custom model'],
              ] as const
            ).map(([key, label]) => (
              <Tabs.Trigger
                key={key}
                value={key}
                className="flex-1 rounded-lg px-3 py-1.5 font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-xs"
              >
                {label}
              </Tabs.Trigger>
            ))}
          </Tabs.List>

            <Tabs.Content value="catalog" className="outline-none">
              {catalog.isPending ? (
                <div aria-busy="true" aria-label="Loading models" className="flex flex-col gap-2">
                  <Skeleton className="h-24 rounded-xl" />
                  <Skeleton className="h-24 rounded-xl" />
                </div>
              ) : catalog.isError ? (
                <ErrorState message={catalog.error.message} onRetry={() => catalog.refetch()} />
              ) : models.length === 0 ? (
                <p className="rounded-xl bg-muted/50 p-4 text-sm text-muted-foreground">No models are available right now. Try a custom model.</p>
              ) : (
                <fieldset className="flex flex-col gap-3">
                  <legend className="sr-only">Base model</legend>
                  {models.map((m) => (
                    <ModelCard key={m.id} model={m} selected={selected?.id === m.id} onSelect={() => setModelId(m.id)} />
                  ))}
                </fieldset>
              )}
              {noChat && (
                <Callout tone="warning" className="mt-3">
                  {selected.display_name} won't open in the playground: it's too big for the chat server. You can still download it and chat with
                  it on your own computer with Ollama.
                  {chatModel && ` Use ${chatModel.display_name} if you want to chat here.`}
                </Callout>
              )}
              {selected && /llama/i.test(selected.license) && (
                <Callout tone="info" className="mt-3">
                  This model uses the Llama license. Show <strong>Built with Llama</strong> whenever you share the result.
                </Callout>
              )}
            </Tabs.Content>
            <Tabs.Content value="custom" className="flex flex-col gap-3 outline-none">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={hfInputId}>Hugging Face model id</Label>
                <div className="flex gap-2">
                  <Input
                    id={hfInputId}
                    placeholder="organisation/model-name"
                    value={hfId}
                    onChange={(e) => {
                      setHfId(e.target.value)
                      setLicenseAck(false)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        runCheck()
                      }
                    }}
                  />
                  <Button type="button" variant="secondary" disabled={!hfId.trim() || check.isPending} onClick={runCheck}>
                    {check.isPending ? 'Checking…' : 'Check model'}
                  </Button>
                </div>
              </div>
              {check.isError && <ErrorState message={check.error.message} />}
              {checked && <ModelCheckResult result={checked} licenseAck={licenseAck} onLicenseAck={setLicenseAck} />}
            </Tabs.Content>
          </Tabs.Root>

          {presets.isPending ? (
            <Skeleton aria-busy="true" aria-label="Loading presets" className="h-24 rounded-xl" />
          ) : presets.isError ? (
            <ErrorState message={presets.error.message} onRetry={() => presets.refetch()} />
          ) : (
            <PresetPicker presets={presets.data} value={preset} onChange={setPreset} minutes={minutes} />
          )}

          <details className="group rounded-xl border p-3.5 text-sm">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-2 font-medium [&::-webkit-details-marker]:hidden">
              <span>Advanced</span>
              <span className="text-caption font-normal text-muted-foreground">Optional · most people can skip this</span>
              <ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" aria-hidden />
            </summary>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`${advancedId}-epochs`}>Epochs</Label>
                <Input
                  id={`${advancedId}-epochs`}
                  type="number"
                  min={1}
                  placeholder="From the preset"
                  value={advanced.epochs}
                  onChange={(e) => setAdvanced({ ...advanced, epochs: e.target.value })}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`${advancedId}-rank`}>LoRA rank</Label>
                <NativeSelect id={`${advancedId}-rank`} value={advanced.loraR} onChange={(e) => setAdvanced({ ...advanced, loraR: e.target.value })}>
                  <option value="">From the preset</option>
                  {RANKS.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </NativeSelect>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`${advancedId}-lr`}>Learning rate</Label>
                <Input
                  id={`${advancedId}-lr`}
                  type="number"
                  step="any"
                  min={0}
                  placeholder="From the preset"
                  value={advanced.learningRate}
                  onChange={(e) => setAdvanced({ ...advanced, learningRate: e.target.value })}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`${advancedId}-seq`}>Max sequence length</Label>
                <Input
                  id={`${advancedId}-seq`}
                  type="number"
                  min={1}
                  placeholder="From the preset"
                  value={advanced.maxSeqLen}
                  onChange={(e) => setAdvanced({ ...advanced, maxSeqLen: e.target.value })}
                />
              </div>
              <p className="text-caption text-muted-foreground sm:col-span-2">
                LoRA rank is how much the adapter can learn (a small file of what your model learned). Leave these empty unless you know you need them.
              </p>
            </div>
          </details>

          {createMessage && (
            <Callout tone="destructive" role="alert">
              <p>{createMessage}</p>
              {fieldErrors.length > 0 && (
                <ul>
                  {fieldErrors.map(([field, msgs]) => (
                    <li key={field}>
                      {field}: {msgs.join(', ')}
                    </li>
                  ))}
                </ul>
              )}
            </Callout>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Not now
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {create.isPending ? 'Creating…' : 'Create training job'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function kaggleHint(status: string | undefined, hoursLeft: number | null, loading: boolean): string {
  if (loading) return 'Checking your Kaggle account…'
  switch (status) {
    case 'ok':
      return hoursLeft === null ? 'Free T4 GPU in your own Kaggle account.' : `Free T4 GPU in your own Kaggle account. ${hoursLeft} GPU hours left this week.`
    case 'unchecked':
      return 'Still checking your Kaggle account. Try again in a moment.'
    case 'invalid':
      return 'Your Kaggle token is not valid. Fix it in Settings.'
    case 'no_gpu_quota':
      return 'No Kaggle GPU hours left this week. Use Colab, or wait for the reset.'
    default:
      return 'Free T4 GPU, no notebook to run.'
  }
}

function BackendOption({
  value,
  checked,
  disabled = false,
  onSelect,
  title,
  hint,
  icon: Icon,
  badge,
  children,
}: {
  value: Backend
  checked: boolean
  disabled?: boolean
  onSelect: () => void
  title: string
  hint: string
  icon: LucideIcon
  badge: string
  children?: ReactNode
}) {
  const id = useId()
  return (
    <div
      className={cn(
        'relative flex flex-col gap-2 rounded-xl border bg-card p-4 transition-colors has-focus-visible:ring-[3px] has-focus-visible:ring-ring/50',
        checked ? 'border-primary bg-accent/40 ring-1 ring-primary' : !disabled && 'hover:border-primary/50',
        disabled && 'bg-muted/40',
      )}
    >
      <input
        id={id}
        type="radio"
        name="backend"
        value={value}
        className="sr-only"
        checked={checked}
        disabled={disabled}
        onChange={onSelect}
      />
      <label
        htmlFor={id}
        className={cn('flex items-start gap-3 pr-7 text-sm after:absolute after:inset-0 after:content-[""]', disabled ? 'cursor-not-allowed' : 'cursor-pointer')}
      >
        <span className={cn('flex size-9 shrink-0 items-center justify-center rounded-lg', checked ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground')}>
          <Icon className="size-4.5" aria-hidden />
        </span>
        <span className="flex min-w-0 flex-col gap-0.5">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-card-title">{title}</span>
            <Badge variant="secondary">{badge}</Badge>
          </span>
          <span className="text-caption text-muted-foreground">{hint}</span>
        </span>
      </label>
      <span
        aria-hidden
        className={cn(
          'absolute top-4 right-4 flex size-5 items-center justify-center rounded-full border',
          checked ? 'border-primary bg-primary text-primary-foreground' : 'bg-background',
        )}
      >
        {checked && <Check className="size-3" />}
      </span>
      {children && <div className="relative z-10 pl-12">{children}</div>}
    </div>
  )
}
