import { Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router'

import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/auth-context'
import { AuthShell } from '@/features/auth/AuthShell'
import { safeNext } from '@/lib/redirect'

/** Supabase finishes the sign-in from the URL (PKCE code); we wait for the session, then continue. */
export function AuthCallback() {
  const { session } = useAuth()
  const [params] = useSearchParams()
  const [timedOut, setTimedOut] = useState(false)
  const urlError = params.get('error_description') ?? params.get('error')

  useEffect(() => {
    const t = window.setTimeout(() => setTimedOut(true), 10_000)
    return () => window.clearTimeout(t)
  }, [])

  if (session) return <Navigate to={safeNext(params.get('next'))} replace />
  if (urlError || timedOut) {
    return (
      <AuthShell>
        <div className="flex flex-col gap-4">
          <ErrorState title="Sign-in didn't complete" message={urlError ?? 'The sign-in link may have expired.'} />
          <Button asChild>
            <Link to="/sign-in">Back to sign in</Link>
          </Button>
        </div>
      </AuthShell>
    )
  }
  return (
    <AuthShell>
      <div role="status" className="flex flex-col items-center gap-3 py-12 text-center">
        <Loader2 className="size-6 animate-spin text-primary motion-reduce:animate-none" aria-hidden />
        <div className="text-card-title">Signing you in…</div>
        <p className="text-sm text-muted-foreground">This only takes a moment.</p>
      </div>
    </AuthShell>
  )
}
