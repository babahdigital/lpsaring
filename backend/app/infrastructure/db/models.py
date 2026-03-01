# backend/app/infrastructure/db/models.py
import uuid
import enum
import datetime
from typing import List, Optional

from sqlalchemy import (
    Text,
    DateTime,
    Numeric,
    func,
    Boolean,
    ForeignKey,
    Index,
    UniqueConstraint,
    Enum as SQLAlchemyEnum,
    BigInteger,
    Date,
    String,
    Integer,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import expression
import sqlalchemy as sa

from app.extensions import db


# --- Definisi Enum ---
class UserRole(enum.Enum):
    USER = "USER"
    KOMANDAN = "KOMANDAN"
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


class TransactionEventSource(enum.Enum):
    APP = "APP"
    MIDTRANS_WEBHOOK = "MIDTRANS_WEBHOOK"
    MIDTRANS_STATUS = "MIDTRANS_STATUS"


class NotificationType(enum.Enum):
    NEW_USER_REGISTRATION = "NEW_USER_REGISTRATION"
    NEW_KOMANDAN_REQUEST = "NEW_KOMANDAN_REQUEST"
    ROLE_UPGRADE_TO_ADMIN = "ROLE_UPGRADE_TO_ADMIN"
    ROLE_DOWNGRADE_TO_USER = "ROLE_DOWNGRADE_TO_USER"
    QUOTA_DEBT_LIMIT_EXCEEDED = "QUOTA_DEBT_LIMIT_EXCEEDED"


class PromoEventType(enum.Enum):
    BONUS_REGISTRATION = "BONUS_REGISTRATION"
    GENERAL_ANNOUNCEMENT = "GENERAL_ANNOUNCEMENT"


class PromoEventStatus(enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SCHEDULED = "SCHEDULED"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


class RequestType(enum.Enum):
    QUOTA = "QUOTA"
    UNLIMITED = "UNLIMITED"


class RequestStatus(enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PARTIALLY_APPROVED = "PARTIALLY_APPROVED"


class AdminActionType(enum.Enum):
    CREATE_USER = "CREATE_USER"
    APPROVE_USER = "APPROVE_USER"
    REJECT_USER = "REJECT_USER"
    CHANGE_USER_ROLE = "CHANGE_USER_ROLE"
    UPGRADE_TO_ADMIN = "UPGRADE_TO_ADMIN"
    DOWNGRADE_TO_USER = "DOWNGRADE_TO_USER"
    DOWNGRADE_FROM_ADMIN = "DOWNGRADE_FROM_ADMIN"
    INJECT_QUOTA = "INJECT_QUOTA"
    SET_UNLIMITED_STATUS = "SET_UNLIMITED_STATUS"
    REVOKE_UNLIMITED_STATUS = "REVOKE_UNLIMITED_STATUS"
    ACTIVATE_USER = "ACTIVATE_USER"
    DEACTIVATE_USER = "DEACTIVATE_USER"
    RESET_HOTSPOT_PASSWORD = "RESET_HOTSPOT_PASSWORD"
    GENERATE_ADMIN_PASSWORD = "GENERATE_ADMIN_PASSWORD"
    MANUAL_USER_DELETE = "MANUAL_USER_DELETE"
    UPDATE_USER_PROFILE = "UPDATE_USER_PROFILE"
    BLOCK_USER = "BLOCK_USER"
    UNBLOCK_USER = "UNBLOCK_USER"

    RESET_USER_LOGIN = "RESET_USER_LOGIN"

    # --- [PENAMBAHAN DI SINI] ---
    # Menambahkan tipe aksi spesifik untuk pemrosesan permintaan kuota.
    PROCESS_QUOTA_REQUEST_APPROVE = "PROCESS_QUOTA_REQUEST_APPROVE"
    PROCESS_QUOTA_REQUEST_REJECT = "PROCESS_QUOTA_REQUEST_REJECT"
    PROCESS_QUOTA_REQUEST_PARTIALLY_APPROVED = "PROCESS_QUOTA_REQUEST_PARTIALLY_APPROVED"

    # Generic fallback for any admin mutation endpoint that does not have a specific action type.
    ADMIN_API_MUTATION = "ADMIN_API_MUTATION"

    CREATE_QRIS_BILL = "CREATE_QRIS_BILL"


# --- Definisi Model ---


class PromoEvent(db.Model):
    __tablename__ = "promo_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    event_type: Mapped[PromoEventType] = mapped_column(
        SQLAlchemyEnum(PromoEventType, name="promo_event_type_enum", native_enum=False),
        nullable=False,
        default=PromoEventType.GENERAL_ANNOUNCEMENT,
        server_default=PromoEventType.GENERAL_ANNOUNCEMENT.value,
    )
    status: Mapped[PromoEventStatus] = mapped_column(
        SQLAlchemyEnum(PromoEventStatus, name="promo_event_status_enum", native_enum=False),
        nullable=False,
        default=PromoEventStatus.DRAFT,
        server_default=PromoEventStatus.DRAFT.value,
        index=True,
    )
    start_date: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    end_date: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    bonus_value_mb: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, comment="Nilai bonus dalam MB untuk event tipe BONUS_REGISTRATION"
    )
    bonus_duration_days: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Durasi masa aktif bonus dalam hari"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_by: Mapped["User"] = relationship("User", back_populates="created_promo_events")


class PackageProfile(db.Model):
    __tablename__ = "package_profiles"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    packages: Mapped[List["Package"]] = relationship("Package", back_populates="profile")


class Package(db.Model):
    __tablename__ = "packages"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=expression.true())
    data_quota_gb: Mapped[float] = mapped_column(
        Numeric(8, 2), nullable=False, default=0, server_default="0", comment="Kuota dalam GB. 0 berarti unlimited."
    )
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30, server_default="30")
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("package_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    profile: Mapped["PackageProfile"] = relationship("PackageProfile", back_populates="packages", lazy="joined")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="package")


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("phone_number", name="uq_users_phone_number"),
        Index("ix_users_phone_number", "phone_number", unique=True),
        {"extend_existing": True},
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number: Mapped[str] = mapped_column(String(25), nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    blok: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    kamar: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_tamping: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=expression.false(),
        comment="Penanda pengguna tamping (True) atau non-tamping (False).",
    )
    tamping_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="Jenis tamping jika pengguna tamping."
    )
    previous_blok: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, comment="Menyimpan data blok terakhir sebelum diupgrade ke admin"
    )
    previous_kamar: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="Menyimpan data kamar terakhir sebelum diupgrade ke admin"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=expression.false())
    role: Mapped[UserRole] = mapped_column(
        SQLAlchemyEnum(UserRole, name="user_role_enum", native_enum=False),
        nullable=False,
        default=UserRole.USER,
        server_default=UserRole.USER.value,
    )
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        SQLAlchemyEnum(ApprovalStatus, name="approval_status_enum", native_enum=False),
        nullable=False,
        default=ApprovalStatus.PENDING_APPROVAL,
        server_default=ApprovalStatus.PENDING_APPROVAL.value,
    )

    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=expression.false())
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    blocked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", name="fk_users_blocked_by_id_users"), nullable=True
    )

    # PENAMBAHAN FIELD BARU
    mikrotik_user_exists: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=expression.false(),
        comment="Flag untuk menandakan user sudah ada di Mikrotik.",
    )

    mikrotik_server_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Nama server hotspot spesifik di Mikrotik."
    )
    mikrotik_profile_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Nama profil hotspot spesifik di Mikrotik."
    )
    mikrotik_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    total_quota_purchased_mb: Mapped[int] = mapped_column(BigInteger(), nullable=False, default=0, server_default="0")
    total_quota_used_mb: Mapped[float] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False, default=0.0, server_default="0.0"
    )

    # Auto-debt offset (MB) used to settle automatic debt WITHOUT increasing purchased quota.
    # Effective auto debt = max(0, used - purchased - auto_debt_offset).
    auto_debt_offset_mb: Mapped[int] = mapped_column(BigInteger(), nullable=False, default=0, server_default="0")

    # Manual debt (MB) entered by admin. This is separate from automatic debt computed as used - purchased.
    manual_debt_mb: Mapped[int] = mapped_column(BigInteger(), nullable=False, default=0, server_default="0")
    manual_debt_updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    quota_expiry_date: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_unlimited_user: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=expression.false()
    )

    # Telegram linking (per user)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    telegram_username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    telegram_linked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    device_brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    device_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    raw_user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    approved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", name="fk_users_approved_by_id_users"), nullable=True
    )
    rejected_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", name="fk_users_rejected_by_id_users"), nullable=True
    )
    last_login_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_low_quota_notif_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Waktu terakhir notifikasi kuota rendah dikirim"
    )
    last_expiry_notif_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Waktu terakhir notifikasi akan kedaluwarsa dikirim"
    )
    last_quota_notification_level: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Level persen terakhir notifikasi kuota (mis. 20/10/5)"
    )
    last_expiry_notification_level: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Level hari terakhir notifikasi masa aktif (mis. 7/3/1)"
    )

    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="user", lazy="select", cascade="all, delete-orphan"
    )
    daily_usage_logs: Mapped[List["DailyUsageLog"]] = relationship(
        "DailyUsageLog", back_populates="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    notification_subscriptions: Mapped[List["NotificationRecipient"]] = relationship(
        "NotificationRecipient", back_populates="admin", cascade="all, delete-orphan"
    )
    login_histories: Mapped[List["UserLoginHistory"]] = relationship(
        "UserLoginHistory", back_populates="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    created_promo_events: Mapped[List["PromoEvent"]] = relationship(
        "PromoEvent", back_populates="created_by", foreign_keys=[PromoEvent.created_by_id]
    )
    quota_requests: Mapped[List["QuotaRequest"]] = relationship(
        "QuotaRequest",
        back_populates="requester",
        foreign_keys="QuotaRequest.requester_id",
        cascade="all, delete-orphan",
    )
    created_action_logs: Mapped[List["AdminActionLog"]] = relationship(
        "AdminActionLog", back_populates="admin", foreign_keys="AdminActionLog.admin_id"
    )
    received_action_logs: Mapped[List["AdminActionLog"]] = relationship(
        "AdminActionLog", back_populates="target_user", foreign_keys="AdminActionLog.target_user_id"
    )
    devices: Mapped[List["UserDevice"]] = relationship(
        "UserDevice", back_populates="user", cascade="all, delete-orphan", lazy="select"
    )
    manual_debts: Mapped[List["UserQuotaDebt"]] = relationship(
        "UserQuotaDebt",
        back_populates="user",
        foreign_keys="UserQuotaDebt.user_id",
        cascade="all, delete-orphan",
        lazy="select",
    )
    quota_mutation_logs: Mapped[List["QuotaMutationLedger"]] = relationship(
        "QuotaMutationLedger",
        back_populates="user",
        foreign_keys="QuotaMutationLedger.user_id",
        cascade="all, delete-orphan",
        lazy="select",
    )

    @property
    def is_admin_role(self) -> bool:
        return self.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]

    @property
    def is_super_admin_role(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN

    @property
    def is_approved(self) -> bool:
        return self.approval_status == ApprovalStatus.APPROVED

    @property
    def quota_debt_auto_mb(self) -> float:
        if self.role == UserRole.KOMANDAN or bool(getattr(self, "is_unlimited_user", False)):
            return 0.0
        from app.utils.quota_debt import compute_debt_mb

        purchased_mb = float(self.total_quota_purchased_mb or 0.0)
        try:
            offset_mb = float(getattr(self, "auto_debt_offset_mb", 0) or 0.0)
        except Exception:
            offset_mb = 0.0
        used_mb = float(self.total_quota_used_mb or 0.0)
        return float(compute_debt_mb(purchased_mb + offset_mb, used_mb))

    @property
    def quota_debt_manual_mb(self) -> int:
        if self.role == UserRole.KOMANDAN or bool(getattr(self, "is_unlimited_user", False)):
            return 0
        try:
            return int(self.manual_debt_mb or 0)
        except (TypeError, ValueError):
            return 0

    @property
    def quota_debt_total_mb(self) -> float:
        if self.role == UserRole.KOMANDAN or bool(getattr(self, "is_unlimited_user", False)):
            return 0.0
        return float(self.quota_debt_auto_mb) + float(self.quota_debt_manual_mb)


class UserQuotaDebt(db.Model):
    __tablename__ = "user_quota_debts"
    __table_args__ = (
        Index("ix_user_quota_debts_user_id", "user_id"),
        Index("ix_user_quota_debts_is_paid", "is_paid"),
        {"extend_existing": True},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_paid_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    debt_date: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)
    amount_mb: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    paid_mb: Mapped[int] = mapped_column(BigInteger(), nullable=False, default=0, server_default="0")
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=expression.false())
    paid_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_paid_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="manual_debts", foreign_keys=[user_id])
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])
    last_paid_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[last_paid_by_id])


