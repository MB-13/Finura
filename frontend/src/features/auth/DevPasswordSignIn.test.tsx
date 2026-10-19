import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { DevPasswordSignIn } from '@/features/auth/DevPasswordSignIn'
import { friendlyPasswordError } from '@/features/auth/sign-in'

const auth = { signInWithPassword: vi.fn(), signUp: vi.fn() }
vi.mock('@/lib/supabase', () => ({ getSupabase: () => ({ auth }) }))

async function fill(user: ReturnType<typeof userEvent.setup>, email = 'alice@example.com', password = 'secret123') {
  await user.type(screen.getByLabelText('Test account email'), email)
  await user.type(screen.getByLabelText('Password'), password)
}

describe('DevPasswordSignIn', () => {
  beforeEach(() => {
    auth.signInWithPassword.mockReset().mockResolvedValue({ data: { session: {} }, error: null })
    auth.signUp.mockReset().mockResolvedValue({ data: { session: {} }, error: null })
  })

  it('signs in with email and password', async () => {
    const user = userEvent.setup()
    render(<DevPasswordSignIn />)
    await fill(user)
    await user.click(screen.getByRole('button', { name: 'Sign in with password' }))
    expect(auth.signInWithPassword).toHaveBeenCalledWith({ email: 'alice@example.com', password: 'secret123' })
  })

  it('shows a clear message for wrong credentials', async () => {
    auth.signInWithPassword.mockResolvedValue({ data: { session: null }, error: { message: 'Invalid login credentials' } })
    const user = userEvent.setup()
    render(<DevPasswordSignIn />)
    await fill(user)
    await user.click(screen.getByRole('button', { name: 'Sign in with password' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Wrong email or password')
  })

  it('creates an account', async () => {
    const user = userEvent.setup()
    render(<DevPasswordSignIn />)
    await user.click(screen.getByRole('button', { name: 'No account yet? Create one' }))
    await fill(user)
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    expect(auth.signUp).toHaveBeenCalledWith({ email: 'alice@example.com', password: 'secret123' })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('explains when Supabase still requires email confirmation', async () => {
    auth.signUp.mockResolvedValue({ data: { session: null, user: {} }, error: null })
    const user = userEvent.setup()
    render(<DevPasswordSignIn />)
    await user.click(screen.getByRole('button', { name: 'No account yet? Create one' }))
    await fill(user)
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Turn off "Confirm email"')
  })

  it('maps other Supabase errors', () => {
    expect(friendlyPasswordError('User already registered')).toContain('Sign in instead')
    expect(friendlyPasswordError('Email not confirmed')).toContain('Confirm email')
    expect(friendlyPasswordError('boom')).toBe('boom')
  })
})
