# 2026-03-26 Unlimited Debt Display & Settlement Amount Errors

## Severity: High

## Summary

Multiple bugs discovered in WhatsApp notifications, PDF receipts, and online payment flow related to **unlimited debt items** (paket unlimited dicatat sebagai tunggakan manual). Sentinel value `amount_mb=1` for unlimited packages caused:

1. "0.00 GB" displayed instead of "Unlimited" in WA notifications
2. Settlement amount showing "Rp 10.000" instead of actual "Rp 4.000.000"
3. Admin settlement opening blank browser tab
4. Online payment flow blocked for unlimited users with valid debts
5. Debt cleared WA notification sending wrong template keys (no content rendered)

## Impact

- **Users** received confusing WA messages with "0.00 GB" and incorrect settlement amounts
- **Admin** saw blank browser tabs when settling debts
- **Unlimited users** could not settle debts via online payment (Midtrans)
- **Financial reporting** incorrect — Rp 10.000 shown instead of Rp 4.000.000

## Root Cause Analysis

### RC-1: Sentinel value not handled in display layer

Unlimited debt items store `amount_mb=1` (sentinel) with note containing "unlimited". When `format_mb_to_gb(1)` is called, it returns "0.00 GB" because 1 MB = ~0.001 GB.

**Affected locations:**
- `user_profile.py` — `total_manual_debt_gb` in `user_debt_added` WA context
- `user_management_routes.py` — `paid_manual_debt_gb`, `paid_total_debt_gb`, `remaining_manual_debt_gb` in settle-single and settle-all WA contexts

### RC-2: Settlement amount estimation from sentinel MB

`estimate_amount_rp_for_mb(paid_manual_mb)` where `paid_manual_mb=4` (4 unlimited items × 1 MB) yields ~Rp 10.000. The system should use `price_rp` from the debt items instead.

**Affected locations:**
- `debt_settlement_receipt_service.py` — settle-all path had no access to per-item `price_rp`
- `user_management_routes.py` — settle-single/all WA amount display

### RC-3: debt_clear WA sends wrong template keys

`user_profile.py` sent `paid_auto_debt_mb`, `paid_manual_debt_mb`, `paid_total_debt_mb`, `remaining_mb` — but the WA template `user_debt_cleared` expects `paid_auto_debt_gb`, `paid_manual_debt_gb`, `paid_total_debt_gb`, `paid_total_debt_amount_display`, `payment_channel_label`, `remaining_quota`, `receipt_url`.

### RC-4: Blank page from preemptive window.open

`UserDebtLedgerDialog.vue` opened `window.open('', '_blank', 'noopener')` before the API call. If the receipt URL was unavailable or the request failed, the blank tab persisted.

### RC-5: Online payment blocked for unlimited users

`initiation_routes.py` line 619 unconditionally blocked `is_unlimited_user=True` from initiating debt settlement, even when they had valid manual debts.

### RC-6: Online payment pricing ignores price_rp

`initiation_routes.py` used `estimate_debt_rp_for_mb(manual_item_remaining_mb)` instead of checking the debt item's explicit `price_rp` field.

### RC-7: Missing debt_item_id in online settlement mutation event

`debt_helpers.py` did not include `debt_item_id` in the `transactions.debt_settlement_success` mutation event, so receipt generation could not find the specific debt item.

### RC-8: No WA notification for online debt settlement

`webhook_routes.py` debt settlement success path did not send any WA notification to the user, unlike the regular package purchase flow.

## Fixes Applied

### 1. `debt_settlement_receipt_service.py` — Settle-all price_rp from items
- For settle-all (no `debt_item_id`), query recently settled `UserQuotaDebt` items within 10s window
- Sum their `price_rp` values instead of estimating from tiny sentinel MB
- Detect unlimited items in the batch for display purposes

### 2. `user_management_routes.py` — Settle WA unlimited display
- Added `_is_unlimited_debt_item()` helper: checks `amount_mb <= 1` and "unlimited" in note
- Added `_format_remaining_manual_debt_display()`: queries open unlimited items for count display
- Settle-single WA: uses receipt_context for gb/amount values; falls back to unlimited-aware display
- Settle-all WA: uses receipt_context for manual/total gb; unlimited-aware remaining_quota

### 3. `user_profile.py` — debt_added & debt_clear WA
- Added `_format_total_manual_debt_gb()`: queries open unlimited debt items for count display
- `user_debt_added` WA: `total_manual_debt_gb` and `total_debt_gb` use unlimited-aware formatter
- `user_debt_cleared` WA: **Complete rewrite** — fixed all wrong keys (`_mb` → `_gb`), added `payment_channel_label`, `paid_total_debt_amount_display`, `remaining_quota`, `receipt_url`; detects settled unlimited items

### 4. `UserDebtLedgerDialog.vue` — Remove preemptive blank tab
- `settleItem()` and `settleAll()` no longer call `window.open('', '_blank')` upfront
- PDF opens only after blob is fetched successfully
- `openPdfDocument()` simplified — no more `targetWindow` parameter
- Popup blocked → snackbar notification instead of thrown error

### 5. `initiation_routes.py` — Unlimited guard + pricing fix
- Unlimited users: only blocked if `quota_debt_manual_mb <= 0` (no manual debts)
- Pricing: checks `manual_item.price_rp` first before falling back to estimation

### 6. `debt_helpers.py` — debt_item_id in mutation event
- Added `debt_item_id` to `transactions.debt_settlement_success` event_details

### 7. `webhook_routes.py` — WA notification for online debt settlement
- Added WA notification (`user_debt_cleared` / `user_debt_cleared_unblock`) after successful debt settlement
- Uses receipt context for unlimited-aware display values
- Best-effort with proper error handling

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/debt_settlement_receipt_service.py` | Settle-all queries price_rp from settled items |
| `backend/app/infrastructure/http/admin/user_management_routes.py` | Unlimited helpers + settle WA fix |
| `backend/app/services/user_management/user_profile.py` | debt_added + debt_clear WA fix |
| `frontend/components/admin/users/UserDebtLedgerDialog.vue` | Remove blank tab, simplify PDF open |
| `backend/app/infrastructure/http/transactions/initiation_routes.py` | Unlimited guard + price_rp pricing |
| `backend/app/infrastructure/http/transactions/debt_helpers.py` | debt_item_id in event |
| `backend/app/infrastructure/http/transactions/webhook_routes.py` | WA notification for online settlement |

## Testing

- Verify WA notification for `user_debt_added` shows "X item Unlimited" for total_manual_debt_gb
- Verify WA notification for `user_debt_cleared` (admin + online) shows correct amounts
- Verify admin settle-single and settle-all show "Unlimited" and correct Rp amounts
- Verify online debt settlement for unlimited users works (Midtrans initiation)
- Verify PDF receipt shows correct amounts for unlimited settlements
- Verify no blank browser tab when settling from UserDebtLedgerDialog

## Timeline

- **25 Mar 2026 18:23 WITA** — "Catatan Tunggakan Baru" WA received with "Total tunggakan kuota: 0.00 GB"
- **26 Mar 2026 05:24 WITA** — "Tunggakan Selesai" WA received with "Rp 10.000" and all "0.00 GB"
- **26 Mar 2026** — All 8 root causes identified and fixed
