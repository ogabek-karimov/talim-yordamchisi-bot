"""Database models."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


# --- enums as plain string constants ---------------------------------------
class Role:
    OWNER = "owner"
    ADMIN = "admin"
    USER = "user"
    ALL = (OWNER, ADMIN, USER)
    STAFF = (OWNER, ADMIN)


class Status:
    PENDING = "pending"
    APPROVED = "approved"
    BLOCKED = "blocked"


class AppStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# --- users ----------------------------------------------------------------
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(8), default="uz")
    role: Mapped[str] = mapped_column(String(16), default=Role.USER, index=True)
    status: Mapped[str] = mapped_column(String(16), default=Status.PENDING, index=True)
    subscription_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[int | None] = mapped_column(BigInteger)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def full_name(self) -> str:
        parts = [p for p in (self.first_name, self.last_name) if p]
        return " ".join(parts) or (f"@{self.username}" if self.username else str(self.tg_id))

    @property
    def is_staff(self) -> bool:
        return self.role in Role.STAFF

    @property
    def is_owner(self) -> bool:
        return self.role == Role.OWNER

    @property
    def is_approved(self) -> bool:
        return self.status == Status.APPROVED

    def subscription_active(self, now: datetime | None = None) -> bool:
        if self.subscription_until is None:
            return False
        now = now or utcnow()
        until = self.subscription_until
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return until > now


# --- applications -------------------------------------------------------
class Application(Base, TimestampMixin):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str] = mapped_column(String(256))
    phone: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(8), default="uz")
    status: Mapped[str] = mapped_column(String(16), default=AppStatus.PENDING, index=True)
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String(512))


# --- settings (KV) ----------------------------------------------------
class Setting(Base, TimestampMixin):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)


# --- test bank -------------------------------------------------------
class Subject(Base, TimestampMixin):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name_i18n: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)

    test_sets: Mapped[list["TestSet"]] = relationship(
        back_populates="subject", cascade="all, delete-orphan"
    )


class TestSet(Base, TimestampMixin):
    __tablename__ = "test_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), index=True
    )
    title_i18n: Mapped[dict] = mapped_column(JSON, default=dict)
    description_i18n: Mapped[dict] = mapped_column(JSON, default=dict)
    time_limit_sec: Mapped[int] = mapped_column(Integer, default=0)  # 0 = no limit
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int | None] = mapped_column(BigInteger)

    subject: Mapped[Subject] = relationship(back_populates="test_sets")
    questions: Mapped[list["Question"]] = relationship(
        back_populates="test_set",
        cascade="all, delete-orphan",
        order_by="Question.order",
    )


class Question(Base, TimestampMixin):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_set_id: Mapped[int] = mapped_column(
        ForeignKey("test_sets.id", ondelete="CASCADE"), index=True
    )
    order: Mapped[int] = mapped_column(Integer, default=0)
    body_i18n: Mapped[dict] = mapped_column(JSON, default=dict)
    options_i18n: Mapped[dict] = mapped_column(JSON, default=dict)  # {lang: [opt, ...]}
    correct_index: Mapped[int] = mapped_column(Integer, default=0)
    explanation_i18n: Mapped[dict] = mapped_column(JSON, default=dict)
    image_url: Mapped[str | None] = mapped_column(String(512))

    test_set: Mapped[TestSet] = relationship(back_populates="questions")


class Attempt(Base, TimestampMixin):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    test_set_id: Mapped[int] = mapped_column(ForeignKey("test_sets.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)  # {question_id: chosen_index}


# --- payments -------------------------------------------------------
class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    telegram_payment_charge_id: Mapped[str] = mapped_column(String(128), unique=True)
    stars_amount: Mapped[int] = mapped_column(Integer, default=0)
    plan_key: Mapped[str] = mapped_column(String(32), default="")
    days: Mapped[int] = mapped_column(Integer, default=0)
    refunded: Mapped[bool] = mapped_column(Boolean, default=False)


# --- ai usage (rate-limit ledger) --------------------------------
class AiUsage(Base):
    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(24), default="homework")
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


# --- audit log -----------------------------------------------------
class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_tg_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str | None] = mapped_column(String(128))
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


__all__ = [
    "Role",
    "Status",
    "AppStatus",
    "utcnow",
    "User",
    "Application",
    "Setting",
    "Subject",
    "TestSet",
    "Question",
    "Attempt",
    "Payment",
    "AiUsage",
    "AuditLog",
]
