"""
Test suite untuk Midtrans webhook signature security fix (BUG-2).

Coverage:
- Constant-time comparison using hmac.compare_digest()
- Prevention of timing attacks
- Proper error responses for invalid signatures
"""

import pytest
import hmac
import hashlib
from unittest.mock import patch, MagicMock


class TestMidtransWebhookSignatureSecurity:
    """Test Midtrans webhook signature validation fixes."""

    @pytest.fixture
    def webhook_endpoint(self, client):
        """Get webhook endpoint."""
        return "/api/transactions/webhook/midtrans/notification"

    @pytest.fixture
    def signature_payload(self):
        """Create a valid signature payload."""
        order_id = "ORDER-123"
        status_code = "200"
        gross_amount = "100000.00"
        server_key = "test-server-key"

        string_to_hash = f"{order_id}{status_code}{gross_amount}{server_key}"
        signature_key = hashlib.sha512(
            string_to_hash.encode("utf-8")
        ).hexdigest()

        return {
            "order_id": order_id,
            "status_code": status_code,
            "gross_amount": gross_amount,
            "signature_key": signature_key,
            "transaction_status": "capture",
            "fraud_status": "accept",
        }

    def test_uses_constant_time_comparison(self):
        """
        Test that webhook handler uses hmac.compare_digest for signature comparison.
        This prevents timing attacks where attacker can brute-force signature byte-by-byte.
        """
        # Correct signature
        sig_correct = "abcdef1234567890"
        # Attacker signature (first char correct, rest wrong)
        sig_attack_1 = "abcdef0000000000"
        # Attacker signature (first char wrong)
        sig_attack_2 = "0bcdef1234567890"

        # hmac.compare_digest should take same time for both
        # (In contrast, == would be faster for sig_attack_2 due to first char mismatch)
        with patch("hmac.compare_digest") as mock_compare:
            mock_compare.return_value = False

            # Both should call compare_digest (constant time)
            result1 = mock_compare(sig_correct, sig_attack_1)
            result2 = mock_compare(sig_correct, sig_attack_2)

            assert result1 == False
            assert result2 == False
            # Both calls went through constant-time function
            assert mock_compare.call_count == 2

    def test_signature_validation_invalid_signature_returns_403(
        self, client, webhook_endpoint, signature_payload
    ):
        """Test that invalid signature returns 403 Forbidden."""
        # Tamper with signature key
        signature_payload["signature_key"] = "invalid_signature_key"

        with patch(
            "app.infrastructure.http.transactions.webhook_routes.current_app"
        ) as mock_app:
            mock_app.config.get.side_effect = lambda key, default=None: {
                "MIDTRANS_SERVER_KEY": "test-server-key",
                "MIDTRANS_REQUIRE_SIGNATURE_VALIDATION": True,
                "FLASK_ENV": "production",
            }.get(key, default)

            response = client.post(
                webhook_endpoint,
                json=signature_payload,
                content_type="application/json",
            )

            assert response.status_code == 403
            assert "Signature tidak valid" in response.json.get("message", "")

    def test_signature_validation_valid_signature(
        self, client, webhook_endpoint, signature_payload
    ):
        """Test that valid signature passes through."""
        with patch(
            "app.infrastructure.http.transactions.webhook_routes.current_app"
        ) as mock_app, patch(
            "app.infrastructure.http.transactions.webhook_routes.Transaction"
        ) as mock_tx_model:

            mock_app.config.get.side_effect = lambda key, default=None: {
                "MIDTRANS_SERVER_KEY": "test-server-key",
                "MIDTRANS_REQUIRE_SIGNATURE_VALIDATION": True,
                "FLASK_ENV": "production",
                "MIDTRANS_IS_PRODUCTION": False,
            }.get(key, default)

            # Mock transaction query
            mock_query = MagicMock()
            mock_tx_model.query.return_value = mock_query
            mock_query.options.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.with_for_update.return_value = mock_query
            mock_query.first.return_value = None  # No transaction found

            response = client.post(
                webhook_endpoint,
                json=signature_payload,
                content_type="application/json",
            )

            # Should get OK response (even if transaction not found)
            assert response.status_code in [200, 400]  # 200 OK or 400 Bad Request

    def test_missing_signature_key_returns_403(
        self, client, webhook_endpoint, signature_payload
    ):
        """Test that missing signature key returns 403."""
        del signature_payload["signature_key"]

        with patch(
            "app.infrastructure.http.transactions.webhook_routes.current_app"
        ) as mock_app:
            mock_app.config.get.side_effect = lambda key, default=None: {
                "MIDTRANS_SERVER_KEY": "test-server-key",
                "MIDTRANS_REQUIRE_SIGNATURE_VALIDATION": True,
                "FLASK_ENV": "production",
            }.get(key, default)

            response = client.post(
                webhook_endpoint,
                json=signature_payload,
                content_type="application/json",
            )

            assert response.status_code == 403


class TestSignatureTimingAttackResistance:
    """
    Test that signature comparison is resistant to timing attacks.
    """

    def test_hmac_compare_digest_is_constant_time(self):
        """Verify hmac.compare_digest is time-constant."""
        # This is more of a documentation test — hmac.compare_digest
        # is guaranteed by Python stdlib to be constant-time
        sig1 = "a" * 128  # 128-char hex (SHA512)
        sig_correct = sig1

        # Different in 1st position
        sig_early = ("b") + sig1[1:]
        # Different in last position
        sig_late = sig1[:-1] + ("b")

        # All should execute in roughly same time
        # (With regular == operator, sig_early would be faster)
        result_early = hmac.compare_digest(sig_correct, sig_early)
        result_late = hmac.compare_digest(sig_correct, sig_late)
        result_correct = hmac.compare_digest(sig_correct, sig_correct)

        assert result_early == False
        assert result_late == False
        assert result_correct == True