class UserDevice(db.Model):
    __tablename__ = "user_devices"
    __table_args__ = (
        UniqueConstraint("user_id", "mac_address", name="uq_user_devices_user_mac"),
        Index("ix_user_devices_user_id", "user_id"),
        Index("ix_user_devices_mac_address", "mac_address"),
        {"extend_existing": True},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    mac_address: Mapped[str] = mapped_column(String(32), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    last_bytes_total: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    last_bytes_updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_authorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=expression.true())
    first_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    authorized_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    deauthorized_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="devices", lazy="joined")


class RefreshToken(db.Model):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
        {"extend_existing": True},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Simpan hash (sha256 hex) dari refresh token raw untuk menghindari penyimpanan token plaintext.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    issued_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    replaced_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True
    )

    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    user: Mapped["User"] = relationship("User", lazy="joined")
    replaced_by: Mapped[Optional["RefreshToken"]] = relationship("RefreshToken", remote_side=[id], lazy="select")


class NotificationRecipient(db.Model):
    __tablename__ = "notification_recipients"
    __table_args__ = (
        UniqueConstraint("admin_user_id", "notification_type", name="uq_notification_recipient_user_type"),
        Index("ix_notification_recipients_admin_user_id", "admin_user_id"),
        {"extend_existing": True},
    )
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    admin_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        SQLAlchemyEnum(NotificationType, name="notification_type_enum", native_enum=False, length=64),
        nullable=False,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    admin: Mapped["User"] = relationship("User", back_populates="notification_subscriptions")


