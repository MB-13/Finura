import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ThemeProvider } from '@/components/theme/ThemeProvider'
import { AppLayout } from '@/components/layout/AppLayout'
import { renderRoutes } from '@/test/render'

function renderLayout(signOut = vi.fn(async () => {})) {
  const view = renderRoutes(
    <ThemeProvider>
      <AppLayout />
    </ThemeProvider>,
    { path: '/projects', auth: { signOut }, routes: [{ path: '/sign-in', element: <div>Sign-in page</div> }, { path: '/settings', element: <div>Settings page</div> }] },
  )
  return { ...view, signOut }
}

describe('AppLayout account menu', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
  })

  it('shows the signed-in email and opens Settings', async () => {
    renderLayout()
    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }))
    expect(await screen.findByText('alice@example.com')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('menuitem', { name: /Settings/ }))
    expect(await screen.findByText('Settings page')).toBeInTheDocument()
  })

  it('signs out and goes to /sign-in', async () => {
    const { signOut } = renderLayout()
    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }))
    await userEvent.click(await screen.findByRole('menuitem', { name: /Sign out/ }))
    expect(signOut).toHaveBeenCalledTimes(1)
    expect(await screen.findByText('Sign-in page')).toBeInTheDocument()
  })

  it('changes the theme from the menu: html class and stored choice', async () => {
    renderLayout()
    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }))
    await userEvent.click(await screen.findByRole('menuitemradio', { name: /Dark/ }))
    expect(document.documentElement).toHaveClass('dark')
    expect(localStorage.getItem('doctune-theme')).toBe('dark')

    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }))
    await userEvent.click(await screen.findByRole('menuitemradio', { name: /Light/ }))
    expect(document.documentElement).not.toHaveClass('dark')
    expect(localStorage.getItem('doctune-theme')).toBe('light')
  })
})
