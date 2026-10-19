import { createClient, type SupabaseClient } from '@supabase/supabase-js'

import { env, supabaseConfigured } from '@/lib/env'

let client: SupabaseClient | null = null

export function getSupabase(): SupabaseClient {
  if (!supabaseConfigured) {
    throw new Error('Supabase is not configured: set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY')
  }
  client ??= createClient(env.supabaseUrl!, env.supabaseAnonKey!, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, flowType: 'pkce' },
  })
  return client
}

export async function getAccessToken(): Promise<string | null> {
  if (!supabaseConfigured) return null
  const { data } = await getSupabase().auth.getSession()
  return data.session?.access_token ?? null
}
