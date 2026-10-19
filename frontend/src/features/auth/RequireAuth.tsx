import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'

import { useAuth } from '@/features/auth/auth-context'
import { FullPageSpinner } from '@/components/FullPageSpinner'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth()
  const location = useLocation()

  if (loading) return <FullPageSpinner label="Checking your session…" />
  if (!session) {
    const next = location.pathname + location.search
    return <Navigate to={`/sign-in?next=${encodeURIComponent(next)}`} replace />
  }
  return <>{children}</>
}
