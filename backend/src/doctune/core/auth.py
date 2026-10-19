import json
import uuid
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
import structlog
from fastapi import Depends, Request
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from doctune.core.config import Settings, get_settings
from doctune.core.db import get_session
from doctune.core.errors import Unauthorized
from doctune.models.user import User

log = structlog.get_logger()

ASYMMETRIC_ALGS = ["RS256", "ES256"]


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    email: str | None


class TokenVerifier:
    """Verifies Supabase access tokens: asymmetric signing keys via JWKS (ES256/RS256) and, when configured,
    the legacy HS256 secret. Both are accepted at once because Supabase projects switching to signing keys
    can issue either kind during the migration."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._jwk_client: jwt.PyJWKClient | None = None
        self._static_jwks: jwt.PyJWKSet | None = None
        if settings.jwt_jwks_json:
            self._static_jwks = jwt.PyJWKSet.from_dict(json.loads(settings.jwt_jwks_json))
        else:
            self._jwk_client = jwt.PyJWKClient(settings.jwks_url, cache_keys=True, lifespan=600)

    def _key_for(self, token: str) -> tuple[Any, list[str]]:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")
        if alg == "HS256":
            if not self.settings.supabase_jwt_secret:
                log.warning("jwt_hs256_without_secret", hint="set SUPABASE_JWT_SECRET (Supabase legacy JWT secret)")
                raise Unauthorized(
                    self._explain(
                        "Your Supabase project signs sessions with its legacy JWT secret (HS256). "
                        "Set SUPABASE_JWT_SECRET in backend/.env "
                        "(Supabase → Project Settings → JWT Keys → Legacy JWT Secret) and restart the API."
                    )
                )
            return self.settings.supabase_jwt_secret.get_secret_value(), ["HS256"]
        if alg not in ASYMMETRIC_ALGS:
            log.warning("jwt_unsupported_alg", alg=alg)
            raise Unauthorized(self._explain(f"Unsupported token signing algorithm: {alg}."))
        if self._static_jwks is not None:
            kid = header.get("kid")
            for key in self._static_jwks.keys:
                if key.key_id == kid:
                    return key.key, ASYMMETRIC_ALGS
            raise Unauthorized("Unknown signing key")
        if self._jwk_client is None:
            raise Unauthorized(self._explain(f"No signing keys configured for {alg} tokens."))
        return self._jwk_client.get_signing_key_from_jwt(token).key, ASYMMETRIC_ALGS

    def _explain(self, detail: str) -> str:
        """Configuration hints help locally; production only says the token is unsupported."""
        return detail if self.settings.env in ("local", "test") else "Unsupported token"

    def verify(self, token: str) -> dict[str, Any]:
        try:
            key, algorithms = self._key_for(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=algorithms,
                audience=self.settings.supabase_jwt_aud,
                issuer=self.settings.jwt_issuer,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
        except Unauthorized:
            raise
        except jwt.ExpiredSignatureError as exc:
            raise Unauthorized("Session expired", code="token_expired") from exc
        except (jwt.PyJWTError, ValueError) as exc:
            log.info("jwt_rejected", reason=type(exc).__name__)
            raise Unauthorized("Invalid token") from exc
        return claims


def get_verifier(request: Request) -> TokenVerifier:
    verifier: TokenVerifier | None = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        verifier = TokenVerifier(get_settings())
        request.app.state.token_verifier = verifier
    return verifier


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthorized()
    return token


async def current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    verifier: Annotated[TokenVerifier, Depends(get_verifier)],
) -> CurrentUser:
    token = _bearer(request)
    # PyJWKClient may fetch keys over the network, so keep it off the event loop
    claims = await run_in_threadpool(verifier.verify, token)
    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except ValueError as exc:
        raise Unauthorized("Invalid token") from exc
    email = claims.get("email")

    # first request from a new Supabase user creates their row; email follows Supabase
    stmt = (
        insert(User)
        .values(id=user_id, email=email)
        .on_conflict_do_update(
            index_elements=[User.id], set_={"email": email}, where=User.email.is_distinct_from(email)
        )
    )
    await session.execute(stmt)
    await session.commit()
    structlog.contextvars.bind_contextvars(user_id=str(user_id))
    return CurrentUser(id=user_id, email=email)


CurrentUserDep = Annotated[CurrentUser, Depends(current_user)]
