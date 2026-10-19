import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { BookOpen, Clock, KeyRound, Wallet, type LucideIcon } from 'lucide-react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import { StepMarker } from '@/components/StepRail'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { useUpdateMe } from '@/features/me/api'
import { useCreateProject } from '@/features/projects/api'
import { cn } from '@/lib/utils'

const STEPS = ['What to expect', 'Connect a key', 'First project'] as const

function Point({ icon: Icon, children }: { icon: LucideIcon; children: ReactNode }) {
  return (
    <li className="flex gap-3">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
        <Icon className="size-4.5" aria-hidden />
      </div>
      <div className="min-w-0 pt-1">{children}</div>
    </li>
  )
}

export function OnboardingFlow() {
  const [step, setStep] = useState(0)
  const [name, setName] = useState('')
  const update = useUpdateMe()
  const create = useCreateProject()
  const navigate = useNavigate()
  const heading = useRef<HTMLHeadingElement>(null)
  const firstRender = useRef(true)

  // the focused Next / Back button can unmount with the step, so move focus to the new step's heading
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    heading.current?.focus()
  }, [step])

  /** Mark onboarding done, then leave. A failed save must not trap the user, so we leave either way. */
  function finish(to: string) {
    update.mutate(
      { onboarding_done: true },
      {
        onError: (err) => toast.error(`Could not save your progress: ${err.message}`),
        onSettled: () => void navigate(to, { replace: true, state: { skipOnboarding: true } }),
      },
    )
  }

  function createProject(e: FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    create.mutate(trimmed, { onSuccess: (project) => finish(`/projects/${project.id}`) })
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
      <PageHeader title="Welcome to DocTune" description="Three quick steps to get set up. You can skip this and come back any time." />

      <div className="flex flex-col gap-3">
        <ol aria-label="Onboarding steps" className="hidden gap-2 sm:flex">
          {STEPS.map((label, i) => {
            const state = i < step ? 'done' : i === step ? 'active' : 'todo'
            return (
              <li
                key={label}
                aria-current={i === step ? 'step' : undefined}
                className={cn(
                  'flex flex-1 items-center gap-2 rounded-lg border px-3 py-2 text-caption',
                  i === step ? 'border-primary/40 bg-accent font-medium text-accent-foreground' : 'bg-card text-muted-foreground',
                )}
              >
                <StepMarker state={state} n={i + 1} size="sm" />
                <span className="truncate">
                  {label}
                  {state === 'done' && <span className="sr-only"> (done)</span>}
                </span>
              </li>
            )
          })}
        </ol>
        <div className="flex flex-col gap-2 sm:hidden">
          <div className="text-eyebrow tabular-nums" aria-live="polite">
            Step {step + 1} of {STEPS.length}: {STEPS[step]}
          </div>
          <Progress value={((step + 1) / STEPS.length) * 100} aria-label="Onboarding progress" />
        </div>
      </div>

      <Card>
        {step === 0 && (
          <>
            <CardHeader>
              <CardTitle ref={heading} tabIndex={-1} className="text-section-title outline-none">What to expect</CardTitle>
              <CardDescription>DocTune turns your documents into a model that answers in your style.</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="flex flex-col gap-5 text-sm">
                <Point icon={BookOpen}>
                  <p>
                    <strong>Fine-tuning teaches style, not facts.</strong> Your model learns how to answer. The facts come from your documents, which the
                    playground looks up as it answers.
                  </p>
                </Point>
                <Point icon={Wallet}>
                  <p>
                    <strong>It is free.</strong> You bring your own free AI provider key to write the training data, and your own free Google Colab GPU to train.
                    DocTune never charges you.
                  </p>
                </Point>
                <Point icon={Clock}>
                  <p>Expect it to take a while: writing the data can take a day or more on free keys, and training takes about an hour.</p>
                </Point>
              </ul>
            </CardContent>
          </>
        )}
        {step === 1 && (
          <>
            <CardHeader>
              <CardTitle ref={heading} tabIndex={-1} className="text-section-title outline-none">Connect an AI key</CardTitle>
              <CardDescription>DocTune uses your own key to write the training examples from your documents.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4 text-sm">
              <ul>
                <Point icon={KeyRound}>
                  <p>A free Groq key is enough to start. Adding a Gemini key later makes it faster.</p>
                </Point>
              </ul>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                <Button asChild variant="outline">
                  <Link to="/settings">Open settings to add a key</Link>
                </Button>
                <Link to="/docs/groq-key" className="font-medium text-primary underline underline-offset-4">
                  How to get a free Groq key
                </Link>
              </div>
              <p className="text-caption text-muted-foreground">You can also do this later, right before you generate your dataset.</p>
            </CardContent>
          </>
        )}
        {step === 2 && (
          <>
            <CardHeader>
              <CardTitle ref={heading} tabIndex={-1} className="text-section-title outline-none">Create your first project</CardTitle>
              <CardDescription>A project holds your documents and the model you train from them.</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={createProject} className="flex flex-col gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="first-project">Project name</Label>
                  <Input id="first-project" value={name} maxLength={120} autoComplete="off" onChange={(e) => setName(e.target.value)} />
                  <p className="text-caption text-muted-foreground">For example, "Support answers" or "Product manual". You can rename it later.</p>
                </div>
                {create.isError && (
                  <p role="alert" className="text-sm font-medium text-destructive-muted-foreground">
                    {create.error.message}
                  </p>
                )}
                <Button type="submit" className="self-start" disabled={!name.trim() || create.isPending || update.isPending}>
                  {create.isPending || update.isPending ? 'Creating…' : 'Create project'}
                </Button>
              </form>
            </CardContent>
          </>
        )}
        <CardFooter className="justify-between gap-3 border-t">
          <Button variant="ghost" disabled={update.isPending} onClick={() => finish('/projects')}>
            Skip for now
          </Button>
          <div className="flex gap-2">
            {step > 0 && (
              <Button variant="outline" onClick={() => setStep(step - 1)}>
                Back
              </Button>
            )}
            {step < STEPS.length - 1 && <Button onClick={() => setStep(step + 1)}>Next</Button>}
          </div>
        </CardFooter>
      </Card>
    </div>
  )
}
