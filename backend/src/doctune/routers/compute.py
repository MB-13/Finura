from fastapi import APIRouter, Depends, status

from doctune.core.auth import CurrentUserDep
from doctune.core.crypto import encrypt, mask
from doctune.core.errors import NotFound
from doctune.core.ratelimit import limit
from doctune.models.compute import ComputeAccount, ComputeStatus
from doctune.routers.deps import DB
from doctune.schemas.compute import KaggleAccountOut, KaggleAccountPut
from doctune.services import compute as compute_service

router = APIRouter(prefix="/compute", tags=["compute"])


@router.get("/kaggle", response_model=KaggleAccountOut | None)
async def get_kaggle(user: CurrentUserDep, db: DB) -> KaggleAccountOut | None:
    account = await compute_service.get_kaggle(db, user.id)
    return compute_service.kaggle_out(account) if account else None


@router.put("/kaggle", response_model=KaggleAccountOut, dependencies=[Depends(limit("put_kaggle", 10))])
async def put_kaggle(body: KaggleAccountPut, user: CurrentUserDep, db: DB) -> KaggleAccountOut:
    """Save the user's Kaggle username and API token (encrypted); a worker then validates it with Kaggle."""
    from doctune.workers.tasks.kaggle import check_kaggle_account

    account = await compute_service.get_kaggle(db, user.id)
    if account is None:
        account = ComputeAccount(user_id=user.id, provider=compute_service.KAGGLE)
        db.add(account)
    account.username = body.username.lower()
    account.ciphertext = encrypt(body.api_token)
    account.last4 = mask(body.api_token)
    account.status = ComputeStatus.unchecked
    account.status_message = None
    account.gpu_used_s = account.gpu_total_s = account.quota_refresh_at = account.checked_at = None
    await db.commit()
    check_kaggle_account.delay(str(user.id))
    await db.refresh(account)
    return compute_service.kaggle_out(account)


@router.post(
    "/kaggle/check",
    response_model=KaggleAccountOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(limit("check_kaggle", 20))],
)
async def check_kaggle(user: CurrentUserDep, db: DB) -> KaggleAccountOut:
    from doctune.workers.tasks.kaggle import check_kaggle_account

    account = await compute_service.get_kaggle(db, user.id)
    if account is None:
        raise NotFound("No Kaggle account is connected")
    check_kaggle_account.delay(str(user.id))
    await db.refresh(account)
    return compute_service.kaggle_out(account)


@router.delete("/kaggle", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kaggle(user: CurrentUserDep, db: DB) -> None:
    account = await compute_service.get_kaggle(db, user.id)
    if account is None:
        raise NotFound("No Kaggle account is connected")
    await db.delete(account)
    await db.commit()
