import { screen } from '@testing-library/react'

import { RequireAuth } from '@/features/auth/RequireAuth'
import { renderRoutes } from '@/test/render'

const signInRoute = [{ path: '/sign-in', element: <div>sign-in page</div> }]

describe('RequireAuth', () => {
  it('shows a spinner while the session loads', () => {
    renderRoutes(<RequireAuth>secret</RequireAuth>, { path: '/projects', auth: { loading: true, session: null } })
    expect(screen.getByRole('status')).toHaveTextContent('Checking your session')
  })

  it('redirects signed-out users to sign-in and remembers where they were going', async () => {
    const { router } = renderRoutes(<RequireAuth>secret</RequireAuth>, {
      path: '/projects',
      auth: { session: null },
      routes: signInRoute,
    })
    expect(await screen.findByText('sign-in page')).toBeInTheDocument()
    expect(router.state.location.search).toBe('?next=%2Fprojects')
    expect(screen.queryByText('secret')).not.toBeInTheDocument()
  })

  it('renders the page for signed-in users', () => {
    renderRoutes(<RequireAuth>secret</RequireAuth>, { path: '/projects' })
    expect(screen.getByText('secret')).toBeInTheDocument()
  })
})
