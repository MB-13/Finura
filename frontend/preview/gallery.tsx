import { FileText, FolderOpen, Gauge, Plus, Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'

import { AppFrame } from '@/components/AppFrame'
import { GuideJoint, GuideRails } from '@/components/marketing/GuideRails'
import { StatRow } from '@/components/StatRow'
import { Callout } from '@/components/Callout'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { KeyValue } from '@/components/KeyValue'
import { Logo } from '@/components/Logo'
import { NativeSelect } from '@/components/NativeSelect'
import { PageHeader } from '@/components/PageHeader'
import { Section } from '@/components/Section'
import { Stat } from '@/components/Stat'
import { StatusBadge } from '@/components/StatusBadge'
import { ThemeToggle } from '@/components/theme/ThemeToggle'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { statusMeta } from '@/components/status-meta'
import type { ProjectStatus } from '@/features/projects/api'
import { ProjectStepper } from '@/features/projects/ProjectStepper'

const swatches = ['background', 'card', 'muted', 'accent', 'primary', 'secondary', 'border', 'ring', 'success', 'warning', 'info', 'destructive']
const charts = ['chart-1', 'chart-2', 'chart-3', 'chart-4', 'chart-5']

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Section title={title} as="h2">
      {children}
    </Section>
  )
}

export function Gallery() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-12 px-4 py-8 sm:px-6">
      <div className="flex items-center justify-between">
        <Logo />
        <ThemeToggle />
      </div>
      <PageHeader
        back={{ to: '/projects', label: 'Back to projects' }}
        title="Design system gallery"
        badge={<StatusBadge status="training" />}
        description="Everything the pages are built from. Light and dark are both driven by tokens in src/index.css."
        actions={
          <>
            <Button variant="outline">Secondary action</Button>
            <Button>
              <Plus aria-hidden /> Primary action
            </Button>
          </>
        }
      />

      <Block title="Colour tokens">
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          {swatches.map((name) => (
            <div key={name} className="flex flex-col gap-1.5">
              <div className="h-12 rounded-lg border shadow-xs" style={{ background: `var(--${name})` }} />
              <code className="text-xs text-muted-foreground">{name}</code>
            </div>
          ))}
          {charts.map((name) => (
            <div key={name} className="flex flex-col gap-1.5">
              <div className="h-12 rounded-lg border shadow-xs" style={{ background: `var(--${name})` }} />
              <code className="text-xs text-muted-foreground">{name}</code>
            </div>
          ))}
        </div>
      </Block>

      <Block title="Typography">
        <div className="flex flex-col gap-3 rounded-xl border bg-card p-5">
          <div className="text-display">Your documents, your model</div>
          <div className="text-display-sm text-muted-foreground">Display small headline</div>
          <div className="text-page-title">Page title - Fine-tune a model on your documents</div>
          <div className="text-section-title">Section title - Choose a base model</div>
          <div className="text-card-title">Card title - Customer support bot</div>
          <p className="text-body">Body - DocTune turns your documents into training examples so the model learns your style. Facts still come from search in the playground.</p>
          <p className="text-caption text-muted-foreground">Caption - Last saved 12 s ago</p>
          <p className="text-eyebrow">Eyebrow label (text-eyebrow / text-overline)</p>
          <p className="text-metric text-3xl">42% <span className="text-xl text-success-muted-foreground">+2.5</span> 940 pairs</p>
          <p className="text-sm tabular-nums">Tabular numbers: 1,234.56 / 0,000.00 / 111.11 <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.8125rem]">dtj_ab12cd34</code></p>
        </div>
      </Block>

      <Block title="Buttons and badges">
        <div className="flex flex-wrap items-center gap-3">
          <Button>Default</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="link">Link</Button>
          <Button variant="destructive">Delete</Button>
          <Button size="sm">Small</Button>
          <Button size="lg">Large</Button>
          <Button disabled>Disabled</Button>
          <Button size="icon" variant="outline" aria-label="Sparkle">
            <Sparkles aria-hidden />
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge>Default</Badge>
          <Badge variant="secondary">Secondary</Badge>
          <Badge variant="outline">Outline</Badge>
          <Badge variant="success">Fits free T4</Badge>
          <Badge variant="warning">Check license</Badge>
          <Badge variant="info">Recommended</Badge>
          <Badge variant="destructive">Blocked</Badge>
        </div>
        <div className="flex flex-wrap gap-2">
          {(Object.keys(statusMeta) as ProjectStatus[]).map((s) => (
            <StatusBadge key={s} status={s} />
          ))}
        </div>
      </Block>

      <Block title="Form controls">
        <div className="grid gap-4 sm:grid-cols-2">
          <Input placeholder="Project name" aria-label="Project name" />
          <NativeSelect aria-label="Tone">
            <option>Friendly</option>
            <option>Formal</option>
          </NativeSelect>
          <Input aria-label="Invalid" aria-invalid defaultValue="Something wrong" />
          <Input aria-label="Disabled" disabled placeholder="Disabled" />
          <Textarea className="sm:col-span-2" aria-label="Description" placeholder="Describe how the model should answer..." />
        </div>
      </Block>

      <Block title="StatRow, AppFrame, marketing backgrounds">
        <Card>
          <CardContent>
            <StatRow
              items={[
                { label: 'Pairs kept', value: '940', hint: 'of 1,000 target', icon: FileText },
                { label: 'Train / eval', value: '846 / 94' },
                { label: 'Avg quality', value: '4.3', hint: 'out of 5', icon: Gauge },
                { label: 'Documents', value: '3' },
                { label: 'Cost', value: '$0' },
              ]}
            />
          </CardContent>
        </Card>
        <div className="relative overflow-hidden rounded-2xl border">
          <div aria-hidden className="bg-glow pointer-events-none absolute inset-0" />
          <div aria-hidden className="bg-grid pointer-events-none absolute inset-0" />
          <GuideJoint />
          <GuideRails className="px-6 pt-10">
            <AppFrame title="Dataset review" fade bodyClassName="h-40 p-4">
              <p className="text-body">Product window content goes here.</p>
              <p className="mt-2 text-caption text-muted-foreground">Cropped by a fade at the bottom.</p>
            </AppFrame>
          </GuideRails>
          <GuideJoint />
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Pairs kept" value="940" hint="of 1,000 target" icon={FileText} />
          <Stat label="Train / eval" value="846 / 94" />
          <Stat label="Avg quality" value="4.3" hint="out of 5" icon={Gauge} />
          <Stat label="Documents" value="3" />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Qwen3.5 4B</CardTitle>
              <CardDescription>Best quality on a free T4.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <div className="flex gap-2">
                <Badge variant="success">Fits free T4</Badge>
                <Badge variant="outline">Apache 2.0</Badge>
              </div>
              <Progress value={62} aria-label="Demo progress" />
            </CardContent>
            <CardFooter className="gap-2">
              <Button size="sm">Choose model</Button>
              <Button size="sm" variant="ghost">
                Details
              </Button>
            </CardFooter>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Job details</CardTitle>
            </CardHeader>
            <CardContent>
              <KeyValue
                items={[
                  { label: 'Base model', value: 'unsloth/Qwen3.5-4B', mono: true },
                  { label: 'Preset', value: 'Balanced' },
                  { label: 'Steps', value: '340 / 800' },
                  { label: 'Last heartbeat', value: '12 s ago' },
                ]}
              />
            </CardContent>
          </Card>
        </div>
      </Block>

      <Block title="Callouts">
        <div className="grid gap-3 md:grid-cols-2">
          <Callout tone="info" title="Fine-tuning teaches style">Facts come from search in the playground.</Callout>
          <Callout tone="success" title="Dataset approved">846 train and 94 eval examples are ready.</Callout>
          <Callout tone="warning" title="Progress is saved" action={<Button size="sm" variant="outline">Open notebook again</Button>}>
            Your Colab session ended. Reopen the notebook to continue from 42%.
          </Callout>
          <Callout tone="destructive" title="Could not read a document">scan.pdf looks password-protected.</Callout>
        </div>
      </Block>

      <Block title="States">
        <div className="grid gap-4 md:grid-cols-2">
          <EmptyState
            icon={FolderOpen}
            title="No projects yet"
            description="Create a project, upload your documents and DocTune will turn them into a fine-tuned model."
            action={
              <Button>
                <Plus aria-hidden /> New project
              </Button>
            }
          />
          <div className="flex flex-col gap-4">
            <ErrorState message="The server took too long to answer." onRetry={() => {}} />
            <div className="flex flex-col gap-2 rounded-xl border bg-card p-4">
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-4/5" />
            </div>
          </div>
        </div>
      </Block>

      <Block title="Project stepper">
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {(['uploaded', 'awaiting_style', 'training', 'ready'] as ProjectStatus[]).map((s) => (
            <div key={s} className="flex flex-col gap-2">
              <code className="text-xs text-muted-foreground">{s}</code>
              <ProjectStepper status={s} className="lg:static" />
            </div>
          ))}
        </div>
      </Block>
    </div>
  )
}
