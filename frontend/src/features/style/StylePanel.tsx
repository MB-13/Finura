import { ChevronDown, ChevronRight, KeyRound } from 'lucide-react'
import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Callout } from '@/components/Callout'
import { NativeSelect } from '@/components/NativeSelect'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import type { Project } from '@/features/projects/api'
import { useKeys, useProviders } from '@/features/settings/api'
import { usePatchProject, useSaveStyle, useStartPreview, type StyleIn, type StyleTemplate } from '@/features/style/api'
import { DatasetFormatPicker } from '@/features/style/DatasetFormatPicker'
import { ExamplesEditor } from '@/features/style/ExamplesEditor'
import {
  cleanStyle,
  errorsFor,
  FORMATS,
  LANGUAGES,
  LENGTHS,
  MAX_DESCRIPTION,
  MAX_TARGET,
  MIN_TARGET,
  toStyleIn,
  TONES,
  validateStyle,
  type FieldErrors,
} from '@/features/style/style-form'
import { TemplatePicker } from '@/features/style/TemplatePicker'
import { ApiError } from '@/lib/api/client'
import { cn } from '@/lib/utils'

const label = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

type Props = {
  project: Project
  /** Changing this number moves focus to the description (used by "Tweak style"). */
  focusSignal?: number
}

export function StylePanel({ project, focusSignal = 0 }: Props) {
  const keys = useKeys()
  const providers = useProviders()
  const savePatch = usePatchProject(project.id)
  const saveStyle = useSaveStyle(project.id)
  const startPreview = useStartPreview(project.id)

  const [form, setForm] = useState<StyleIn>(() => toStyleIn(project.style))
  const [targetPairs, setTargetPairs] = useState(String(project.target_pairs))
  const [provider, setProvider] = useState(project.gen_provider ?? '')
  const [model, setModel] = useState(project.gen_model ?? '')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [warnings, setWarnings] = useState(project.style?.warnings ?? [])

  const descriptionRef = useRef<HTMLTextAreaElement>(null)
  const descId = useId()
  const advancedId = useId()

  useEffect(() => {
    if (focusSignal === 0) return
    descriptionRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
    descriptionRef.current?.focus()
  }, [focusSignal])

  const set = <K extends keyof StyleIn>(key: K, value: StyleIn[K]) => setForm((f) => ({ ...f, [key]: value }))

  function applyTemplate(t: StyleTemplate) {
    // a template sets the answer style, not the shape of the dataset
    setForm((f) => ({ ...toStyleIn(t.defaults), template_key: t.key, dataset_format: f.dataset_format }))
    setErrors({})
  }

  const usableKeys = (keys.data ?? []).filter((k) => k.status === 'valid' || k.status === 'unverified').sort((a, b) => a.priority - b.priority)
  const keysLoaded = keys.isSuccess
  const noKey = keysLoaded && usableKeys.length === 0
  const providerInfo = providers.data?.find((p) => p.provider === provider)
  const busy = saveStyle.isPending || startPreview.isPending || savePatch.isPending

  async function submit(e: FormEvent) {
    e.preventDefault()
    setFormError(null)
    const local = validateStyle(form)
    const target = Number(targetPairs)
    if (!Number.isInteger(target) || target < MIN_TARGET || target > MAX_TARGET) {
      local['target_pairs'] = [`Choose between ${MIN_TARGET} and ${MAX_TARGET} pairs.`]
      setShowAdvanced(true)
    }
    setErrors(local)
    if (Object.keys(local).length > 0) return

    try {
      const patch: Parameters<typeof savePatch.mutateAsync>[0] = {}
      if (target !== project.target_pairs) patch.target_pairs = target
      if (provider && provider !== project.gen_provider) patch.gen_provider = provider as 'groq' | 'gemini' | 'cerebras'
      if (model && model !== project.gen_model) patch.gen_model = model
      if (Object.keys(patch).length > 0) await savePatch.mutateAsync(patch)
      const saved = await saveStyle.mutateAsync(cleanStyle(form))
      setWarnings(saved.warnings ?? [])
      await startPreview.mutateAsync({})
      toast.success('Generating a preview…')
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors)
        const hasFields = Object.keys(err.fieldErrors).length > 0
        setFormError(hasFields ? 'Please fix the highlighted fields.' : err.message)
        if (hasFields && ['target_pairs', 'gen_provider', 'gen_model'].some((k) => k in err.fieldErrors)) setShowAdvanced(true)
      } else {
        setFormError(err instanceof Error ? err.message : 'Something went wrong')
      }
    }
  }

  const known = ['dataset_format', 'description', 'tone', 'length', 'format', 'language', 'examples', 'system_prompt_in_data', 'target_pairs', 'gen_provider', 'gen_model']
  const otherErrors = Object.entries(errors).filter(([k]) => !known.some((n) => k === n || k.startsWith(`${n}.`) || k.startsWith(`${n}[`)))
  const descError = errorsFor(errors, 'description')
  const AdvancedChevron = showAdvanced ? ChevronDown : ChevronRight

  return (
    <Card>
      <CardHeader>
        <CardTitle>Describe how your model should answer</CardTitle>
        <CardDescription>
          Pick a starting point, describe the style in your own words and show a few examples. We&apos;ll write a small
          sample first so you can check it before the full run. Fine-tuning teaches your model <em>how</em> to answer; the
          facts still come from your documents.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} noValidate className="flex flex-col gap-8" aria-label="Style setup">
          <FormSection
            title="Choose the dataset format"
            description="The shape of every training example. It decides what we generate and what your model learns to do."
          >
            <DatasetFormatPicker value={form.dataset_format ?? 'qa_chat'} onChange={(v) => set('dataset_format', v)} disabled={busy} />
            <FieldError message={errorsFor(errors, 'dataset_format')} />
          </FormSection>

          <FormSection
            title="Start from a template"
            description="Optional. Fills in the fields below, and you can change anything."
            className="border-t pt-8"
          >
            <TemplatePicker selectedKey={form.template_key} onPick={applyTemplate} disabled={busy} />
          </FormSection>

          <FormSection title="Describe the style" className="border-t pt-8">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={descId}>Style description</Label>
              <Textarea
                id={descId}
                ref={descriptionRef}
                rows={4}
                maxLength={MAX_DESCRIPTION}
                placeholder="e.g. A friendly support agent who answers briefly, cites the manual section and never guesses."
                value={form.description}
                onChange={(e) => set('description', e.target.value)}
                aria-invalid={Boolean(descError)}
                aria-describedby={descError ? `${descId}-error` : undefined}
              />
              <div className="flex justify-between gap-3 text-caption text-muted-foreground">
                <span>Who is answering, who is asking, and how should answers sound?</span>
                <span className="shrink-0 tabular-nums">
                  {form.description.length}/{MAX_DESCRIPTION}
                </span>
              </div>
              {descError && (
                <p id={`${descId}-error`} role="alert" className="text-sm text-destructive">
                  {descError}
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <SelectField id="style-tone" label="Tone" value={form.tone} onChange={(v) => set('tone', v as StyleIn['tone'])} error={errorsFor(errors, 'tone')}>
                {TONES.map((t) => (
                  <option key={t} value={t}>
                    {label(t)}
                  </option>
                ))}
              </SelectField>
              <SelectField id="style-length" label="Length" value={form.length} onChange={(v) => set('length', v as StyleIn['length'])} error={errorsFor(errors, 'length')}>
                {LENGTHS.map((t) => (
                  <option key={t} value={t}>
                    {label(t)}
                  </option>
                ))}
              </SelectField>
              <SelectField id="style-format" label="Format" value={form.format} onChange={(v) => set('format', v as StyleIn['format'])} error={errorsFor(errors, 'format')}>
                {FORMATS.map((t) => (
                  <option key={t} value={t}>
                    {label(t)}
                  </option>
                ))}
              </SelectField>
              <SelectField id="style-language" label="Language" value={form.language} onChange={(v) => set('language', v)} error={errorsFor(errors, 'language')}>
                {!(form.language in LANGUAGES) && <option value={form.language}>{form.language}</option>}
                {Object.entries(LANGUAGES).map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </SelectField>
            </div>
          </FormSection>

          <div className="border-t pt-8">
            <ExamplesEditor examples={form.examples} onChange={(v) => set('examples', v)} error={errorsFor(errors, 'examples')} disabled={busy} />
          </div>

          <div className="flex flex-col gap-3 border-t pt-6">
            <button
              type="button"
              aria-expanded={showAdvanced}
              aria-controls={advancedId}
              onClick={() => setShowAdvanced((v) => !v)}
              className="flex items-center gap-1 self-start rounded-md text-sm font-medium outline-none hover:text-primary focus-visible:ring-[3px] focus-visible:ring-ring/50"
            >
              <AdvancedChevron className="size-4" aria-hidden /> Advanced
            </button>
            <div id={advancedId} hidden={!showAdvanced} className="flex flex-col gap-4 border-l-2 pl-4">
              <div className="flex items-start gap-2">
                <input
                  id="style-system-prompt"
                  type="checkbox"
                  className="mt-1 size-4 accent-primary"
                  checked={form.system_prompt_in_data}
                  onChange={(e) => set('system_prompt_in_data', e.target.checked)}
                />
                <Label htmlFor="style-system-prompt" className="text-sm leading-snug font-normal">
                  Also add the description as a system prompt in every training example
                </Label>
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="target-pairs">Dataset size (pairs)</Label>
                  <Input
                    id="target-pairs"
                    type="number"
                    inputMode="numeric"
                    min={MIN_TARGET}
                    max={MAX_TARGET}
                    value={targetPairs}
                    onChange={(e) => setTargetPairs(e.target.value)}
                    aria-invalid={Boolean(errorsFor(errors, 'target_pairs'))}
                  />
                  <p className="text-caption text-muted-foreground">
                    {MIN_TARGET} to {MAX_TARGET}. More pairs take longer to generate.
                  </p>
                  <FieldError message={errorsFor(errors, 'target_pairs')} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="gen-provider">Provider</Label>
                  <NativeSelect
                    id="gen-provider"
                    value={provider}
                    onChange={(e) => {
                      setProvider(e.target.value)
                      setModel('')
                    }}
                  >
                    <option value="">Automatic</option>
                    {usableKeys.map((k) => (
                      <option key={k.provider} value={k.provider}>
                        {providers.data?.find((p) => p.provider === k.provider)?.name ?? label(k.provider)}
                      </option>
                    ))}
                  </NativeSelect>
                  <FieldError message={errorsFor(errors, 'gen_provider')} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="gen-model">Model</Label>
                  <NativeSelect id="gen-model" value={model} onChange={(e) => setModel(e.target.value)} disabled={!providerInfo}>
                    <option value="">Automatic</option>
                    {providerInfo?.models.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.id}
                      </option>
                    ))}
                  </NativeSelect>
                  <FieldError message={errorsFor(errors, 'gen_model')} />
                </div>
              </div>
            </div>
          </div>

          {warnings.length > 0 && (
            <Callout tone="warning" role="status" title="Suggestions">
              <ul className="list-inside list-disc">
                {warnings.map((w) => (
                  <li key={w.code}>{w.message}</li>
                ))}
              </ul>
            </Callout>
          )}

          {noKey && (
            <Callout
              tone="info"
              icon={KeyRound}
              title="Connect an AI provider key first"
              action={
                <Link to="/settings" className="text-sm font-medium text-primary underline underline-offset-4">
                  Add a key in Settings
                </Link>
              }
            >
              DocTune writes your dataset with your own free API key (Groq is the quickest to set up).
            </Callout>
          )}

          {(formError || otherErrors.length > 0) && (
            <Callout tone="destructive" role="alert">
              {formError && <p>{formError}</p>}
              {otherErrors.map(([field, msgs]) => (
                <p key={field}>
                  {field}: {msgs[0]}
                </p>
              ))}
            </Callout>
          )}

          <div className="flex flex-col gap-3 border-t pt-6 sm:flex-row sm:items-center">
            <Button type="submit" disabled={busy || noKey} className="sm:shrink-0">
              {busy ? 'Working…' : 'Save & generate preview'}
            </Button>
            <p className="text-caption text-muted-foreground">Creates about 8 sample pairs. Nothing big runs until you approve it.</p>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

function FormSection({ title, description, className, children }: { title: string; description?: string; className?: string; children: ReactNode }) {
  return (
    <section className={cn('flex flex-col gap-4', className)}>
      <div className="flex flex-col gap-0.5">
        <h3 className="text-card-title">{title}</h3>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      {children}
    </section>
  )
}

function FieldError({ message }: { message: string | undefined }) {
  return message ? (
    <p role="alert" className="text-sm text-destructive">
      {message}
    </p>
  ) : null
}

function SelectField({
  id,
  label: text,
  value,
  onChange,
  error,
  children,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  error?: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{text}</Label>
      <NativeSelect id={id} value={value} onChange={(e) => onChange(e.target.value)} aria-invalid={Boolean(error)}>
        {children}
      </NativeSelect>
      <FieldError message={error} />
    </div>
  )
}
