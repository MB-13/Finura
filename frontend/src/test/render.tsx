import type { Session } from '@supabase/supabase-js'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { createMemoryRouter, RouterProvider, type RouteObject } from 'react-router'

import { AuthContext, type AuthState } from '@/features/auth/auth-context'

export const fakeSession = {
  access_token: 'token',
  user: { id: '00000000-0000-4000-8000-000000000001', email: 'alice@example.com' },
} as unknown as Session

type Options = { path?: string; auth?: Partial<AuthState>; routes?: RouteObject[] }

/** Render a route tree with a fake auth state and a fresh query client. */
export function renderRoutes(element: ReactElement, { path = '/', auth = {}, routes = [] }: Options = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const authState: AuthState = {
    session: fakeSession,
    loading: false,
    configured: true,
    signOut: async () => {},
    ...auth,
  }
  const router = createMemoryRouter([{ path, element }, ...routes], { initialEntries: [path] })
  const { unmount } = render(
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={authState}>
        <RouterProvider router={router} />
      </AuthContext.Provider>
    </QueryClientProvider>,
  )
  return { router, queryClient, unmount }
}
