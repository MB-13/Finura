import { Link } from 'react-router'

const linkClass = 'rounded-sm text-caption text-muted-foreground transition-colors hover:text-foreground'

const columns: { heading: string; links: { to: string; label: string }[] }[] = [
  {
    heading: 'Product',
    links: [
      { to: '/#how-it-works', label: 'How it works' },
      { to: '/#faq', label: 'FAQ' },
      { to: '/sign-in', label: 'Get started' },
    ],
  },
  {
    heading: 'Resources',
    links: [
      { to: '/docs', label: 'Help' },
      { to: '/docs/groq-key', label: 'Free Groq key' },
      { to: '/docs/run-notebook', label: 'Notebook and pauses' },
      { to: '/docs/ollama', label: 'GGUF in Ollama' },
    ],
  },
  {
    heading: 'Legal',
    links: [
      { to: '/privacy', label: 'Privacy' },
      { to: '/terms', label: 'Terms' },
    ],
  },
]

export function FooterLinks() {
  return (
    <nav aria-label="Footer" className="grid grid-cols-2 gap-x-8 gap-y-8 sm:grid-cols-3 sm:gap-x-12">
      {columns.map((c) => (
        <div key={c.heading} className="flex flex-col gap-3">
          <div className="text-eyebrow">{c.heading}</div>
          <ul className="flex flex-col gap-2">
            {c.links.map((l) => (
              <li key={l.to}>
                <Link to={l.to} className={linkClass}>
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}
