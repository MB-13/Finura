import { useEffect, useState, type FormEvent } from 'react'
import { Loader2 } from 'lucide-react'
import { Link, Navigate, useSearchParams } from 'react-router'

import { Callout } from '@/components/Callout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/features/auth/auth-context'
import { AuthShell } from '@/features/auth/AuthShell'
import { DevPasswordSignIn } from '@/features/auth/DevPasswordSignIn'
import { friendlyAuthError, RESEND_COOLDOWN } from '@/features/auth/sign-in'
import { safeNext } from '@/lib/redirect'
import { getSupabase } from '@/lib/supabase'

type Step = { kind: 'email' } | { kind: 'code' }
type Busy = 'idle' | 'sending' | 'verifying'

export function SignIn() {
  const { session, configured } = useAuth()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [step, setStep] = useState<Step>({ kind: 'email' })
  const [busy, setBusy] = useState<Busy>('idle')
  const [error, setError] = useState<string | null>(null)
  const [cooldown, setCooldown] = useState(0)

  useEffect(() => {
    if (cooldown <= 0) return
    const t = window.setTimeout(() => setCooldown((c) => c - 1), 1000)
    return () => window.clearTimeout(t)
  }, [cooldown])

  if (session) return <Navigate to={next} replace />

  const redirectTo = `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`

  async function sendCode() {
    setBusy('sending')
    setError(null)
    // the email contains a 6-digit code (and a link as a fallback)
    const { error: err } = await getSupabase().auth.signInWithOtp({
      email,
      options: { emailRedirectTo: redirectTo },
    })
    setBusy('idle')
    if (err) {
      setError(friendlyAuthError(err.message))
      return
    }
    setCode('')
    setStep({ kind: 'code' })
    setCooldown(RESEND_COOLDOWN)
  }

  async function onSendSubmit(e: FormEvent) {
    e.preventDefault()
    await sendCode()
  }

  async function onVerifySubmit(e: FormEvent) {
    e.preventDefault()
    setBusy('verifying')
    setError(null)
    const token = code.replace(/\s/g, '')
    const auth = getSupabase().auth
    // existing users get a "magic link" email, brand-new users a "confirm signup" one; try both
    let { error: err } = await auth.verifyOtp({ email, token, type: 'email' })
    if (err) ({ error: err } = await auth.verifyOtp({ email, token, type: 'signup' }))
    setBusy('idle')
    if (err) setError(friendlyAuthError(err.message))
    // on success AuthProvider receives the session and the <Navigate> above takes over
  }

  async function oauth(provider: 'github' | 'google') {
    setError(null)
    const { error: err } = await getSupabase().auth.signInWithOAuth({
      provider,
      options: { redirectTo },
    })
    if (err) setError(friendlyAuthError(err.message))
  }

  const codeValid = /^\d{6,10}$/.test(code.replace(/\s/g, ''))

  const sending = busy === 'sending'
  const linkBtn =
    'rounded-sm text-sm font-medium text-primary underline-offset-4 hover:underline disabled:text-muted-foreground disabled:no-underline'

  return (
    <AuthShell>
      <div className="flex w-full flex-col gap-6">
        <div className="flex flex-col gap-2">
          <h1 className="text-3xl leading-9 font-[650] tracking-[-0.03em]">{step.kind === 'email' ? 'Sign in to DocTune' : 'Check your email'}</h1>
          <p className="text-body break-words text-muted-foreground [overflow-wrap:anywhere]">
            {step.kind === 'email' ? "We'll email you a 6-digit code. No password needed." : `Enter the code we sent to ${email}.`}
          </p>
        </div>
        <div>
          {!configured ? (
            <Callout tone="destructive" role="alert" title="Sign-in isn't set up yet">
              Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in frontend/.env, then reload.
            </Callout>
          ) : (
            <div className="flex flex-col gap-4">
              {step.kind === 'email' ? (
                <form onSubmit={onSendSubmit} className="flex flex-col gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="email">Email</Label>
                    <Input
                      id="email"
                      type="email"
                      autoComplete="email"
                      placeholder="you@example.com"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                    />
                  </div>
                  <Button type="submit" disabled={busy !== 'idle'}>
                    {sending && <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden />}
                    {sending ? 'Sending…' : 'Email me a code'}
                  </Button>
                </form>
              ) : (
                <form onSubmit={onVerifySubmit} className="flex flex-col gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="code">Sign-in code</Label>
                    <Input
                      id="code"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      pattern="[0-9 ]*"
                      maxLength={12}
                      autoFocus
                      placeholder="123456"
                      className="h-11 text-center font-mono text-lg tracking-[0.4em]"
                      value={code}
                      onChange={(e) => setCode(e.target.value.replace(/[^\d ]/g, ''))}
                    />
                    <p className="text-caption text-muted-foreground">
                      Can't find it? Check spam. Only the newest email works. You can also click the link in the email.
                    </p>
                  </div>
                  <Button type="submit" disabled={busy !== 'idle' || !codeValid}>
                    {busy === 'verifying' && <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden />}
                    {busy === 'verifying' ? 'Checking…' : 'Sign in'}
                  </Button>
                  <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
                    <button type="button" className={linkBtn} disabled={cooldown > 0 || busy !== 'idle'} onClick={sendCode}>
                      {cooldown > 0 ? `Send a new code in ${cooldown}s` : 'Send a new code'}
                    </button>
                    <button
                      type="button"
                      className={linkBtn}
                      onClick={() => {
                        setStep({ kind: 'email' })
                        setError(null)
                      }}
                    >
                      Use a different email
                    </button>
                  </div>
                </form>
              )}
              <div className="flex items-center gap-3 text-caption text-muted-foreground" aria-hidden>
                <span className="h-px flex-1 bg-border" /> or <span className="h-px flex-1 bg-border" />
              </div>
              <div className="grid gap-2">
                <Button variant="outline" onClick={() => oauth('github')}>
                  Continue with GitHub
                </Button>
                <Button variant="outline" onClick={() => oauth('google')}>
                  Continue with Google
                </Button>
              </div>
              {import.meta.env.DEV && (
                <details className="group rounded-md text-caption text-muted-foreground">
                  <summary className="cursor-pointer list-none rounded-sm underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden">
                    Developer sign-in
                  </summary>
                  <div className="mt-3">
                    <DevPasswordSignIn />
                  </div>
                </details>
              )}
              {error && (
                <Callout tone="destructive" role="alert">
                  {error}
                </Callout>
              )}
            </div>
          )}
        </div>
      </div>
      <p className="mt-6 text-caption text-muted-foreground">
        By continuing you agree to the{' '}
        <Link to="/terms" className="underline underline-offset-4 hover:text-foreground">
          Terms
        </Link>{' '}
        and{' '}
        <Link to="/privacy" className="underline underline-offset-4 hover:text-foreground">
          Privacy notice
        </Link>
        .
      </p>
    </AuthShell>
  )
}