class Transaction(db.Model):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("midtrans_order_id", name="uq_transactions_midtrans_order_id"),
        Index("ix_transactions_midtrans_order_id", "midtrans_order_id", unique=True),
        Index("ix_transactions_user_id", "user_id"),
        Index("ix_transactions_package_id", "package_id"),
        Index("ix_transactions_status", "status"),
        Index("ix_transactions_midtrans_transaction_id", "midtrans_transaction_id"),
        {"extend_existing": True},
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_transactions_user_id_users"),
        nullable=True,
    )
    package_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("packages.id", ondelete="RESTRICT", name="fk_transactions_package_id_packages"),
        nullable=True,
    )
    midtrans_order_id: Mapped[str] = mapped_column(String(100), nullable=False)
    midtrans_transaction_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    snap_token: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    snap_redirect_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(
        SQLAlchemyEnum(TransactionStatus, name="transaction_status_enum", native_enum=False),
        nullable=False,
        default=TransactionStatus.PENDING,
        server_default=TransactionStatus.PENDING.value,
    )
    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expiry_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    va_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    biller_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    qr_code_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    midtrans_notification_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hotspot_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    user: Mapped[Optional["User"]] = relationship("User", back_populates="transactions", lazy="select")
    package: Mapped[Optional["Package"]] = relationship("Package", back_populates="transactions", lazy="select")
    events: Mapped[List["TransactionEvent"]] = relationship(
        "TransactionEvent",
        back_populates="transaction",
        cascade="all, delete-orphan",
        lazy="select",
    )


