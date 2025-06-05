# backend/app/infrastructure/db/models.py
# VERSI: Penyesuaian nama ENUM dan penambahan inherit_schema.
# PEMBARUAN: Perbesar kolom transactions.hotspot_password

import uuid
import enum
import datetime # Pastikan datetime diimpor
from typing import List, Optional

from sqlalchemy import (
    Text, DateTime, Numeric, func, Boolean,
    ForeignKey, Index, UniqueConstraint, Enum as SQLAlchemyEnum,
    BigInteger, Date, String
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import expression
import sqlalchemy as sa

from app.extensions import db

class UserRole(enum.Enum):
    USER = "USER"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"

class ApprovalStatus(enum.Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class UserBlok(enum.Enum):
    A = "A"; B = "B"; C = "C"; D = "D"; E = "E"; F = "F"

class UserKamar(enum.Enum):
    Kamar_1 = "1"
    Kamar_2 = "2"
    Kamar_3 = "3"
    Kamar_4 = "4"
    Kamar_5 = "5"
    Kamar_6 = "6"

class TransactionStatus(enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"

class Package(db.Model):
    __tablename__ = 'packages'
    __table_args__ = (
        UniqueConstraint('name', name='uq_packages_name'),
        Index('ix_packages_name', 'name', unique=True),
        Index('ix_packages_mikrotik_profile_name', 'mikrotik_profile_name'),
        {'extend_existing': True}
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[int] = mapped_column(Numeric(10, 0), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_quota_mb: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    speed_limit_kbps: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    mikrotik_profile_name: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=expression.true())
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="package", lazy="select")

    def __repr__(self):
        return f'<Package id={self.id} name={self.name}>'

class User(db.Model):
    __tablename__ = 'users'
    __table_args__ = (
        UniqueConstraint('phone_number', name='uq_users_phone_number'),
        Index('ix_users_phone_number', 'phone_number', unique=True),
        {'extend_existing': True}
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number: Mapped[str] = mapped_column(String(25), nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True) # Password login portal
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)

    blok: Mapped[Optional[UserBlok]] = mapped_column(
        SQLAlchemyEnum(
            UserBlok,
            name="userblokenum",
            create_type=True,
            values_callable=lambda obj: [e.value for e in obj],
            inherit_schema=True
        ),
        nullable=True
    )

    kamar: Mapped[Optional[UserKamar]] = mapped_column(
        SQLAlchemyEnum(
            UserKamar,
            name="userkamarenum",
            create_type=True,
            values_callable=lambda obj: [e.value for e in obj],
            inherit_schema=True
        ),
        nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=expression.false())

    role: Mapped[UserRole] = mapped_column(
        SQLAlchemyEnum(
            UserRole,
            name="user_role_enum",
            create_type=True,
            values_callable=lambda obj: [e.value for e in obj],
            inherit_schema=True
        ),
        nullable=False,
        default=UserRole.USER,
        server_default=sa.text(f"'{UserRole.USER.value}'::user_role_enum")
    )

    approval_status: Mapped[ApprovalStatus] = mapped_column(
        SQLAlchemyEnum(
            ApprovalStatus,
            name="approval_status_enum",
            create_type=True,
            values_callable=lambda obj: [e.value for e in obj],
            inherit_schema=True
        ),
        nullable=False,
        default=ApprovalStatus.PENDING_APPROVAL,
        server_default=sa.text(f"'{ApprovalStatus.PENDING_APPROVAL.value}'::approval_status_enum")
    )

    mikrotik_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True) # Untuk password hotspot (6 digit angka plain text)
    total_quota_purchased_mb: Mapped[int] = mapped_column(BigInteger(), nullable=False, default=0, server_default='0')
    total_quota_used_mb: Mapped[int] = mapped_column(BigInteger(), nullable=False, default=0, server_default='0')

    device_brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    device_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    raw_user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    approved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', name='fk_users_approved_by_id_users'), nullable=True)
    rejected_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', name='fk_users_rejected_by_id_users'), nullable=True)
    last_login_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction",
        back_populates="user",
        lazy="select",
        cascade="all, delete-orphan"
    )
    daily_usage_logs: Mapped[List["DailyUsageLog"]] = relationship(
        "DailyUsageLog",
        back_populates="user",
        lazy="dynamic", # Menggunakan lazy="dynamic" agar bisa di-filter lebih lanjut
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f'<User id={self.id} phone={self.phone_number}>'

    @property
    def is_admin_role(self) -> bool: # type: ignore
        return self.role == UserRole.ADMIN or self.role == UserRole.SUPER_ADMIN

    @property
    def is_super_admin_role(self) -> bool: # type: ignore
        return self.role == UserRole.SUPER_ADMIN

    @property
    def is_approved(self) -> bool: # type: ignore
        return self.approval_status == ApprovalStatus.APPROVED

class Transaction(db.Model):
    __tablename__ = 'transactions'
    __table_args__ = (
        UniqueConstraint('midtrans_order_id', name='uq_transactions_midtrans_order_id'),
        Index('ix_transactions_midtrans_order_id', 'midtrans_order_id', unique=True),
        Index('ix_transactions_user_id', 'user_id'),
        Index('ix_transactions_package_id', 'package_id'),
        Index('ix_transactions_status', 'status'),
        Index('ix_transactions_midtrans_transaction_id', 'midtrans_transaction_id'),
        {'extend_existing': True}
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL', name='fk_transactions_user_id_users'),
        nullable=True
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('packages.id', ondelete='RESTRICT', name='fk_transactions_package_id_packages'),
        nullable=False
    )
    midtrans_order_id: Mapped[str] = mapped_column(String(100), nullable=False)
    midtrans_transaction_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    snap_token: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    snap_redirect_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    amount: Mapped[int] = mapped_column(Numeric(10, 0), nullable=False)

    status: Mapped[TransactionStatus] = mapped_column(
        SQLAlchemyEnum(
            TransactionStatus,
            name="transaction_status_enum",
            create_type=True,
            values_callable=lambda obj: [e.value for e in obj],
            inherit_schema=True
        ),
        nullable=False,
        default=TransactionStatus.PENDING,
        server_default=sa.text(f"'{TransactionStatus.PENDING.value}'::transaction_status_enum")
    )

    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expiry_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    va_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    biller_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    qr_code_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    hotspot_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True) # DIPERBESAR
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="transactions", lazy="select")
    package: Mapped["Package"] = relationship("Package", back_populates="transactions", lazy="select")

    def __repr__(self):
        status_repr = self.status.name if isinstance(self.status, enum.Enum) else self.status
        return f'<Transaction id={self.id} order_id={self.midtrans_order_id} status={status_repr}>'

