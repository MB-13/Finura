import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { friendlyPasswordError, PASSWORD_MIN } from '@/features/auth/sign-in'
import { getSupabase } from '@/lib/supabase'

type Mode = 'sign-in' | 'sign-up'

/**
 * Email + password sign-in for LOCAL TESTING ONLY. Rendered only on the Vite dev server
 * (import.meta.env.DEV), so production builds never contain it in the UI. Needs "Confirm email"
 * turned off in Supabase (Authentication → Sign In / Providers → Email) so no email is sent.
 */
export function DevPasswordSignIn() {
  const [mode, setMode] = useState<Mode>('sign-in')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ kind: 'error' | 'info'; text: string } | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setMessage(null)
    const auth = getSupabase().auth
    if (mode === 'sign-in') {
      const { error } = await auth.signInWithPassword({ email, password })
      if (error) setMessage({ kind: 'error', text: friendlyPasswordError(error.message) })
    } else {
      const { data, error } = await auth.signUp({ email, password })
      if (error) setMessage({ kind: 'error', text: friendlyPasswordError(error.message) })
      else if (!data.session) {
        setMessage({
          kind: 'info',
          text: 'Account created, but Supabase still wants an email confirmation. Turn off "Confirm email" in '
            + 'Supabase (Authentication → Sign In / Providers → Email), delete this user under Authentication → '
            + 'Users, and create it again.',
        })
      }
    }
    // on success AuthProvider receives the session and the sign-in page redirects
    setBusy(false)
  }

  return (
    <section aria-labelledby="dev-login" className="flex flex-col gap-3 rounded-lg border border-dashed bg-muted/40 p-3">
      <div>
        <h2 id="dev-login" className="text-card-title">
          Password sign-in (local testing only)
        </h2>
        <p className="text-caption text-muted-foreground">Only shown on the development server. Sends no email.</p>
      </div>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="dev-email">Test account email</Label>
          <Input
            id="dev-email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="dev-password">Password</Label>
          <Input
            id="dev-password"
            type="password"
            autoComplete={mode === 'sign-in' ? 'current-password' : 'new-password'}
            required
            minLength={PASSWORD_MIN}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <Button type="submit" variant="secondary" disabled={busy}>
          {busy ? 'Please wait…' : mode === 'sign-in' ? 'Sign in with password' : 'Create account'}
        </Button>
      </form>
      <button
        type="button"
        className="self-start rounded-sm text-sm font-medium text-primary underline underline-offset-4"
        onClick={() => {
          setMode(mode === 'sign-in' ? 'sign-up' : 'sign-in')
          setMessage(null)
        }}
      >
        {mode === 'sign-in' ? 'No account yet? Create one' : 'Already have an account? Sign in'}
      </button>
      {message && (
        <p role={message.kind === 'error' ? 'alert' : 'status'} className={message.kind === 'error' ? 'text-sm font-medium text-destructive-muted-foreground' : 'text-sm'}>
          {message.text}
        </p>
      )}
    </section>
  )
}
