# Devlog: 2026-03-27 — Quota History WA, Admin UX Polish, Mobile Layout Fix

**Tanggal**: 27 Maret 2026
**Author**: Abdullah (via GitHub Copilot)
**Scope**: fitur baru quota history WA, relokasi tombol admin, mobile responsive fix, analisa log produksi

---

## Ringkasan

Batch ini menyelesaikan empat area pengembangan dalam satu sesi:

1. **WhatsApp kirim riwayat mutasi kuota** — backend endpoint + PDF generation + Fonnte integration + frontend button
2. **Relokasi tombol Reset Password** — dari area inject-actions ke footer dialog, dibatasi role ADMIN
3. **Export PDF menggantikan Print** — ikon dan label diperbarui di dialog riwayat mutasi kuota
4. **Mobile layout fix** — kartu "Preview Cleanup Nonaktif" di halaman admin users tidak lagi wrapping di mobile
5. **Analisa log produksi** — nginx error log, docker backend/celery, tidak ditemukan anomali

---

## Implementasi Detail

### 1. Endpoint Quota History WA

**Backend** (`backend/app/infrastructure/http/admin/user_management_routes.py`):

- `POST /api/admin/users/<uuid>/quota-history/send-wa`
  - Menerima `recipient_phone`, `start_date`, `end_date`
  - Generate PDF via WeasyPrint menggunakan template `quota_report.html`
  - Kirim PDF ke Fonnte sebagai attachment
  - Fallback ke teks WA jika PDF generation gagal
  - Return `{"status": "sent", "method": "pdf"|"text"}`

- `GET /api/admin/users/quota-report/temp/<token>.pdf`
  - Route publik tanpa auth untuk akses PDF oleh provider WA (Fonnte)
  - Token sementara berbasis `notification_service` dengan salt `quota-report`
  - Auto-expire setelah 1 jam

**OpenAPI** (`contracts/openapi/openapi.v1.yaml`):
- Skema `AdminQuotaHistorySendWaRequest` dan `AdminQuotaHistorySendWaResponse` ditambahkan
- Endpoint didokumentasikan di path `/admin/users/{id}/quota-history/send-wa`

**Frontend** (`frontend/components/admin/users/UserQuotaHistoryDialog.vue`):
- Fungsi `sendQuotaHistoryWa()` — kirim POST ke endpoint baru, snackbar sukses/error
- Tombol WhatsApp (`tabler-brand-whatsapp`) di header dialog
- Tombol Export PDF (`tabler-download`) menggantikan printer icon

### 2. Relokasi Reset Password

**Frontend** (`frontend/components/admin/users/UserEditDialog.vue`):
- Tombol Reset Password dipindah dari area inject-actions ke `VCardActions` di footer
- Layout `justify-space-between` memisahkan Reset Password (kiri) dan Batal (kanan)
- Tombol hanya tampil jika `authStore.isAdmin === true`

### 3. Mobile Layout Fix

**Frontend** (`frontend/pages/admin/users.vue`):
- CSS `@media (max-width: 600px)` untuk `.admin-users__cleanupCardItem`:
  - `grid-template-columns: max-content 1fr !important` — override Vuetify 3 default 3-column grid
  - `.v-card-item__append` mendapat `grid-column: 1 / -1` — tombol turun ke baris penuh di bawah judul
  - `.admin-users__cleanupCardActions` mendapat `display: flex; gap: 8px` — tombol side-by-side

**Root cause**: Vuetify 3 `VCardItem` menggunakan `display: grid` (bukan flex), sehingga CSS lama `flex-direction: column` tidak punya efek.

### 4. Analisa Log Produksi

**Nginx Error Log** (4 entry total):
- 2x 502 pada 26 Mar 13:03 — selama deploy/recreate, backend upstream refused
- 2x 502 pada 27 Mar 09:01 — selama deploy/recreate, backend upstream refused
- **Verdict**: Normal, hanya terjadi saat window restart container

**Nginx Access Log**:
- Zero 5xx di luar window deploy
- 4xx normal: session expired, wrong password attempt, unregistered captive device
- 499 (client disconnect) pada healthcheck dan slow query — harmless

**Docker Backend**: Semua log level INFO, zero error/exception. Gunicorn healthy, MikroTik pool OK.

**Celery Worker**: Semua task sukses dengan 0 failure:
- `sync_hotspot_usage_task`: 85-86 processed, 0 failed
- `sync_unauthorized_hosts_task`: 206-209 hosts, 0 failed
- `policy_parity_guard_task`: "no mismatch detected"
- `send_manual_debt_reminders_task`: checked=0 (none pending)

---

## CI/CD

| Push | Commit | Hasil | Catatan |
|------|--------|-------|---------|
| 1 | `8de3c1ced` | CI FAIL | contract-gate: OpenAPI/contracts belum diupdate |
| 2 | `05b169620` | CI FAIL | api_quality_gate: generated contracts out of date |
| 3 | `be562a1eb` | CI FAIL | frontend typecheck: inline object types di contracts.generated.ts |
| 4 | `1fdc6e0a9` | CI GREEN | Semua jobs passed |
| 5 | `7591a07ca` | — | Mobile layout fix (push terakhir) |

Docker publish sukses (run 23641248375), deploy via `deploy_pi.sh --recreate --detach-local` sukses.

---

## Pelajaran

1. **Vuetify 3 VCardItem adalah grid, bukan flex.** Jangan gunakan `flex-direction` untuk mengubah layout — gunakan `grid-template-columns` dan `grid-column`.
2. **OpenAPI contract gate ketat.** Setiap penambahan endpoint baru wajib update: `openapi.v1.yaml`, `contracts.generated.ts`, `contracts.ts`, `API_DETAIL.md`.
3. **Inline object types di generated contracts bisa memecahkan Nuxt auto-import scanner.** Gunakan named schemas di OpenAPI agar TypeScript types mendapat nama yang stabil.
