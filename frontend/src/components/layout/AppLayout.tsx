import { LogOut, Settings as SettingsIcon } from 'lucide-react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router'

import { Logo } from '@/components/Logo'
import { ThemeMenuItems } from '@/components/theme/ThemeMenuItems'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAuth } from '@/features/auth/auth-context'
import { cn } from '@/lib/utils'

const navItems = [
  { to: '/projects', label: 'Projects' },
  { to: '/settings', label: 'Settings' },
]

function UserMenu() {
  const { session, signOut } = useAuth()
  const navigate = useNavigate()
  const email = session?.user.email ?? ''

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Account menu" className="rounded-full size-9">
          <span
            aria-hidden
            className="flex size-7 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-foreground ring-1 ring-primary/20"
          >
            {email.charAt(0).toUpperCase() || '?'}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="flex flex-col gap-0.5 font-normal">
          <span className="text-caption text-muted-foreground">Signed in as</span>
          <span className="truncate font-medium">{email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-overline text-muted-foreground">Theme</DropdownMenuLabel>
        <ThemeMenuItems />
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void navigate('/settings')}>
          <SettingsIcon aria-hidden /> Settings
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={async () => {
            await signOut()
            navigate('/sign-in', { replace: true })
          }}
        >
          <LogOut aria-hidden /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function AppLayout() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <a
        href="#main-content"
        className="sr-only z-50 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-border/80 bg-background/80 backdrop-blur-md supports-[backdrop-filter]:bg-background/70">
        <div className="mx-auto flex h-12 w-full max-w-6xl items-center gap-3 px-4 sm:gap-5 sm:px-6 lg:px-8">
          <Link to="/projects" aria-label="DocTune home" className="rounded-md">
            <Logo />
          </Link>
          <nav aria-label="Main" className="flex items-center gap-0.5">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'rounded-full px-3 py-1 text-[0.8125rem] font-medium transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50',
                    isActive
                      ? 'bg-accent text-accent-foreground shadow-[inset_0_0_0_1px_var(--border)]'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-1">
            <UserMenu />
          </div>
        </div>
      </header>
      <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-6xl px-4 py-6 outline-none sm:px-6 sm:py-10 lg:px-8">
        <Outlet />
      </main>
    </div>
  )
}
