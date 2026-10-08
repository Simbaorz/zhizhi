"""Portal-owned records; platform tables are never migrated by this app."""

import time
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "portal_account"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    email: Mapped[str] = mapped_column(String(320), default="")
    password_hash: Mapped[str] = mapped_column(String(512))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    scopes: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)

    def public(self, *, admin: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "email": self.email,
        }
        if admin:
            result.update(active=self.active, scopes=self.scopes)
        return result


class BrowserSession(Base):
    __tablename__ = "portal_browser_session"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(64), index=True)
    admin: Mapped[bool] = mapped_column(Boolean)
    token_version: Mapped[int] = mapped_column(Integer)
    csrf: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[float] = mapped_column(Float)


class LoginAttempt(Base):
    __tablename__ = "portal_login_attempt"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[float] = mapped_column(Float, default=time.time)


class Conversation(Base):
    __tablename__ = "portal_conversation"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("portal_account.id"), index=True)
    scope_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(128), default="新对话")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)
