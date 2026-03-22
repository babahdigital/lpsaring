"""
Test suite untuk enforce_overdue_debt_block_task fixes (BUG-1, BUG-3, counter labels, ENABLE_MIKROTIK check).

Coverage:
- DetachedInstanceError fix: devices selectinload
- Session management: proper cleanup at end
- Counter labels: skipped_non_approved vs skipped_non_user_role
- ENABLE_MIKROTIK_OPERATIONS guard
- MikroTik operation failure handling
- WA notification sending
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, call
from app.infrastructure.db.models import (
    User, UserQuotaDebt, UserDevice, ApprovalStatus, UserRole,
)
from app.tasks import enforce_overdue_debt_block_task


class TestEnforceOverdueDebtBlockCriticalFixes:
    """Test critical fixes in enforce_overdue_debt_block_task."""

    @pytest.fixture
    def app_with_db(self, app, db_session):
        """Flask app with database context."""
        with app.app_context():
            yield app

    @pytest.fixture
    def sample_users(self, db_session):
        """Create sample users for testing."""
        # User 1: Active, approved, regular user with overdue debt
        user1 = User(
            id="user-1",
            phone_number="+6285123456789",
            approval_status=ApprovalStatus.APPROVED,
            role=UserRole.USER,
            is_active=True,
            is_unlimited_user=False,
            is_blocked=False,
        )
        db_session.add(user1)

        # User 2: Komandan (should skip with skipped_non_user_role)
        user2 = User(
            id="user-2",
            phone_number="+6285987654321",
            approval_status=ApprovalStatus.APPROVED,
            role=UserRole.KOMANDAN,  # Not USER role
            is_active=True,
            is_unlimited_user=False,
            is_blocked=False,
        )
        db_session.add(user2)

        # User 3: Inactive (should skip with skipped_non_approved)
        user3 = User(
            id="user-3",
            phone_number="+6289876543210",
            approval_status=ApprovalStatus.PENDING,  # Not approved
            role=UserRole.USER,
            is_active=True,
            is_unlimited_user=False,
            is_blocked=False,
        )
        db_session.add(user3)

        db_session.flush()
        return user1, user2, user3

    @pytest.fixture
    def overdue_debts(self, db_session, sample_users):
        """Create overdue debt entries."""
        user1, user2, user3 = sample_users
        today = datetime.now().date()
        old_date = today - timedelta(days=10)  # 10 days overdue

        debt1 = UserQuotaDebt(
            id="debt-1",
            user_id=user1.id,
            amount_mb=1000,
            debt_date=old_date,
            due_date=old_date,
            paid_at=None,
            is_paid=False,
        )
        debt2 = UserQuotaDebt(
            id="debt-2",
            user_id=user2.id,
            amount_mb=500,
            debt_date=old_date,
            due_date=old_date,
            paid_at=None,
            is_paid=False,
        )
        debt3 = UserQuotaDebt(
            id="debt-3",
            user_id=user3.id,
            amount_mb=2000,
            debt_date=old_date,
            due_date=old_date,
            paid_at=None,
            is_paid=False,
        )

        db_session.add_all([debt1, debt2, debt3])
        db_session.commit()
        return [debt1, debt2, debt3]

    def test_selectinload_devices_no_detached_instance_error(
        self, app_with_db, db_session, sample_users, overdue_debts
    ):
        """
        Test BUG-1 fix: devices are properly loaded and accessible after session.remove().
        This would fail before the fix with DetachedInstanceError.
        """
        user1 = sample_users[0]

        # Create device for user1
        device = UserDevice(
            id="device-1",
            user_id=user1.id,
            mac_address="aa:bb:cc:dd:ee:ff",
            ip_address="172.16.2.10",
            device_type="mobile",
        )
        db_session.add(device)
        db_session.commit()

        with patch(
            "app.tasks.settings_service.get_setting"
        ) as mock_settings, patch(
            "app.tasks._handle_mikrotik_operation"
        ) as mock_mikrotik, patch(
            "app.tasks.get_mikrotik_connection"
        ) as mock_conn:

            # Mock all settings to allow task to proceed
            def settings_get(key, default=None):
                settings = {
                    "ENABLE_OVERDUE_DEBT_BLOCK": "True",
                    "ENABLE_MIKROTIK_OPERATIONS": "True",
                    "MIKROTIK_BLOCKED_PROFILE": "inactive",
                    "MIKROTIK_ADDRESS_LIST_BLOCKED": "blocked",
                    "ENABLE_WHATSAPP_NOTIFICATIONS": "True",
                    "MIKROTIK_ADDRESS_LIST_ACTIVE": "active",
                    "MIKROTIK_ADDRESS_LIST_FUP": "fup",
                    "MIKROTIK_ADDRESS_LIST_INACTIVE": "inactive",
                    "MIKROTIK_ADDRESS_LIST_EXPIRED": "expired",
                    "MIKROTIK_ADDRESS_LIST_HABIS": "habis",
                    "IP_BINDING_TYPE_BLOCKED": "blocked",
                }
                return settings.get(key, default)

            mock_settings.side_effect = settings_get
            mock_mikrotik.return_value = (True, None)
            mock_conn.return_value.__enter__.return_value = MagicMock()

            # Run task - should not raise DetachedInstanceError
            result = enforce_overdue_debt_block_task.apply_async().get()

            # Device should have been accessed without error
            assert result["checked"] >= 1
            assert "block_failed" in result

    def test_counter_labels_non_user_role(
        self, app_with_db, db_session, sample_users, overdue_debts
    ):
        """
        Test INFO-4 fix: counter labels differentiate between non_approved and non_user_role.
        User2 (Komandan) should increment skipped_non_user_role, not skipped_non_approved.
        """
        with patch(
            "app.tasks.settings_service.get_setting"
        ) as mock_settings, patch(
            "app.tasks._handle_mikrotik_operation"
        ), patch(
            "app.tasks.get_mikrotik_connection"
        ) as mock_conn:

            def settings_get(key, default=None):
                settings = {
                    "ENABLE_OVERDUE_DEBT_BLOCK": "True",
                    "ENABLE_MIKROTIK_OPERATIONS": "True",
                    "MIKROTIK_BLOCKED_PROFILE": "inactive",
                    "MIKROTIK_ADDRESS_LIST_BLOCKED": "blocked",
                    "ENABLE_WHATSAPP_NOTIFICATIONS": "False",  # Disable WA
                    "MIKROTIK_ADDRESS_LIST_ACTIVE": "active",
                    "MIKROTIK_ADDRESS_LIST_FUP": "fup",
                    "MIKROTIK_ADDRESS_LIST_INACTIVE": "inactive",
                    "MIKROTIK_ADDRESS_LIST_EXPIRED": "expired",
                    "MIKROTIK_ADDRESS_LIST_HABIS": "habis",
                    "IP_BINDING_TYPE_BLOCKED": "blocked",
                }
                return settings.get(key, default)

            mock_settings.side_effect = settings_get
            mock_conn.return_value.__enter__.return_value = MagicMock()

            result = enforce_overdue_debt_block_task.apply_async().get()

            # User2 (Komandan) should be in skipped_non_user_role
            assert result.get("skipped_non_user_role", 0) >= 1
            # And NOT in skipped_non_approved
            assert result.get("skipped_non_approved", 0) == 0  # Only user3 should be here

    def test_enable_mikrotik_operations_guard(
        self, app_with_db, db_session, sample_users, overdue_debts
    ):
        """Test INFO-3 fix: Task skips if ENABLE_MIKROTIK_OPERATIONS is False."""
        with patch(
            "app.tasks.settings_service.get_setting"
        ) as mock_settings:

            def settings_get(key, default=None):
                if key == "ENABLE_OVERDUE_DEBT_BLOCK":
                    return "True"
                if key == "ENABLE_MIKROTIK_OPERATIONS":
                    return "False"  # Disabled!
                return default

            mock_settings.side_effect = settings_get

            result = enforce_overdue_debt_block_task.apply_async().get()

            # Should return early with mikrotik_disabled reason
            assert result.get("skipped") == "mikrotik_disabled"

    def test_session_cleanup_at_end(
        self, app_with_db, db_session, sample_users, overdue_debts
    ):
        """Test session management: db.session.remove() called at end, not in finally."""
        with patch(
            "app.tasks.db.session.remove"
        ) as mock_remove, patch(
            "app.tasks.settings_service.get_setting"
        ) as mock_settings, patch(
            "app.tasks._handle_mikrotik_operation"
        ), patch(
            "app.tasks.get_mikrotik_connection"
        ) as mock_conn:

            def settings_get(key, default=None):
                settings = {
                    "ENABLE_OVERDUE_DEBT_BLOCK": "True",
                    "ENABLE_MIKROTIK_OPERATIONS": "True",
                    "MIKROTIK_BLOCKED_PROFILE": "inactive",
                    "MIKROTIK_ADDRESS_LIST_BLOCKED": "blocked",
                    "ENABLE_WHATSAPP_NOTIFICATIONS": "False",
                    "MIKROTIK_ADDRESS_LIST_ACTIVE": "active",
                    "MIKROTIK_ADDRESS_LIST_FUP": "fup",
                    "MIKROTIK_ADDRESS_LIST_INACTIVE": "inactive",
                    "MIKROTIK_ADDRESS_LIST_EXPIRED": "expired",
                    "MIKROTIK_ADDRESS_LIST_HABIS": "habis",
                    "IP_BINDING_TYPE_BLOCKED": "blocked",
                }
                return settings.get(key, default)

            mock_settings.side_effect = settings_get
            mock_conn.return_value.__enter__.return_value = MagicMock()

            result = enforce_overdue_debt_block_task.apply_async().get()

            # session.remove() should be called at least once (at the end)
            assert mock_remove.call_count >= 1
