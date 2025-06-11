# backend/app/infrastructure/db/models.py
import uuid
import enum
import datetime
from typing import List, Optional

from sqlalchemy import (
    Text, DateTime, Numeric, func, Boolean,
    ForeignKey, Index, UniqueConstraint, Enum as SQLAlchemyEnum,
    BigInteger, Date, String, Integer
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import expression
import sqlalchemy as sa

from app.extensions import db

# --- Definisi Enum (Tetap ada untuk digunakan di Pydantic & Logika Aplikasi) ---
class UserRole(enum.Enum):
    USER = "USER"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"

class ApprovalStatus(enum.Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class UserBlok(enum.Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"

class UserKamar(enum.Enum):
    Kamar_1 = "Kamar_1"
    Kamar_2 = "Kamar_2"
    Kamar_3 = "Kamar_3"
    Kamar_4 = "Kamar_4"
    Kamar_5 = "Kamar_5"
    Kamar_6 = "Kamar_6"

class TransactionStatus(enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"

class NotificationType(enum.Enum):
    NEW_USER_REGISTRATION = "NEW_USER_REGISTRATION"
    ROLE_UPGRADE_TO_ADMIN = "ROLE_UPGRADE_TO_ADMIN"
    ROLE_DOWNGRADE_TO_USER = "ROLE_DOWNGRADE_TO_USER"

# --- ENUM BARU UNTUK PROMO ---
class PromoEventType(enum.Enum):
    """
    Jenis-jenis event promo.
    - BONUS_REGISTRATION: Bonus otomatis saat registrasi (tidak perlu kode).
    - GENERAL_ANNOUNCEMENT: Pengumuman umum tanpa bonus, hanya informasi.
    """
    BONUS_REGISTRATION = "BONUS_REGISTRATION"
    GENERAL_ANNOUNCEMENT = "GENERAL_ANNOUNCEMENT"

class PromoEventStatus(enum.Enum):
    """Status dari sebuah event promo."""
    DRAFT = "DRAFT"       # Disimpan tapi belum aktif
    ACTIVE = "ACTIVE"     # Sedang berjalan dan terlihat oleh pengguna
    SCHEDULED = "SCHEDULED" # Dijadwalkan untuk aktif di masa depan
    EXPIRED = "EXPIRED"   # Sudah lewat masa berlakunya
    ARCHIVED = "ARCHIVED" # Disimpan sebagai arsip

# --- Definisi Model ---

# --- MODEL BARU UNTUK PROMO EVENT ---
class PromoEvent(db.Model):
    __tablename__ = 'promo_events'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    event_type: Mapped[PromoEventType] = mapped_column(SQLAlchemyEnum(PromoEventType, name="promo_event_type_enum", native_enum=False), nullable=False, default=PromoEventType.GENERAL_ANNOUNCEMENT)
    status: Mapped[PromoEventStatus] = mapped_column(SQLAlchemyEnum(PromoEventStatus, name="promo_event_status_enum", native_enum=False), nullable=False, default=PromoEventStatus.DRAFT, index=True)
    start_date: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    end_date: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Kolom untuk menyimpan nilai bonus jika ada (misal: kuota dalam MB)
    bonus_value_mb: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="Nilai bonus dalam MB untuk event tipe BONUS_REGISTRATION")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)

    created_by: Mapped["User"] = relationship("User", back_populates="created_promo_events")

    def __repr__(self):
        return f'<PromoEvent name={self.name} status={self.status.name}>'


class PackageProfile(db.Model):
    __tablename__ = 'package_profiles'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    packages: Mapped[List["Package"]] = relationship("Package", back_populates="profile")

    def __repr__(self):
        return f'<PackageProfile name={self.profile_name}>'

class Package(db.Model):
    __tablename__ = 'packages'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    data_quota_gb: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=0, comment="Kuota dalam GB. 0 berarti unlimited.")
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('package_profiles.id', ondelete='RESTRICT'), nullable=False)
    profile: Mapped["PackageProfile"] = relationship("PackageProfile", back_populates="packages", lazy="joined")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="package")

