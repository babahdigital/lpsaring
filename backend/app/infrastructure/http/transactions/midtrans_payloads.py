from typing import Any


def build_core_api_charge_payload(
    *,
    order_id: str,
    gross_amount: int,
    item_id: str,
    item_name: str,
    customer_name: str,
    customer_phone: str,
    expiry_minutes: int,
    finish_url: str,
    method: str,
    va_bank: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "transaction_details": {"order_id": order_id, "gross_amount": int(gross_amount)},
        "item_details": [{"id": item_id, "price": int(gross_amount), "quantity": 1, "name": item_name[:100]}],
        "customer_details": {
            "first_name": customer_name or "Pengguna",
            "phone": customer_phone,
        },
        "custom_expiry": {"expiry_duration": int(expiry_minutes), "unit": "minute"},
    }

    if method == "qris":
        payload["payment_type"] = "qris"
        payload["qris"] = {"acquirer": "gopay"}
        return payload

    if method == "gopay":
        payload["payment_type"] = "gopay"
        payload["gopay"] = {
            "enable_callback": True,
            "callback_url": str(finish_url),
        }
        return payload

    if method == "shopeepay":
        payload["payment_type"] = "shopeepay"
        payload["shopeepay"] = {
            "callback_url": str(finish_url),
        }
        return payload

    bank = va_bank or "bni"
    if bank == "mandiri":
        payload["payment_type"] = "echannel"
        payload["echannel"] = {
            "bill_info1": "Pembayaran Hotspot",
            "bill_info2": item_name[:18] or "Hotspot",
        }
        return payload

    payload["payment_type"] = "bank_transfer"
    payload["bank_transfer"] = {"bank": bank}
    return payload
