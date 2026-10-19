# Local testing — Stage 1 (sign in → upload → generate → review → approve)

Time: ~30 minutes. Needs: a Supabase project (free) and a Groq API key (free). No GPU, no deployment.

## A. Create the Supabase project (5 min)
1. Go to https://supabase.com → Sign in → **New project**. Name `doctune-dev`, set a database password (you won't need it for this test), pick the region closest to you → **Create**.
2. Left menu → **Authentication → URL Configuration**:
   - **Site URL**: `http://localhost:5173`
   - **Redirect URLs** → Add URL: `http://localhost:5173/auth/callback` → Save.
3. Left menu → **Project Settings → API Keys** (or **Data API**). Copy:
   - **Project URL** (looks like `https://abcdefgh.supabase.co`)
   - **anon / publishable key** (public key; starts with `eyJ…` or `sb_publishable_…`)
   - Never copy the **service_role / secret** key anywhere for this test.
4. Left menu → **Project Settings → JWT Keys**. If it says the project uses the **Legacy JWT Secret**, copy that secret too (needed in step C). If it shows **JWT Signing Keys** (ECC/RSA) as current, you don't need anything from this page.

## B. Get a Groq key (2 min)
https://console.groq.com/keys → **Create API Key** → copy it. Don't paste it in chat or files — you'll paste it into the app.

## C. Create the two config files (you do this; the assistant is not allowed to read/write `.env` files)
From the project folder `proj_6oc/`:
```bash
cp backend/env.example backend/.env
cp frontend/env.example frontend/.env
```
Edit `backend/.env` and set:
```
SUPABASE_URL=https://YOUR-PROJECT.supabase.co
# only if step A4 said "Legacy JWT Secret":
# SUPABASE_JWT_SECRET=paste-the-legacy-secret
EMBEDDING_BACKEND=hash
EMAIL_BACKEND=smtp
```
(`EMBEDDING_BACKEND=hash` avoids a ~700 MB model download for this test. `EMAIL_BACKEND=smtp` sends emails to Mailpit so you can see them.)

Edit `frontend/.env` and set:
```
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=https://YOUR-PROJECT.supabase.co
VITE_SUPABASE_ANON_KEY=paste-the-anon-or-publishable-key
```

## D. Install and start (first time ~3 min)
```bash
make up                                  # Postgres, Redis, Mailpit (Docker)
cd backend && uv sync && cd ..
cd frontend && corepack pnpm install && cd ..
make migrate
```
Open three terminals in `proj_6oc/`:
```bash
make backend     # terminal 1 → API on http://localhost:8000 (check http://localhost:8000/readyz)
make worker      # terminal 2 → background jobs (parsing, generation)
make frontend    # terminal 3 → app on http://localhost:5173
```

## E. Test the flow (what you should see)
1. Open http://localhost:5173 → **Get started** → enter your email → **Email me a link**. Open the email from Supabase and click the link → you land on **Projects** (or onboarding the first time).
   - Supabase's built-in email allows only a few emails per hour — if no email arrives, wait or use GitHub sign-in later.
2. **Settings → AI provider keys → Groq** → paste the key → **Save**. Within ~10 s the status should become **Valid**.
3. **Projects → New project** → name it → **Create**.
4. Upload **one real PDF with several pages of text** (5–30 pages works well; max 20 MB). Wait for the progress bar → **Process documents**. The status goes *Reading documents* → the style step. Open **Documents** to see the chunks.
5. Pick a template (e.g. *Customer support bot*), adjust the description and examples → **Save & generate preview**. After ~30–60 s you see ~8 sample question/answer pairs with scores.
6. **Generate full dataset** → check the estimate → confirm. With the default 500 pairs on Groq's free tier this can take a long time (and may wait for quota). **For a quick test set the dataset size to 50** in the style form's *Advanced* section before generating. Progress updates live.
7. When it reaches **Review**: open the review table, edit an answer, drop a pair, add one, then **Approve dataset**.
8. **Set up training** → choose a model and preset → you get a **job token** and Colab steps. Stop here for Stage 1 — training needs Stage 2 (public API address + notebook).

Also check: Mailpit at http://localhost:58025 (emails), Settings → Delete account (only on a test account).

## F. If something goes wrong
| Symptom | Fix |
|---|---|
| Sign-in says "isn't configured" | `frontend/.env` values missing → fix and restart `make frontend` |
| After sign-in, pages show "Invalid token" / 401 | `SUPABASE_URL` in `backend/.env` wrong, or your project uses the legacy secret → set `SUPABASE_JWT_SECRET` (A4), restart `make backend` |
| Magic link opens but loops to sign-in | Redirect URL missing in Supabase (A2) |
| Stuck on *Reading documents* | `make worker` isn't running — start it; the job continues |
| Key status *Invalid* | Wrong Groq key, or copy included spaces — paste again |
| Generation shows *waiting for quota* | Free Groq limit reached; it resumes automatically (the worker's beat isn't running locally — run `make beat` in a 4th terminal to get automatic resume) |

Send the assistant: what you did, what you saw, and the last ~30 lines of the terminal that showed an error.