class User(db.Model):
    __tablename__ = 'users'
    __table_args__ = (UniqueConstraint('phone_number', name='uq_users_phone_number'), Index('ix_users_phone_number', 'phone_number', unique=True), {'extend_existing': True})
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number: Mapped[str] = mapped_column(String(25), nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    blok: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    kamar: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    previous_blok: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, comment="Menyimpan data blok terakhir sebelum diupgrade ke admin")
    previous_kamar: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="Menyimpan data kamar terakhir sebelum diupgrade ke admin")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=expression.false())
    role: Mapped[UserRole] = mapped_column(SQLAlchemyEnum(UserRole, name="user_role_enum", native_enum=False, create_type=False), nullable=False, default=UserRole.USER)
    approval_status: Mapped[ApprovalStatus] = mapped_column(SQLAlchemyEnum(ApprovalStatus, name="approval_status_enum", native_enum=False, create_type=False), nullable=False, default=ApprovalStatus.PENDING_APPROVAL)
    mikrotik_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    total_quota_purchased_mb: Mapped[int] = mapped_column(BigInteger(), nullable=False, default=0, server_default='0')
    total_quota_used_mb: Mapped[float] = mapped_column(Numeric(precision=15, scale=2), nullable=False, default=0.0, server_default='0.0')
    quota_expiry_date: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_unlimited_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=expression.false())
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

    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="user", lazy="select", cascade="all, delete-orphan")
    daily_usage_logs: Mapped[List["DailyUsageLog"]] = relationship("DailyUsageLog", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
    notification_subscriptions: Mapped[List["NotificationRecipient"]] = relationship("NotificationRecipient", back_populates="admin", cascade="all, delete-orphan")
    login_histories: Mapped[List["UserLoginHistory"]] = relationship("UserLoginHistory", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
    
    # Relasi baru dari User ke PromoEvent
    created_promo_events: Mapped[List["PromoEvent"]] = relationship("PromoEvent", back_populates="created_by", foreign_keys=[PromoEvent.created_by_id])


    def __repr__(self):
        return f'<User id={self.id} phone={self.phone_number}>'

    @property
    def is_admin_role(self) -> bool:
        return self.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]

    @property
    def is_super_admin_role(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN

    @property
    def is_approved(self) -> bool:
        return self.approval_status == ApprovalStatus.APPROVED

class NotificationRecipient(db.Model):
    __tablename__ = 'notification_recipients'
    __table_args__ = (UniqueConstraint('admin_user_id', 'notification_type', name='uq_notification_recipient_user_type'), Index('ix_notification_recipients_admin_user_id', 'admin_user_id'), {'extend_existing': True})
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    admin_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    notification_type: Mapped[NotificationType] = mapped_column(SQLAlchemyEnum(NotificationType, name="notification_type_enum", native_enum=False, create_type=False), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    admin: Mapped["User"] = relationship("User", back_populates="notification_subscriptions")

    def __repr__(self):
        return f'<NotificationRecipient user_id={self.admin_user_id} type={self.notification_type.name}>'

class Transaction(db.Model):
    __tablename__ = 'transactions'
    __table_args__ = (UniqueConstraint('midtrans_order_id', name='uq_transactions_midtrans_order_id'), Index('ix_transactions_midtrans_order_id', 'midtrans_order_id', unique=True), Index('ix_transactions_user_id', 'user_id'), Index('ix_transactions_package_id', 'package_id'), Index('ix_transactions_status', 'status'), Index('ix_transactions_midtrans_transaction_id', 'midtrans_transaction_id'), {'extend_existing': True})
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL', name='fk_transactions_user_id_users'), nullable=True)
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('packages.id', ondelete='RESTRICT', name='fk_transactions_package_id_packages'), nullable=False)
    midtrans_order_id: Mapped[str] = mapped_column(String(100), nullable=False)
    midtrans_transaction_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    snap_token: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    snap_redirect_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(SQLAlchemyEnum(TransactionStatus, name="transaction_status_enum", native_enum=False, create_type=False), nullable=False, default=TransactionStatus.PENDING)
    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expiry_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    va_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    biller_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    qr_code_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    hotspot_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    user: Mapped[Optional["User"]] = relationship("User", back_populates="transactions", lazy="select")
    package: Mapped["Package"] = relationship("Package", back_populates="transactions", lazy="select")

    def __repr__(self):
        status_repr = self.status.name if isinstance(self.status, enum.Enum) else self.status
        return f'<Transaction id={self.id} order_id={self.midtrans_order_id} status={status_repr}>'

class DailyUsageLog(db.Model):
    __tablename__ = 'daily_usage_logs'
    __table_args__ = (UniqueConstraint('user_id', 'log_date', name='uq_daily_usage_logs_user_log_date'), Index('ix_daily_usage_logs_user_id_log_date', 'user_id', 'log_date'), Index('ix_daily_usage_logs_user_id', 'user_id'), Index('ix_daily_usage_logs_log_date', 'log_date'), {'extend_existing': True})
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE', name='fk_daily_usage_logs_user_id_users'), nullable=False)
    log_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
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
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent_string: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user: Mapped["User"] = relationship("User", back_populates="login_histories")

    def __repr__(self):
        return f'<UserLoginHistory user_id={self.user_id} time={self.login_time}>'

class ApplicationSetting(db.Model):
    __tablename__ = 'application_settings'
    setting_key: Mapped[str] = mapped_column(String(100), primary_key=True, comment="Kunci unik untuk pengaturan, misal: 'APP_NAME'")
    setting_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Nilai dari pengaturan, bisa terenkripsi")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Penjelasan mengenai fungsi pengaturan ini")
    is_encrypted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=expression.false())
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        value_repr = '********' if self.is_encrypted else self.setting_value
        return f'<ApplicationSetting key={self.setting_key} value={value_repr}>'