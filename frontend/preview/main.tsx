import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createMemoryRouter, RouterProvider } from 'react-router'

import { ThemeProvider, ThemedToaster } from '@/components/theme/ThemeProvider'
import { THEME_STORAGE_KEY } from '@/components/theme/theme-context'
import { AuthContext, type AuthState } from '@/features/auth/auth-context'
import { routes } from '@/router'
import { fakeSession } from '@/test/render'

import { Gallery } from './gallery'
import { PlaygroundDemo } from './playground-settings'
import { installMockApi } from './mock-api'
import { defaultHandlers, projectFor, scenarios } from './scenarios'
import './preview.css'

// Everything is controlled by the URL, so screenshots are reproducible:
//   ?view=gallery               component gallery
//   ?scenario=<name>            a page with stubbed API data (see scenarios.ts)
//   ?route=/some/path           override the scenario's route
//   &theme=dark|light|system    default light
const params = new URLSearchParams(window.location.search)
const theme = params.get('theme') ?? 'light'
try {
  localStorage.setItem(THEME_STORAGE_KEY, theme)
} catch {
  // ignore
}
document.documentElement.classList.toggle('dark', theme === 'dark')

const scenarioName = params.get('scenario') ?? 'projects'
const scenario = scenarios[scenarioName]
const view = params.get('view') ?? (params.has('scenario') ? 'page' : 'index')

const auth: AuthState = { session: params.has('anon') ? null : fakeSession, loading: false, configured: true, signOut: async () => {} }
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 30_000 } } })

function Index() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 p-8">
      <h1 className="text-page-title">UI preview</h1>
      <p className="text-muted-foreground">
        <a className="text-primary underline" href="?view=gallery">gallery</a> | append <code>&amp;theme=dark</code> for dark mode.
      </p>
      <ul className="grid gap-1 text-sm">
        {Object.entries(scenarios).map(([name, s]) => (
          <li key={name}>
            <a className="font-mono text-primary underline" href={`?scenario=${name}`}>{name}</a>
            <span className="text-muted-foreground"> {s.note ?? s.route}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function render() {
  let body
  if (view === 'gallery') {
    body = <RouterProvider router={createMemoryRouter([{ path: '*', element: <Gallery /> }])} />
  } else if (view === 'playground-demo') {
    body = <PlaygroundDemo variant={params.get('variant') ?? 'chat'} />
  } else if (view === 'page' && scenario) {
    installMockApi([...(scenario.handlers ?? []), ...defaultHandlers(() => projectFor('draft'))])
    const router = createMemoryRouter(routes, { initialEntries: [params.get('route') ?? scenario.route] })
    body = <RouterProvider router={router} />
  } else {
    body = <Index />
  }
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <AuthContext.Provider value={auth}>
            {body}
            <ThemedToaster />
          </AuthContext.Provider>
        </QueryClientProvider>
      </ThemeProvider>
    </StrictMode>,
  )
}

render()