class DailyUsageLog(db.Model):
    __tablename__ = 'daily_usage_logs'
    __table_args__ = (
        UniqueConstraint('user_id', 'log_date', name='uq_daily_usage_logs_user_log_date'),
        Index('ix_daily_usage_logs_user_id_log_date', 'user_id', 'log_date'),
        Index('ix_daily_usage_logs_user_id', 'user_id'),
        Index('ix_daily_usage_logs_log_date', 'log_date'),
        {'extend_existing': True}
    )
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE', name='fk_daily_usage_logs_user_id_users'),
        nullable=False
    )
    log_date: Mapped[datetime.date] = mapped_column(Date, nullable=False) # Menggunakan datetime.date
    usage_mb: Mapped[float] = mapped_column(Numeric(precision=15, scale=2), nullable=False, default=0.0, server_default='0.0')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="daily_usage_logs", lazy="select")

    def __repr__(self):
        return f'<DailyUsageLog user={self.user_id} date={self.log_date} usage={self.usage_mb:.2f}MB>'

class UserLoginHistory(db.Model):
    __tablename__ = 'user_login_history'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    login_time: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True) # Cukup untuk IPv4 dan IPv6
    user_agent_string: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Anda bisa menambahkan kolom 'status' (berhasil/gagal) jika ingin mencatat percobaan login juga

    user: Mapped["User"] = relationship("User") # Tambahkan relasi jika perlu

    def __repr__(self):
        return f'<UserLoginHistory user_id={self.user_id} time={self.login_time}>'