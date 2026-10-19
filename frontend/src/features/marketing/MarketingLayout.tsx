import { Link, NavLink, Outlet } from 'react-router'

import { GuideJoint, GuideRails } from '@/components/marketing/GuideRails'
import { Logo } from '@/components/Logo'
import { ThemeToggle } from '@/components/theme/ThemeToggle'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/auth-context'
import { FooterLinks } from '@/features/marketing/FooterLinks'
import { MarketingContainer } from '@/features/marketing/MarketingContainer'
import { cn } from '@/lib/utils'

export function MarketingLayout() {
  const { session } = useAuth()
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/70">
        <MarketingContainer className="flex h-14 items-center gap-4 sm:gap-6">
          <Link to="/" aria-label="DocTune home" className="rounded-md">
            <Logo />
          </Link>
          <nav aria-label="Main" className="flex gap-1 text-sm">
            <NavLink
              to="/docs"
              className={({ isActive }) =>
                cn(
                  'rounded-md px-2.5 py-1.5 transition-colors',
                  isActive ? 'bg-accent font-medium text-accent-foreground' : 'text-muted-foreground hover:text-foreground',
                )
              }
            >
              Help
            </NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-1.5">
            <ThemeToggle />
            <Button asChild size="sm">
              <Link to={session ? '/projects' : '/sign-in'}>{session ? 'Open app' : 'Sign in'}</Link>
            </Button>
          </div>
        </MarketingContainer>
      </header>
      <main className="w-full flex-1">
        <Outlet />
      </main>
      <GuideJoint />
      <footer className="bg-background">
        <GuideRails className="max-sm:border-x-0">
          <div className="flex flex-col gap-10 px-4 py-12 sm:px-6 lg:flex-row lg:justify-between">
            <div className="flex max-w-xs flex-col gap-3">
              <Logo />
              <p className="text-caption text-muted-foreground">
                Turn your documents into your own fine-tuned AI model, using free tools and your own accounts.
              </p>
            </div>
            <FooterLinks />
          </div>
          <div className="flex flex-col gap-3 border-t px-4 py-5 text-caption text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <p>Built on free tiers and open-source models. No card needed.</p>
            <div className="flex items-center gap-3">
              <span>&copy; 2026 DocTune</span>
              <ThemeToggle />
            </div>
          </div>
        </GuideRails>
      </footer>
    </div>
  )
}