class TransactionEvent(db.Model):
    __tablename__ = "transaction_events"
    __table_args__ = (
        Index("ix_transaction_events_transaction_id", "transaction_id"),
        Index("ix_transaction_events_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE", name="fk_transaction_events_transaction_id_transactions"),
        nullable=False,
    )
    source: Mapped[TransactionEventSource] = mapped_column(
        SQLAlchemyEnum(TransactionEventSource, name="transaction_event_source_enum", native_enum=False, length=32),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[Optional[TransactionStatus]] = mapped_column(
        SQLAlchemyEnum(TransactionStatus, name="transaction_status_enum", native_enum=False),
        nullable=True,
    )
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    transaction: Mapped["Transaction"] = relationship("Transaction", back_populates="events", lazy="select")


class DailyUsageLog(db.Model):
    __tablename__ = "daily_usage_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "log_date", name="uq_daily_usage_logs_user_log_date"),
        Index("ix_daily_usage_logs_user_id_log_date", "user_id", "log_date"),
    )
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_daily_usage_logs_user_id_users"),
        nullable=False,
    )
    log_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    usage_mb: Mapped[float] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False, default=0.0, server_default="0.0"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    user: Mapped["User"] = relationship("User", back_populates="daily_usage_logs", lazy="select")


class UserLoginHistory(db.Model):
    __tablename__ = "user_login_history"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    login_time: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent_string: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user: Mapped["User"] = relationship("User", back_populates="login_histories")


