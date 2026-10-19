import indexHtml from '../../../index.html?raw'
import { readStoredTheme } from '@/components/theme/theme-context'

/** The inline no-flash script in index.html must agree with readStoredTheme(). */
function runInlineScript(stored: string | null, prefersDark: boolean): boolean {
  const script = /<script>([\s\S]*?)<\/script>/.exec(indexHtml)![1]!
  let dark = false
  const document = { documentElement: { classList: { toggle: (_c: string, on: boolean) => (dark = on) } } }
  const localStorage = { getItem: () => stored }
  const matchMedia = () => ({ matches: prefersDark })
  new Function('document', 'localStorage', 'matchMedia', script)(document, localStorage, matchMedia)
  return dark
}

describe('index.html theme script', () => {
  it.each([
    ['dark', true, true],
    ['dark', false, true],
    ['light', true, false],
    ['light', false, false],
    ['system', true, true],
    ['system', false, false],
    [null, true, true],
    [null, false, false],
    // an invalid stored value means "system", exactly like readStoredTheme()
    ['purple', true, true],
    ['purple', false, false],
  ])('stored %s, system dark %s -> dark %s', (stored, prefersDark, expected) => {
    expect(runInlineScript(stored, prefersDark)).toBe(expected)
  })

  it('readStoredTheme treats an invalid value as system', () => {
    localStorage.setItem('doctune-theme', 'purple')
    expect(readStoredTheme()).toBe('system')
    localStorage.clear()
  })
})
