import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Toaster } from 'sonner'

import {
  readStoredTheme,
  systemPrefersDark,
  ThemeContext,
  THEME_STORAGE_KEY,
  useTheme,
  type Theme,
} from '@/components/theme/theme-context'

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readStoredTheme)
  const [systemDark, setSystemDark] = useState(systemPrefersDark)

  useEffect(() => {
    if (typeof matchMedia !== 'function') return
    const query = matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => setSystemDark(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  const resolvedTheme = theme === 'system' ? (systemDark ? 'dark' : 'light') : theme

  useEffect(() => {
    document.documentElement.classList.toggle('dark', resolvedTheme === 'dark')
  }, [resolvedTheme])

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next)
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next)
    } catch {
      // storage can be unavailable (private mode); the choice still applies for this session
    }
  }, [])

  const value = useMemo(() => ({ theme, resolvedTheme, setTheme }), [theme, resolvedTheme, setTheme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

/** Sonner toaster that follows the active theme. Render inside <ThemeProvider>. */
export function ThemedToaster() {
  const { resolvedTheme } = useTheme()
  return <Toaster richColors closeButton theme={resolvedTheme} />
}
