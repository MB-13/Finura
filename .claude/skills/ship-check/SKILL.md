---
name: ship-check
description: Pre-commit / pre-merge verification for DocTune - lint, types, tests and build for frontend/ and backend/, OpenAPI types drift, notebook smoke test when touched, plus code and security review of the diff. Use before committing, opening a PR or deploying.
---

# Ship check

Run only the parts whose directories changed (`git diff --name-only`); stop at the first hard failure.

**backend/**
1. `uv run ruff check . && uv run ruff format --check .`
2. `uv run mypy src`
3. `uv run pytest`
4. Alembic: models and migrations in sync (`uv run alembic check` if configured)

**frontend/**
5. API types drift: regenerate (see `sync-api-types`) and confirm no diff
6. `pnpm lint && pnpm typecheck`
7. `pnpm test`
8. `pnpm build`

**notebook/** (if touched)
9. Smoke + resume tests

**Review**
10. **code-reviewer** on the diff.
11. **security-auditor** if the diff touches auth, job tokens, LLM keys, uploads, R2 URLs, the notebook, or CORS/rate limits.

## Report
```
api   ruff ✅/❌  mypy ✅/❌  pytest ✅/❌ (n/n)  alembic ✅/❌/skipped
web   types-drift ✅/❌  lint ✅/❌  typecheck ✅/❌  test ✅/❌  build ✅/❌
nb    smoke ✅/❌/skipped
Review   n blockers, n should-fix
Security n findings / skipped
Verdict: Ready / Not ready — <why>
```
Never mark something as passing that wasn't actually run.
