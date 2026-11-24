"""Cloud identity boundary. Opaque session credentials are persisted only as digests in PostgreSQL."""

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer

from .schemas import (
    ClientResponse,
    ClientTokenResponse,
    CurrentOperatorResponse,
    SessionResponse,
)

router = APIRouter(prefix="/auth/v1", tags=["operator access"])
hasher = PasswordHasher()
# A real hash keeps unknown-user and wrong-password verification on the same path.
dummy_hash = hasher.hash(secrets.token_urlsafe(32))
bearer = HTTPBearer(
    auto_error=False,
    scheme_name="OperatorBearer",
    description="Opaque operator/client token issued by POST /auth/v1/sessions or POST /auth/v1/clients.",
)
COOKIE_NAME = "myocontrol_web_session"
web_cookie = APIKeyCookie(
    name=COOKIE_NAME,
    auto_error=False,
    scheme_name="WebSession",
    description="HttpOnly browser session issued at sign-in. Cookie-authenticated mutations require X-MyoControl-Web: 1.",
)


def require_browser_header(request: Request):
    if request.headers.get("X-MyoControl-Web") != "1":
        raise HTTPException(403, "Browser request header required")


def secure_cookie(request: Request):
    return (
        request.url.scheme == "https"
        or os.environ.get("WEB_SESSION_SECURE", "").lower() == "true"
    )


@lru_cache
def engine():
    url = os.environ.get("IDENTITY_DATABASE_URL")
    if not url:
        password = os.environ.get("IDENTITY_DB_PASSWORD")
        if not password:
            raise HTTPException(503, "Operator access is not configured")
        url = URL.create(
            "postgresql+psycopg",
            username="identity_service_login",
            password=password,
            host=os.environ.get("DB_HOST", "database"),
            port=int(os.environ.get("DB_PORT", "5432")),
            database=os.environ.get("DB_NAME", "thesis"),
        )
    return create_engine(url, pool_pre_ping=True)


def digest(token: str):
    return hashlib.sha256(token.encode()).hexdigest()


def principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    cookie: str | None = Depends(web_cookie),
):
    using_cookie = credentials is None
    token = credentials.credentials if credentials else cookie or ""
    if not 32 <= len(token) <= 256:
        raise HTTPException(
            401, "Sign in required", headers={"WWW-Authenticate": "Bearer"}
        )
    with engine().connect() as connection:
        row = (
            connection.execute(
                text(
                    """SELECT v.*, o.display_name, o.role
            FROM identity.valid_session_ids v JOIN identity.access_sessions s ON s.id = v.id
            JOIN identity.operators o ON o.id = v.operator_id WHERE s.token_sha256 = :hash"""
                ),
                {"hash": digest(token)},
            )
            .mappings()
            .one_or_none()
        )
    if row is None or (using_cookie and row["scope"] != "web"):
        raise HTTPException(
            401, "Session expired or revoked", headers={"WWW-Authenticate": "Bearer"}
        )
    if using_cookie and request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_browser_header(request)
    return dict(row)


def web_principal(actor=Depends(principal)):
    if actor["scope"] != "web":
        raise HTTPException(403, "Web session required")
    return actor


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(
        min_length=1,
        max_length=1024,
        json_schema_extra={"format": "password", "writeOnly": True},
    )


@router.post("/sessions", response_model=SessionResponse)
def login(body: Login, request: Request, response: Response):
    if request.headers.get("Origin"):
        require_browser_header(request)
    with engine().begin() as connection:
        row = (
            connection.execute(
                text(
                    "SELECT * FROM identity.operators WHERE email = :email FOR UPDATE"
                ),
                {"email": body.email.strip().lower()},
            )
            .mappings()
            .one_or_none()
        )
        try:
            valid = hasher.verify(
                row["password_hash"] if row else dummy_hash, body.password
            )
        except (VerificationError, InvalidHashError):
            valid = False
        if not valid or row is None or row["state"] != "active":
            raise HTTPException(401, "Invalid email or password")
        token = secrets.token_urlsafe(48)
        expires = datetime.now(timezone.utc) + timedelta(hours=8)
        connection.execute(
            text(
                """INSERT INTO identity.access_sessions(operator_id,token_sha256,scope,expires_at)
            VALUES (:operator,:hash,'web',:expires)"""
            ),
            {"operator": row["id"], "hash": digest(token), "expires": expires},
        )
        if hasher.check_needs_rehash(row["password_hash"]):
            connection.execute(
                text("UPDATE identity.operators SET password_hash=:hash WHERE id=:id"),
                {"hash": hasher.hash(body.password), "id": row["id"]},
            )
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=8 * 60 * 60,
        expires=expires,
        httponly=True,
        secure=secure_cookie(request),
        samesite="strict",
        path="/",
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires,
        "operator": {
            "id": row["id"],
            "display_name": row["display_name"],
            "role": row["role"],
        },
    }


