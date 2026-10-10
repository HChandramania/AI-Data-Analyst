from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(trim(email))", name="normalized_email"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "length(token_digest) = 64 AND token_digest NOT GLOB '*[^0-9a-f]*'",
            name="sha256_digest",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    content_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20))
    original_path: Mapped[str] = mapped_column(String(255))
    parquet_path: Mapped[str] = mapped_column(String(255))
    schema_json: Mapped[str] = mapped_column(Text)
    profile_json: Mapped[str] = mapped_column(Text)
    row_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
