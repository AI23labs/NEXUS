"""
Multi-user Google OAuth2: login, callback, session cookie. Production standards.
Refresh token stored encrypted at rest; Pydantic validates callback params.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import structlog
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.crypto import decrypt_refresh_token, encrypt_refresh_token
from app.core.database import User, get_session_factory

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
SCOPE_CALENDAR = "https://www.googleapis.com/auth/calendar.events"
SCOPE_EMAIL = "https://www.googleapis.com/auth/userinfo.email"
SCOPE_PROFILE = "https://www.googleapis.com/auth/userinfo.profile"
SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE = 86400 * 30  # 30 days


# ----- Pydantic: OAuth callback params -----


class OAuthCallbackQuery(BaseModel):
    """Validated query params for GET /callback. Prevents open redirect / code injection."""

    code: str = Field(..., min_length=1, max_length=2000, description="Authorization code from Google")
    state: str | None = Field(None, max_length=512, description="Optional CSRF state")

    model_config = {"extra": "forbid"}


# ----- Session cookie: sign and verify -----


def _sign_session(user_id: str, secret: str) -> str:
    """Produce signed value: base64(user_id:hmac)."""
    raw = f"{user_id}"
    sig = hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()
    payload = f"{user_id}:{sig}"
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _verify_session(cookie_value: str, secret: str) -> str | None:
    """Verify and return user_id or None."""
    if not cookie_value or len(cookie_value) > 1024:
        return None
    try:
        payload = base64.urlsafe_b64decode(cookie_value.encode("ascii")).decode("utf-8")
        user_id, sig = payload.rsplit(":", 1)
        expected = hmac.new(secret.encode("utf-8"), user_id.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        return user_id
    except Exception:
        return None


# ----- Routes -----


@router.get("/login")
async def auth_login(request: Request) -> Response:
    """
    Redirect user to Google OAuth consent screen.
    access_type=offline & prompt=consent to obtain refresh token.
    """
    settings = get_settings()
    if not (settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET):
        raise HTTPException(
            status_code=503,
            detail="Google OAuth not configured. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env",
        )
    # Always use redirect_uri from env (never request.url_for) so it is correct behind HTTPS proxies (e.g. ngrok).
    redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI
    state = secrets.token_urlsafe(32)
    # Request calendar + email/profile so we can create the user and access Calendar
    scopes = " ".join([SCOPE_EMAIL, SCOPE_PROFILE, SCOPE_CALENDAR])
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    import urllib.parse
    qs = urllib.parse.urlencode(params)
    url = f"{GOOGLE_AUTH_URL}?{qs}"
    logger.info("auth_login_redirect", event_type="auth")
    return Response(status_code=302, headers={"Location": url})


@router.get("/callback")
async def auth_callback(
    response: Response,
    code: Annotated[str, Query(alias="code")] = "",
    state: Annotated[str | None, Query(alias="state")] = None,
) -> Response:
    """
    Exchange authorization code for tokens. Upsert user with encrypted refresh_token.
    Set secure HTTP-only session cookie.
    """
    # Missing code (e.g. ngrok interstitial, or user opened callback URL without coming from Google) -> redirect to login
    if not (code and code.strip()):
        logger.warning("auth_callback_missing_code", event_type="auth")
        return Response(status_code=302, headers={"Location": "/api/auth/login"})
    # Pydantic validate callback params
    query = OAuthCallbackQuery(code=code.strip(), state=state)
    settings = get_settings()
    if not (settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET):
        raise HTTPException(
            status_code=503,
            detail="Google OAuth not configured. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env",
        )

    # redirect_uri must match the value used at login; always from settings (correct behind ngrok).
    import asyncio
    import urllib.parse

    import httpx

    async def _exchange():
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": query.code,
                    "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                    "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if r.status_code >= 400:
                logger.warning("oauth_token_exchange_failed", status=r.status_code, body=r.text, event_type="auth")
                return None, None
            data = r.json()
            return data.get("refresh_token"), data.get("access_token")

    refresh_token, access_token = await _exchange()
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Failed to obtain refresh token from Google")

    # User info (email) via access token
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if r.status_code >= 400:
            logger.warning("oauth_userinfo_failed", status=r.status_code, event_type="auth")
            raise HTTPException(status_code=400, detail="Failed to fetch user info")
        userinfo = r.json()
    email = (userinfo.get("email") or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="Google account has no email")

    # Encrypt refresh token and upsert user
    encrypted = encrypt_refresh_token(refresh_token, settings.ENCRYPTION_KEY)
    factory = get_session_factory()
    user_id_raw = None
    async with factory() as session:
        stmt = (
            insert(User)
            .values(
                email=email,
                google_refresh_token=encrypted,
                created_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_update(
                index_elements=["email"],
                set_={"google_refresh_token": encrypted},
            )
            .returning(User.id)
        )
        r = await session.execute(stmt)
        row = r.one_or_none()
        await session.commit()
        user_id_raw = row[0] if row else None
    if not user_id_raw:
        raise HTTPException(status_code=500, detail="User upsert failed")
    user_id_str = str(user_id_raw)

    cookie_value = _sign_session(user_id_str, settings.SESSION_SECRET_KEY)
    response = Response(status_code=302, headers={"Location": "/docs"})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_value,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
    )
    logger.info("auth_callback_success", user_id=user_id_str, email=email, event_type="auth", timestamp_ms=round(datetime.now(timezone.utc).timestamp() * 1000))
    return response


def get_current_user_id(request: Request) -> str | None:
    """Read session cookie and return user_id or None. Use in Depends for protected routes."""
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        return None
    return _verify_session(cookie, get_settings().SESSION_SECRET_KEY)
