// Every VITE_* value is bundled into the browser — never put a secret here.
export const env = {
  apiUrl: (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000',
  supabaseUrl: import.meta.env.VITE_SUPABASE_URL as string | undefined,
  supabaseAnonKey: import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined,
}

export const supabaseConfigured = Boolean(env.supabaseUrl && env.supabaseAnonKey)
