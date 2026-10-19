import { Monitor, Moon, Sun } from 'lucide-react'

import { useTheme, type Theme } from '@/components/theme/theme-context'
import { DropdownMenuRadioGroup, DropdownMenuRadioItem } from '@/components/ui/dropdown-menu'

/** Light / dark / system radio items. Render inside a DropdownMenuContent. */
export function ThemeMenuItems() {
  const { theme, setTheme } = useTheme()
  return (
    <DropdownMenuRadioGroup value={theme} onValueChange={(v) => setTheme(v as Theme)}>
      <DropdownMenuRadioItem value="light">
        <Sun aria-hidden /> Light
      </DropdownMenuRadioItem>
      <DropdownMenuRadioItem value="dark">
        <Moon aria-hidden /> Dark
      </DropdownMenuRadioItem>
      <DropdownMenuRadioItem value="system">
        <Monitor aria-hidden /> System
      </DropdownMenuRadioItem>
    </DropdownMenuRadioGroup>
  )
}
