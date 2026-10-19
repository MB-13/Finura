import { createBrowserRouter, type RouteObject } from 'react-router'

import { AppLayout } from '@/components/layout/AppLayout'
import { RequireAuth } from '@/features/auth/RequireAuth'
import { AuthCallback } from '@/routes/AuthCallback'
import { MarketingLayout } from '@/features/marketing/MarketingLayout'
import { Landing } from '@/routes/Landing'
import { NotFound } from '@/routes/NotFound'
import { SignIn } from '@/routes/SignIn'

export const routes: RouteObject[] = [
  {
    element: <MarketingLayout />,
    children: [
      { path: '/', element: <Landing /> },
      { path: '/privacy', lazy: async () => ({ Component: (await import('@/routes/Privacy')).Privacy }) },
      { path: '/terms', lazy: async () => ({ Component: (await import('@/routes/Terms')).Terms }) },
      { path: '/docs', lazy: async () => ({ Component: (await import('@/routes/Docs')).DocsIndex }) },
      { path: '/docs/:slug', lazy: async () => ({ Component: (await import('@/routes/Docs')).DocsPage }) },
    ],
  },
  { path: '/sign-in', element: <SignIn /> },
  { path: '/auth/callback', element: <AuthCallback /> },
  {
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { path: '/projects', lazy: async () => ({ Component: (await import('@/routes/Projects')).Projects }) },
      {
        path: '/projects/:id',
        lazy: async () => ({ Component: (await import('@/routes/ProjectWorkspace')).ProjectWorkspace }),
      },
      {
        path: '/projects/:id/dataset',
        lazy: async () => ({ Component: (await import('@/routes/DatasetReview')).DatasetReview }),
      },
      { path: '/onboarding', lazy: async () => ({ Component: (await import('@/routes/Onboarding')).Onboarding }) },
      {
        path: '/projects/:id/playground',
        lazy: async () => ({ Component: (await import('@/routes/Playground')).Playground }),
      },
      { path: '/settings', lazy: async () => ({ Component: (await import('@/routes/Settings')).Settings }) },
    ],
  },
  { path: '*', element: <NotFound /> },
]

export const router = createBrowserRouter(routes)
