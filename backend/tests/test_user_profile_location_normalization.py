from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.infrastructure.db.models import ApprovalStatus, UserBlok, UserKamar, UserRole
from app.services.user_management import user_profile


def test_normalize_user_location_helpers_accept_enum_values():
    assert user_profile._normalize_user_blok_value(UserBlok.A) == "A"
    assert user_profile._normalize_user_kamar_value(UserKamar.Kamar_1) == "Kamar_1"
    assert user_profile._normalize_user_kamar_value("1") == "Kamar_1"


def test_update_user_by_admin_normalizes_enum_location_values(monkeypatch):
    target_user = SimpleNamespace(
        id=uuid.uuid4(),
        role=UserRole.USER,
        is_active=False,
        is_admin_role=False,
        is_unlimited_user=False,
        is_tamping=False,
        tamping_type=None,
        blok="B",
        kamar="Kamar_2",
        is_blocked=False,
        blocked_reason=None,
        full_name="User Lama",
        phone_number="081234567890",
        approval_status=ApprovalStatus.APPROVED,
    )
    admin_actor = SimpleNamespace(is_super_admin_role=True)

    monkeypatch.setattr(user_profile, "_log_admin_action", lambda *_args, **_kwargs: None)

    success, message, updated_user = user_profile.update_user_by_admin_comprehensive(
        target_user,
        admin_actor,
        {"blok": UserBlok.A, "kamar": UserKamar.Kamar_1},
    )

    assert success is True
    assert message == "Data pengguna berhasil diperbarui, akun dinonaktifkan."
    assert updated_user is target_user
    assert target_user.blok == "A"
    assert target_user.kamar == "Kamar_1"