@router.get("/me", response_model=CurrentOperatorResponse)
def me(actor=Depends(principal)):
    return {
        key: actor[key]
        for key in (
            "operator_id",
            "display_name",
            "role",
            "scope",
            "client_id",
            "expires_at",
        )
    }


@router.delete("/sessions/current", status_code=204)
def logout(request: Request, response: Response, actor=Depends(principal)):
    with engine().begin() as connection:
        connection.execute(
            text(
                "UPDATE identity.access_sessions SET revoked_at=clock_timestamp() WHERE id=:id AND revoked_at IS NULL"
            ),
            {"id": actor["id"]},
        )
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        httponly=True,
        secure=secure_cookie(request),
        samesite="strict",
    )


class ClientCreate(BaseModel):
    kind: str = Field(pattern="^(desktop|training_worker)$")
    name: str = Field(min_length=1, max_length=120)
    platform: str = Field(min_length=1, max_length=120)


@router.post("/clients", status_code=201, response_model=ClientTokenResponse)
def register_client(
    body: ClientCreate, response: Response, actor=Depends(web_principal)
):
    if actor["role"] == "reviewer":
        raise HTTPException(403, "Reviewer access is read-only")
    if not body.name.strip() or not body.platform.strip():
        raise HTTPException(422, "Name and platform must not be blank")
    token = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    with engine().begin() as connection:
        client = connection.execute(
            text("""INSERT INTO identity.clients(operator_id,kind,name,platform)
            VALUES (:operator,:kind,:name,:platform) RETURNING id"""),
            {"operator": actor["operator_id"], **body.model_dump()},
        ).scalar_one()
        connection.execute(
            text(
                """INSERT INTO identity.access_sessions(operator_id,client_id,token_sha256,scope,expires_at)
            VALUES (:operator,:client,:hash,:scope,:expires)"""
            ),
            {
                "operator": actor["operator_id"],
                "client": client,
                "hash": digest(token),
                "scope": body.kind,
                "expires": expires,
            },
        )
    response.headers["Cache-Control"] = "no-store"
    return {
        "client_id": client,
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires,
        "scope": body.kind,
    }


@router.get("/clients", response_model=list[ClientResponse])
def list_clients(actor=Depends(web_principal)):
    with engine().connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                text(
                    """SELECT id,kind,name,platform,state,created_at
            FROM identity.clients WHERE operator_id=:operator ORDER BY created_at DESC"""
                ),
                {"operator": actor["operator_id"]},
            ).mappings()
        ]


@router.delete("/clients/{client_id}", status_code=204)
def revoke_client(client_id: UUID, actor=Depends(web_principal)):
    with engine().begin() as connection:
        found = connection.execute(
            text("""UPDATE identity.clients SET state='revoked'
            WHERE id=:id AND operator_id=:operator RETURNING id"""),
            {"id": client_id, "operator": actor["operator_id"]},
        ).scalar_one_or_none()
        if found is None:
            raise HTTPException(404, "Client not found")


def create_operator(email: str, display_name: str, password: str, role="operator"):
    """Administrative CLI only; no open registration endpoint."""
    if len(password) < 12 or len(password) > 1024:
        raise ValueError("Use a password between 12 and 1024 characters")
    with engine().begin() as connection:
        return connection.execute(
            text(
                """INSERT INTO identity.operators(email,display_name,password_hash,role)
            VALUES (:email,:name,:hash,:role) RETURNING id"""
            ),
            {
                "email": email.strip().lower(),
                "name": display_name.strip(),
                "hash": hasher.hash(password),
                "role": role,
            },
        ).scalar_one()


if __name__ == "__main__":
    import argparse
    import getpass

    parser = argparse.ArgumentParser(description="Create a cloud operator")
    parser.add_argument("email")
    parser.add_argument("display_name")
    parser.add_argument(
        "--role", choices=["operator", "reviewer", "administrator"], default="operator"
    )
    args = parser.parse_args()
    password = getpass.getpass("Password (12+ characters): ")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match")
    try:
        print(create_operator(args.email, args.display_name, password, args.role))
    except SQLAlchemyError:
        raise SystemExit(
            "Could not create operator; check database access and email uniqueness"
        ) from None
