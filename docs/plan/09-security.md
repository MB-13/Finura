# 09 — Security Plan

## 1. Assets
Users' LLM API keys · job tokens · uploaded documents (may be business documents) · generated datasets · adapters · Supabase sessions · infrastructure credentials (R2, DB, encryption keys).

## 2. Threats → controls
| # | Threat | Control | Verified by |
|---|---|---|---|
| S1 | IDOR: user reads/edits another user's project, doc, pair, job, artifact | Every service query scoped by `user_id`; not-owned = 404; tests for every route with a second user | pytest matrix `test_authz.py` |
| S2 | Forged/expired JWT | JWKS verification, `aud`, `iss`, `exp`; reject `none`/HS confusion (algorithms allow-list) | unit tests with crafted tokens |
| S3 | Job token leak (shared notebook, screenshot) | 14-day expiry, one job scope, revocable/rotatable, hashed at rest, shown once, `getpass` (not echoed or saved in the .ipynb), `token_prefix` only in UI | tests: expired, revoked, other job |
| S4 | Job token brute force | 256-bit entropy, rate limit per IP on `/jobs/current/*` (60/min), 401 without detail | load test sanity |
| S5 | LLM key leakage | Fernet at rest; decrypted only in worker memory at call time; structlog + Sentry scrubbers; never returned (masked last4); never sent to the browser or the notebook | grep tests for logging; unit test of scrubber |
| S6 | Google creds / HF tokens stored | Notebook uses `getpass`, never posts them; API schemas have no fields for them | code review checklist |
| S7 | Malicious uploads (zip bombs, malformed PDFs, polyglots) | Extension allow-list + magic-byte sniff; 20 MB cap verified via HEAD; page cap 500; parse in separate worker container as non-root with mem/time limits; no shelling out with file names; temp dirs cleaned | fixture tests (malformed, encrypted, huge page count) |
| S8 | Pre-signed URL abuse | Exact key, 15-min TTL, content-type fixed, size verified after upload and object deleted if mismatched; keys namespaced by user/job; no list permission | tests |
| S9 | Storage exhaustion (free tier) | Caps per file/project/user (20 active projects), checkpoint size limit 1.5 GB, retention cleanup, usage alerts | usage dashboard |
| S10 | Prompt injection via documents | Document text only in the "SOURCE TEXT" slot; outputs parsed as data via Pydantic; LLM output never decides authz/status; judge can only drop pairs | review |
| S11 | XSS from model output / user content | React escaping; markdown via `react-markdown` + `rehype-sanitize`, no `dangerouslySetInnerHTML`; CSP | e2e with `<script>` payloads |
| S12 | SSRF via custom HF ID or provider base URL | HF ID regex `^[\w.-]+/[\w.-]+$`, only `huggingface.co` API calls; provider base URLs fixed in code (users can't set URLs) | unit tests |
| S13 | CSRF | API uses bearer tokens (no cookies) → not applicable; CORS restricted to web origin | config test |
| S14 | Abuse of generation/playground resources | slowapi limits per user; one active generation per user; playground concurrency limits | tests |
| S15 | Secrets in the web bundle | Only public `VITE_*` values (API URL, Supabase URL + anon key, Sentry DSN); CI grep for known secret patterns + gitleaks | CI |
| S16 | Dependency vulns | Lockfiles, Dependabot, weekly audits | CI |
| S17 | VM compromise | SSH keys only, ufw, fail2ban, unattended upgrades, containers non-root, Redis password + not exposed, Docker socket not mounted in app containers | bootstrap script review |
| S18 | Account deletion incomplete | `DELETE /me` purges DB rows, R2 prefixes, Supabase auth user; verified by test | test |
| S19 | Colab rules violation (account bans for users) | Notebook interactive only; no keep-alive hacks; review in launch checklist | launch checklist |
| S20 | Provider terms (training on outputs) | BYO keys (user's own terms); Gemini terms acknowledgement; docs explain | UI review |

## 3. HTTP hardening
- API: CORS allow-list, `TrustedHostMiddleware`, request size limit 1 MB (JSON bodies), security headers via Caddy (HSTS, `X-Content-Type-Options`, `Referrer-Policy`), no server banners.
- Web: CSP (`default-src 'self'; connect-src 'self' api.<domain> *.supabase.co <r2-endpoint>; img-src 'self' data: https:; frame-ancestors 'none'`), HSTS by Cloudflare.

## 4. Process
- `security-auditor` agent runs at the end of every phase and on any PR touching auth, tokens, keys, uploads, R2, notebook, CORS.
- Pre-launch: full review against this table; fix all Critical/High.
