import { screen, within } from '@testing-library/react'

import { MarketingLayout } from '@/features/marketing/MarketingLayout'
import { DOCS } from '@/features/marketing/docs-content'
import { DocsIndex, DocsPage } from '@/routes/Docs'
import { Landing } from '@/routes/Landing'
import { Privacy } from '@/routes/Privacy'
import { Terms } from '@/routes/Terms'
import { renderRoutes } from '@/test/render'

function renderAt(path: string) {
  return renderRoutes(<div />, {
    path: '/__root',
    routes: [
      {
        element: <MarketingLayout />,
        children: [
          { path: '/', element: <Landing /> },
          { path: '/privacy', element: <Privacy /> },
          { path: '/terms', element: <Terms /> },
          { path: '/docs', element: <DocsIndex /> },
          { path: '/docs/:slug', element: <DocsPage /> },
        ],
      },
    ],
  }).router.navigate(path)
}

describe('marketing pages', () => {
  it.each([
    ['/privacy', 'Privacy'],
    ['/terms', 'Terms of use'],
  ])('%s renders the DRAFT lawyer-review notice', async (path, heading) => {
    await renderAt(path)
    expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent(/DRAFT/)
    expect(screen.getByRole('note')).toHaveTextContent(/lawyer must review it before DocTune launches/)
  })

  it('privacy covers third-party AI, 14-day deletion, account deletion and Colab', async () => {
    await renderAt('/privacy')
    expect(await screen.findByText(/third-party AI providers whose API keys you connect/)).toBeInTheDocument()
    expect(screen.getByText(/deleted 14 days after a job ends/)).toBeInTheDocument()
    expect(screen.getByText(/delete your account and all of your data at any time/)).toBeInTheDocument()
    expect(screen.getByText(/Google Colab account, under Google/)).toBeInTheDocument()
  })

  it('terms cover responsibilities and no warranty', async () => {
    await renderAt('/terms')
    expect(await screen.findByText(/license of the base model you choose/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'No warranty' })).toBeInTheDocument()
  })

  it('landing has an FAQ and footer links to privacy, terms and help', async () => {
    await renderAt('/')
    expect(await screen.findByRole('heading', { name: 'Questions' })).toBeInTheDocument()
    expect(screen.getByText('What happens when Colab pauses?')).toBeInTheDocument()
    const footer = screen.getByRole('navigation', { name: 'Footer' })
    expect(within(footer).getByRole('link', { name: 'Privacy' })).toHaveAttribute('href', '/privacy')
    expect(within(footer).getByRole('link', { name: 'Terms' })).toHaveAttribute('href', '/terms')
    expect(within(footer).getByRole('link', { name: 'Help' })).toHaveAttribute('href', '/docs')
  })

  it('docs index lists every guide and each page renders', async () => {
    await renderAt('/docs')
    for (const d of DOCS) expect(await screen.findByRole('link', { name: d.title })).toHaveAttribute('href', `/docs/${d.slug}`)
  })

  it('renders a guide and a not-found for unknown slugs', async () => {
    await renderAt('/docs/ollama')
    expect(await screen.findByRole('heading', { name: 'Use your GGUF in Ollama' })).toBeInTheDocument()
    expect(screen.getByText(/ollama create my-doctune-model/)).toBeInTheDocument()
  })
})

describe('docs 404', () => {
  it('shows not found for an unknown guide', async () => {
    await renderAt('/docs/nope')
    expect(await screen.findByText('Page not found')).toBeInTheDocument()
  })
})
