#!/usr/bin/env bash
# Creates backend/.env and frontend/.env for local testing (docs/runbooks/local-testing.md).
# Run it yourself in a terminal from the project folder:   bash scripts/setup-env.sh
# Secrets are typed hidden and never printed.
set -euo pipefail
cd "$(dirname "$0")/.."

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
ok() { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$*"; exit 1; }

# set KEY=VALUE in a file: replace an existing (or commented) line, else append
set_var() {
  local file=$1 key=$2 value=$3 tmp
  tmp=$(mktemp)
  awk -v k="$key" -v v="$value" '
    BEGIN { done = 0 }
    $0 ~ "^#? *" k "=" { if (!done) { print k "=" v; done = 1 }; next }
    { print }
    END { if (!done) print k "=" v }
  ' "$file" > "$tmp"
  mv "$tmp" "$file"
  chmod 600 "$file"
}

backup_if_exists() {
  if [[ -f $1 ]]; then
    cp "$1" "$1.bak.$(date +%s)"
    warn "$1 already existed — backed up next to it"
  fi
}

bold "DocTune local setup"
echo "You need: Supabase Project URL and anon/publishable key (Project Settings → API Keys)."
echo

# --- Supabase URL ---
read -r -p "Supabase Project URL (https://xxxx.supabase.co): " SUPABASE_URL
SUPABASE_URL=${SUPABASE_URL%/}
[[ $SUPABASE_URL =~ ^https://[a-z0-9-]+\.supabase\.co$ ]] || fail "That doesn't look like https://<project>.supabase.co"

# --- anon key (public, but hidden anyway) ---
read -r -s -p "Supabase anon / publishable key (hidden): " ANON_KEY; echo
[[ ${#ANON_KEY} -ge 20 ]] || fail "Key looks too short"

# --- check the project and find out how it signs tokens ---
bold "Checking your Supabase project…"
health=$(curl -s -o /dev/null -w '%{http_code}' -H "apikey: $ANON_KEY" "$SUPABASE_URL/auth/v1/health" || true)
[[ $health == 200 ]] && ok "Project reachable and key accepted" || fail "Supabase answered $health — check the URL and key"

jwks=$(curl -s -H "apikey: $ANON_KEY" "$SUPABASE_URL/auth/v1/.well-known/jwks.json" || true)
JWT_SECRET=""
if [[ $jwks == *'"kty"'* ]]; then
  ok "Project publishes JWT signing keys"
  echo "  Many projects still SIGN sessions with the legacy secret during the switch-over."
  echo "  Paste the Legacy JWT secret (Project Settings → JWT Keys) to be safe, or press Enter to skip."
  read -r -s -p "  Legacy JWT secret (hidden, optional): " JWT_SECRET; echo
else
  warn "Project uses the legacy JWT secret."
  echo "  Copy it from Project Settings → JWT Keys → Legacy JWT Secret."
  read -r -s -p "  Legacy JWT secret (hidden): " JWT_SECRET; echo
  [[ ${#JWT_SECRET} -ge 32 ]] || fail "Secret looks too short"
fi

# --- write backend/.env ---
backup_if_exists backend/.env
cp backend/env.example backend/.env
set_var backend/.env SUPABASE_URL "$SUPABASE_URL"
[[ -n $JWT_SECRET ]] && set_var backend/.env SUPABASE_JWT_SECRET "$JWT_SECRET"
set_var backend/.env EMBEDDING_BACKEND hash
set_var backend/.env EMAIL_BACKEND smtp
# a random signing key even for local use
set_var backend/.env STORAGE_SIGNING_KEY "$(head -c 32 /dev/urandom | base64 | tr -d '/+=' )"
ok "backend/.env written"

# --- write frontend/.env ---
backup_if_exists frontend/.env
cp frontend/env.example frontend/.env
set_var frontend/.env VITE_API_URL http://localhost:8000
set_var frontend/.env VITE_SUPABASE_URL "$SUPABASE_URL"
set_var frontend/.env VITE_SUPABASE_ANON_KEY "$ANON_KEY"
ok "frontend/.env written"

echo
bold "Reminder in Supabase → Authentication → URL Configuration:"
echo "  Site URL:      http://localhost:5173"
echo "  Redirect URL:  http://localhost:5173/auth/callback"
echo
bold "Next:"
echo "  make up && make migrate"
echo "  then in 4 terminals: make backend · make worker · make beat · make frontend"
