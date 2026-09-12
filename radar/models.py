"""SQLAlchemy 2 models mirroring docs/SPEC.md and docs/DATABASE.md."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organization"
    id: Mapped[int] = mapped_column(primary_key=True)
    stir: Mapped[str | None] = mapped_column(String(32), unique=True)
    name_canonical: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    aliases: Mapped[list[OrganizationAlias]] = relationship(back_populates="organization")


class OrganizationAlias(Base):
    __tablename__ = "organization_alias"
    __table_args__ = (UniqueConstraint("org_id", "name_raw", name="uq_org_alias"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False)
    name_raw: Mapped[str] = mapped_column(Text, nullable=False)
    organization: Mapped[Organization] = relationship(back_populates="aliases")


class RawSnapshot(Base):
    __tablename__ = "raw_snapshot"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    body: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # zstd-compressed JSON


class Procedure(Base):
    __tablename__ = "procedure"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_procedure_source_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="uzex")
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    procedure_type: Mapped[str | None] = mapped_column(Text)
    customer_org_id: Mapped[int | None] = mapped_column(ForeignKey("organization.id"))
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str | None] = mapped_column(String(8))
    start_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    raw_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("raw_snapshot.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    customer: Mapped[Organization | None] = relationship()
    items: Mapped[list[LotItem]] = relationship(
        back_populates="procedure", cascade="all, delete-orphan"
    )
    classification: Mapped[Classification | None] = relationship(back_populates="procedure")
    award: Mapped[Award | None] = relationship(back_populates="procedure")


class LotItem(Base):
    __tablename__ = "lot_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    procedure_id: Mapped[int] = mapped_column(
        ForeignKey("procedure.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_name: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 3))
    unit: Mapped[str | None] = mapped_column(Text)
    unit_price_raw: Mapped[str | None] = mapped_column(Text)
    procedure: Mapped[Procedure] = relationship(back_populates="items")


class Award(Base):
    __tablename__ = "award"
    procedure_id: Mapped[int] = mapped_column(
        ForeignKey("procedure.id", ondelete="CASCADE"), primary_key=True
    )
    supplier_org_id: Mapped[int | None] = mapped_column(ForeignKey("organization.id"))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    awarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    procedure: Mapped[Procedure] = relationship(back_populates="award")
    supplier: Mapped[Organization | None] = relationship()


class Classification(Base):
    __tablename__ = "classification"
    procedure_id: Mapped[int] = mapped_column(
        ForeignKey("procedure.id", ondelete="CASCADE"), primary_key=True
    )
    is_it: Mapped[bool] = mapped_column(Boolean, nullable=False)
    category: Mapped[str | None] = mapped_column(Text, index=True)
    subcategory: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(Text)
    model_hint: Mapped[str | None] = mapped_column(Text)
    is_subscription: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    term_months: Mapped[int | None] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(8), nullable=False)  # 'rule' | 'ai'
    model_name: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    procedure: Mapped[Procedure] = relationship(back_populates="classification")


class RenewalOpportunity(Base):
    __tablename__ = "renewal_opportunity"
    __table_args__ = (UniqueConstraint("procedure_id", name="uq_renewal_procedure"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_org_id: Mapped[int | None] = mapped_column(ForeignKey("organization.id"), index=True)
    procedure_id: Mapped[int] = mapped_column(
        ForeignKey("procedure.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(Text)
    last_purchase_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifecycle_months: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_renewal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contact_by_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    customer: Mapped[Organization | None] = relationship()
    procedure: Mapped[Procedure] = relationship()


class ImportCursor(Base):
    __tablename__ = "import_cursor"
    job_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_page: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_source_id: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AiCache(Base):
    __tablename__ = "ai_cache"
    input_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    response_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AiCostLedger(Base):
    """Durable cross-run cost ledger for the $10 classifier cap (DECISIONS.md).

    A row is inserted as a reservation (settled=false) *before* the API call and
    settled with actual token usage afterwards. Budget = sum(reserved or actual).
    """

    __tablename__ = "ai_cost_ledger"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    batch_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    estimated_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    actual_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    settled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="reserved")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


Index("ix_organization_alias_name_trgm", OrganizationAlias.name_raw,
      postgresql_using="gin", postgresql_ops={"name_raw": "gin_trgm_ops"})
