import { Moon, Sun } from 'lucide-react'

import { ThemeMenuItems } from '@/components/theme/ThemeMenuItems'
import { useTheme } from '@/components/theme/theme-context'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

/** Icon button + menu to pick light / dark / system. For pages outside the app shell (landing, sign-in). */
export function ThemeToggle() {
  const { resolvedTheme } = useTheme()
  const Icon = resolvedTheme === 'dark' ? Moon : Sun
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Change theme">
          <Icon aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <ThemeMenuItems />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
