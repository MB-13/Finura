---
name: api-endpoint
description: Create or modify a FastAPI endpoint in backend/ - router, Pydantic request/response models, auth dependency (Supabase user or notebook job token), ownership check, service call, enqueue Celery task, tests. Use for any new or changed HTTP endpoint.
argument-hint: "[router] [method path]"
---

# API endpoint

Target: $ARGUMENTS. Load `backend-conventions` first.

## Template
```py
# backend/src/doctune/routers/datasets.py
from fastapi import APIRouter, Depends, status
from doctune.core.auth import CurrentUser, current_user
from doctune.core.db import Session, get_session
from doctune.schemas.datasets import StartGenerationIn, ProjectOut
from doctune.services import projects as project_service
from doctune.workers.tasks.generate import generate_full_dataset

router = APIRouter(prefix="/projects/{project_id}/dataset", tags=["datasets"])

@router.post("/generate", response_model=ProjectOut, status_code=status.HTTP_202_ACCEPTED)
async def start_generation(
    project_id: str,
    body: StartGenerationIn,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> ProjectOut:
    project = await project_service.get_owned(db, project_id, user.id)        # 404 if not owner
    project = await project_service.transition(db, project, "generating", actor="user")
    generate_full_dataset.delay(project.id)                                    # slow work → worker
    return ProjectOut.model_validate(project)
```

## Checklist
- [ ] Right auth mode: `current_user` (web) or `current_job` (notebook `/jobs/current/*`) — never both
- [ ] Ownership/scope checked in the service, not just "logged in"
- [ ] Request and `response_model` are Pydantic; no ORM objects leak
- [ ] No slow work in the request; enqueue and return 202 where appropriate
- [ ] Status via `transition()` only
- [ ] Caps enforced (20 MB/file, 50 MB/project, 2,000 pairs) where relevant
- [ ] Files via R2 pre-signed URLs, never proxied
- [ ] No secrets in responses or logs (mask LLM keys)
- [ ] Explicit error codes (400/401/403/404/409/413/422/429)
- [ ] pytest: success, invalid, unauthenticated, other user's resource, bad status edge
- [ ] Contract changed → run `/sync-api-types`
