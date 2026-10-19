import { createContext, useContext } from 'react'

export type Theme = 'light' | 'dark' | 'system'

export const THEME_STORAGE_KEY = 'doctune-theme'

export type ThemeState = {
  /** What the user picked. */
  theme: Theme
  /** What is actually applied right now (system resolved). */
  resolvedTheme: 'light' | 'dark'
  setTheme: (theme: Theme) => void
}

/** Defaults to an inert state so components using the theme still render in tests / previews without a provider. */
export const ThemeContext = createContext<ThemeState>({ theme: 'system', resolvedTheme: 'light', setTheme: () => {} })

export function useTheme(): ThemeState {
  return useContext(ThemeContext)
}

export function readStoredTheme(): Theme {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY)
    return value === 'light' || value === 'dark' || value === 'system' ? value : 'system'
  } catch {
    return 'system'
  }
}

export function systemPrefersDark(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches
}
