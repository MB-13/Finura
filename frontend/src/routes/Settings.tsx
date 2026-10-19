import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { PageHeader } from '@/components/PageHeader'
import { Section } from '@/components/Section'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { DeleteAccountCard } from '@/features/settings/DeleteAccountCard'
import { NotificationsCard } from '@/features/settings/NotificationsCard'
import { KaggleCard } from '@/features/settings/KaggleCard'
import { ApiKeysSection } from '@/features/settings/ApiKeysSection'
import { useMe, useUpdateMe, type Me } from '@/features/me/api'
import { ApiError } from '@/lib/api/client'
const HEADER = {
  title: 'Settings',
  description: 'Your account, the keys DocTune uses to write training data, and where your models train.',
}
export function Settings() {
  const me = useMe()
  if (me.isPending) {
    return (
      <div className="flex flex-col gap-8">
        <PageHeader {...HEADER} />
        <div aria-busy="true" aria-label="Loading settings" className="flex flex-col gap-8">
          <Skeleton className="h-44 rounded-lg" />
          <Skeleton className="h-72 rounded-lg" />
        </div>
      </div>
    )
  }
  if (me.isError) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader {...HEADER} />
        <ErrorState message={me.error.message} onRetry={() => me.refetch()} />
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-8">
      <PageHeader {...HEADER} />
      <div className="flex flex-col gap-8 [&>section+section]:border-t [&>section+section]:pt-8">
        <Section layout="side" title="Account" description="Your name and the email you sign in with.">
          <AccountCard me={me.data} />
        </Section>
        <Section
          layout="side"
          title="AI provider keys"
          description="DocTune writes your training data with your own free API keys. Connect Groq first; add Gemini to finish faster."
        >
          <ApiKeysSection />
        </Section>
        <Section
          layout="side"
          title="Training compute"
          description="Connect your own free Kaggle account and DocTune trains your model for you."
        >
          <KaggleCard />
        </Section>
        <Section layout="side" title="Notifications" description="Emails are rare and only about your projects.">
          <NotificationsCard me={me.data} />
        </Section>
        <Section layout="side" title="Danger zone" description="Permanent actions. Think twice." danger>
          <DeleteAccountCard />
        </Section>
      </div>
    </div>
  )
}
function AccountCard({ me }: { me: Me }) {
  const update = useUpdateMe()
  const [name, setName] = useState(me.display_name ?? '')
  const fieldError = update.error instanceof ApiError ? update.error.fieldErrors['display_name']?.[0] : undefined
  function save(e: FormEvent) {
    e.preventDefault()
    update.mutate({ display_name: name.trim() || null }, { onSuccess: () => toast.success('Saved') })
  }
  return (
    <div role="region" aria-label="Account">
        <form onSubmit={save} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <span className="text-eyebrow">Email</span>
            <span className="font-mono text-[0.8125rem] break-all">{me.email}</span>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="display_name">Display name</Label>
            <Input
              id="display_name"
              maxLength={80}
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-invalid={Boolean(fieldError)}
            />
            {fieldError && <p className="text-sm text-destructive-muted-foreground">{fieldError}</p>}
          </div>
          <Button type="submit" className="self-start" disabled={update.isPending}>
            {update.isPending ? 'Saving…' : 'Save'}
          </Button>
        </form>
    </div>
  )
}