class ApplicationSetting(db.Model):
    __tablename__ = "application_settings"
    setting_key: Mapped[str] = mapped_column(String(100), primary_key=True, comment="Kunci unik untuk pengaturan")
    setting_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Nilai dari pengaturan")
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Penjelasan mengenai fungsi pengaturan ini"
    )
    is_encrypted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=expression.false()
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AdminActionLog(db.Model):
    __tablename__ = "admin_action_logs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action_type: Mapped[AdminActionType] = mapped_column(
        SQLAlchemyEnum(AdminActionType, name="admin_action_type_enum", native_enum=False), nullable=False, index=True
    )
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Detail aksi dalam format JSON")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    admin: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[admin_id], back_populates="created_action_logs"
    )
    target_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[target_user_id], back_populates="received_action_logs"
    )


class QuotaMutationLedger(db.Model):
    __tablename__ = "quota_mutation_ledger"
    __table_args__ = (
        Index("ix_quota_mutation_ledger_user_created", "user_id", "created_at"),
        Index("ix_quota_mutation_ledger_source", "source"),
        UniqueConstraint(
            "user_id",
            "source",
            "idempotency_key",
            name="uq_quota_mutation_ledger_user_source_idempotency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    before_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    after_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    event_details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="quota_mutation_logs")
    actor: Mapped[Optional["User"]] = relationship("User", foreign_keys=[actor_user_id])


class PublicDatabaseUpdateSubmission(db.Model):
    __tablename__ = "public_database_update_submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    blok: Mapped[str] = mapped_column(String(10), nullable=False)
    kamar: Mapped[str] = mapped_column(String(20), nullable=False)
    phone_number: Mapped[Optional[str]] = mapped_column(String(25), nullable=True)
    source_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class QuotaRequest(db.Model):
    __tablename__ = "quota_requests"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[RequestStatus] = mapped_column(
        SQLAlchemyEnum(RequestStatus, name="request_status_enum", native_enum=False),
        nullable=False,
        default=RequestStatus.PENDING,
        server_default=RequestStatus.PENDING.value,
        index=True,
    )
    request_type: Mapped[RequestType] = mapped_column(
        SQLAlchemyEnum(RequestType, name="request_type_enum", native_enum=False), nullable=False
    )
    request_details: Mapped[Optional[str]] = mapped_column(
        Text, comment="Detail request dlm JSON, misal: {'mb_to_add': 10240, 'days_to_add': 30}"
    )

    # [PENAMBAHAN] Kolom baru untuk menyimpan detail persetujuan parsial
    granted_details: Mapped[Optional[str]] = mapped_column(
        Text, comment="Detail persetujuan parsial dlm JSON, misal: {'granted_mb': 5120, 'granted_duration_days': 15}"
    )

    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    processed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    processed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    requester: Mapped["User"] = relationship("User", foreign_keys=[requester_id], back_populates="quota_requests")
    processed_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[processed_by_id])
