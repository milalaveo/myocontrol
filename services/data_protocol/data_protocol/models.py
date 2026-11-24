"""Relational entities owned by the data and protocol service."""

import uuid

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = {"schema": "data_protocol"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pseudonym: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class Recording(Base):
    __tablename__ = "recordings"
    __table_args__ = {"schema": "data_protocol"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    participant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_protocol.participants.id"), nullable=False)
    sample_rate_hz: Mapped[float] = mapped_column(Numeric, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="4")


class SyntheticSplit(Base):
    __tablename__ = "synthetic_splits"
    __table_args__ = {"schema": "data_protocol"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_recording_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_protocol.recordings.id"), nullable=False)
    test_recording_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_protocol.recordings.id"), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
