/** Seconds before "Send a new code" is allowed again (Supabase's free email service allows very few emails per hour). */
export const RESEND_COOLDOWN = 60

/** Supabase error text -> something a user can act on. */
export function friendlyAuthError(message: string): string {
  const m = message.toLowerCase()
  if (m.includes('rate limit')) {
    return 'Too many sign-in emails were sent. Wait about an hour, or continue with GitHub.'
  }
  if (m.includes('expired') || m.includes('invalid') || m.includes('token')) {
    return 'That code is wrong or has expired. Check the newest email, or send a new code.'
  }
  return message
}

/** Supabase's default minimum password length. */
export const PASSWORD_MIN = 6

export function friendlyPasswordError(message: string): string {
  const m = message.toLowerCase()
  if (m.includes('invalid login credentials')) return 'Wrong email or password. No account yet? Create one below.'
  if (m.includes('email not confirmed')) {
    return 'This account still needs email confirmation. Turn off "Confirm email" in Supabase, delete the user and create it again.'
  }
  if (m.includes('already registered')) return 'An account with this email already exists. Sign in instead.'
  if (m.includes('signups not allowed')) return 'Sign-ups are disabled in Supabase (Authentication → Sign In / Providers).'
  return message
}
