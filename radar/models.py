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
    merged_from_id: Mapped[int | None] = mapped_column(
        ForeignKey("procedure.id", ondelete="SET NULL"), nullable=True, index=True
    )
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
    crm_deal: Mapped[CrmDeal | None] = relationship(back_populates="procedure", uselist=False)


class LotItem(Base):
    __tablename__ = "lot_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    procedure_id: Mapped[int] = mapped_column(
        ForeignKey("procedure.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_name: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(Text, index=True)
    product_family: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    term_months: Mapped[int | None] = mapped_column(Integer)
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
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    procedure: Mapped[Procedure] = relationship(back_populates="classification")


class RenewalOpportunity(Base):
    __tablename__ = "renewal_opportunity"
    __table_args__ = (
        UniqueConstraint("procedure_id", name="uq_renewal_procedure"),
        UniqueConstraint("customer_org_id", "procedure_id", name="uq_renewal_customer_procedure"),
    )
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


class CrmDeal(Base):
    """CRM Deal synchronized with Bitrix24.

    Strictly idempotent: exactly one deal per procedure (procedure_id is unique).
    """

    __tablename__ = "crm_deal"
    __table_args__ = (UniqueConstraint("procedure_id", name="uq_crm_deal_procedure"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    procedure_id: Mapped[int] = mapped_column(
        ForeignKey("procedure.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    deal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CREATED")
    bitrix_response: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    procedure: Mapped[Procedure] = relationship(back_populates="crm_deal")
    customer: Mapped[Organization | None] = relationship()


class CrmTask(Base):
    """Internal CRM sales tasks and proposals."""

    __tablename__ = "crm_task"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization.id", ondelete="SET NULL"), index=True
    )
    procedure_id: Mapped[int | None] = mapped_column(
        ForeignKey("procedure.id", ondelete="SET NULL"), index=True
    )
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, default="TAKTAK_TAYYORLASH")
    task_title: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_staff_id: Mapped[str | None] = mapped_column(String(64))
    assigned_staff_name: Mapped[str | None] = mapped_column(String(128))
    proposal_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="YANGI")
    bitrix_deal_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    customer: Mapped[Organization | None] = relationship()
    procedure: Mapped[Procedure | None] = relationship()


class User(Base):
    """System user for authentication and role-based access control."""

    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="viewer"
    )  # 'admin' | 'sales' | 'viewer'
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExportLog(Base):
    """Audit log of data export actions by authenticated users."""

    __tablename__ = "export_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    export_type: Mapped[str] = mapped_column(String(16), nullable=False)  # 'xlsx' | 'pdf'
    filter_json: Mapped[dict | None] = mapped_column(JSONB)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user: Mapped[User] = relationship()


class AuditLog(Base):
    """Audit log of sensitive security and privacy actions."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    user: Mapped[User] = relationship()


class AlertLog(Base):
    """Log of dispatched alerts (e.g. Telegram notifications) for idempotency."""

    __tablename__ = "alert_log"
    __table_args__ = (
        UniqueConstraint(
            "procedure_id",
            "channel",
            "recipient",
            name="uq_alert_procedure_channel_recipient",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    procedure_id: Mapped[int] = mapped_column(
        ForeignKey("procedure.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="telegram")
    recipient: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    score: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="sent")
    message_preview: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    procedure: Mapped[Procedure] = relationship()


Index(
    "ix_organization_alias_name_trgm",
    OrganizationAlias.name_raw,
    postgresql_using="gin",
    postgresql_ops={"name_raw": "gin_trgm_ops"},
)
