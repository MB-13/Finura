import { act, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { friendlyAuthError, RESEND_COOLDOWN } from '@/features/auth/sign-in'
import { SignIn } from '@/routes/SignIn'
import { renderRoutes } from '@/test/render'

const auth = {
  signInWithOtp: vi.fn(),
  verifyOtp: vi.fn(),
  signInWithOAuth: vi.fn(),
}

vi.mock('@/lib/supabase', () => ({ getSupabase: () => ({ auth }) }))

function renderSignIn() {
  return renderRoutes(<SignIn />, { path: '/sign-in', auth: { session: null } })
}

async function requestCode(user = userEvent.setup()) {
  renderSignIn()
  await user.type(screen.getByLabelText('Email'), 'alice@example.com')
  await user.click(screen.getByRole('button', { name: 'Email me a code' }))
  return user
}

describe('SignIn with an email code', () => {
  beforeEach(() => {
    auth.signInWithOtp.mockReset().mockResolvedValue({ error: null })
    auth.verifyOtp.mockReset().mockResolvedValue({ error: null })
    auth.signInWithOAuth.mockReset().mockResolvedValue({ error: null })
  })

  it('sends a code and shows the code step', async () => {
    await requestCode()
    expect(auth.signInWithOtp).toHaveBeenCalledWith({
      email: 'alice@example.com',
      options: { emailRedirectTo: expect.stringContaining('/auth/callback?next=') },
    })
    expect(screen.getByText('Enter the code we sent to alice@example.com.')).toBeInTheDocument()
    expect(screen.getByLabelText('Sign-in code')).toBeInTheDocument()
  })

  it('verifies the typed code (spaces ignored) as an email OTP', async () => {
    const user = await requestCode()
    const submit = screen.getByRole('button', { name: 'Sign in' })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText('Sign-in code'), '123 456')
    await user.click(submit)
    expect(auth.verifyOtp).toHaveBeenCalledTimes(1)
    expect(auth.verifyOtp).toHaveBeenCalledWith({ email: 'alice@example.com', token: '123456', type: 'email' })
  })

  it('falls back to the signup type for brand-new users', async () => {
    auth.verifyOtp
      .mockResolvedValueOnce({ error: { message: 'Token has expired or is invalid' } })
      .mockResolvedValueOnce({ error: null })
    const user = await requestCode()
    await user.type(screen.getByLabelText('Sign-in code'), '654321')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(auth.verifyOtp).toHaveBeenLastCalledWith({ email: 'alice@example.com', token: '654321', type: 'signup' })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows a clear message for a wrong code', async () => {
    auth.verifyOtp.mockResolvedValue({ error: { message: 'Token has expired or is invalid' } })
    const user = await requestCode()
    await user.type(screen.getByLabelText('Sign-in code'), '000000')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('wrong or has expired')
  })

  it('explains the email rate limit', async () => {
    auth.signInWithOtp.mockResolvedValue({ error: { message: 'email rate limit exceeded' } })
    await requestCode()
    expect(await screen.findByRole('alert')).toHaveTextContent('Wait about an hour, or continue with GitHub')
    expect(screen.getByLabelText('Email')).toBeInTheDocument() // still on the email step
  })

  it('blocks resending until the cooldown ends', { timeout: 20_000 }, async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const user = await requestCode(userEvent.setup({ advanceTimers: vi.advanceTimersByTime }))
      const resend = screen.getByRole('button', { name: /Send a new code in/ })
      expect(resend).toBeDisabled()
      for (let i = 0; i < RESEND_COOLDOWN; i++) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(1000)
        })
      }
      const ready = screen.getByRole('button', { name: 'Send a new code' })
      expect(ready).toBeEnabled()
      await user.click(ready)
      expect(auth.signInWithOtp).toHaveBeenCalledTimes(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it('can go back and change the email', async () => {
    const user = await requestCode()
    await user.click(screen.getByRole('button', { name: 'Use a different email' }))
    expect(screen.getByLabelText('Email')).toHaveValue('alice@example.com')
  })
})

describe('friendlyAuthError', () => {
  it('passes unknown messages through', () => {
    expect(friendlyAuthError('Something else')).toBe('Something else')
  })
})
